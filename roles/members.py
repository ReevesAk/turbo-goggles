import logging

from django.core.cache import cache
from django.utils import timezone

# In project imports.
from .serializers import MemberSerializer

# Third party imports.
from rest_framework import status, generics
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication

from accounts.models import User
from gamification.points import Points
from permissions import IsNotDisabled, IsMemberAdminOrSuperAdmin
from user_profile.fcm import send_push_to_user
from user_profile.models import HandleChangeRequest, MemberSurvey
from user_profile.serializers import (
    HandleChangeRequestDetailSerializer,
    ReviewHandleChangeSerializer,
)

from security import encrypt, decrypt

logger = logging.getLogger(__name__)

HANDLE_CHANGE_COST = 50


class AllMembersView(generics.ListAPIView):
    serializer_class = MemberSerializer
    permission_classes = [IsAuthenticated, IsNotDisabled, IsMemberAdminOrSuperAdmin]
    authentication_classes = [JWTAuthentication]

    def get_queryset(self):
        members = (
            User.objects.filter(
                account_types__user_type="Member", wallets__isnull=False
            )
            .distinct()
        )
        return members

    def list(self, request, *args, **kwargs):
        cache_key = "all_members"
        cached_response = cache.get(cache_key)

        if cached_response:
            logger.info("Returning cached members list")
            return Response(data=encrypt(cached_response), status=status.HTTP_200_OK)

        queryset = self.get_queryset()
        total_members = queryset.count()
        page = self.paginate_queryset(queryset)

        if total_members == 0:
            response_data = {
                "status": "success",
                "message": "No member found.",
                "No of Members": 0,
                "Members object": [],
            }
        else:
            if page is not None:
                serialized_users = self.get_serializer(page, many=True)
            else:
                serialized_users = self.get_serializer(queryset, many=True)

            response_data = {
                "status": "success",
                "message": "All members retrieved successfully",
                "No of Members": total_members,
                "Members object": serialized_users.data,
            }

        cache.set(cache_key, response_data, timeout=300)  # 5 minutes

        return Response(data=encrypt(response_data), status=status.HTTP_200_OK)


class ListHandleChangeRequestsView(generics.ListAPIView):
    serializer_class = HandleChangeRequestDetailSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, IsMemberAdminOrSuperAdmin]

    def get_queryset(self):
        qs = HandleChangeRequest.objects.select_related("user", "reviewed_by")
        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs

    def list(self, request, *args, **kwargs):
        qs = self.get_queryset()
        serializer = self.get_serializer(qs, many=True)
        return Response(
            data=encrypt({"status": "success", "message": "Change requests retrieved successfully", "total": qs.count(), "data": serializer.data}),
            status=status.HTTP_200_OK,
        )


class ReviewHandleChangeRequestView(generics.GenericAPIView):
    serializer_class = ReviewHandleChangeSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, IsMemberAdminOrSuperAdmin]

    def patch(self, request, pk):
        try:
            handle_request = HandleChangeRequest.objects.select_related("user").get(
                pk=pk
            )
        except HandleChangeRequest.DoesNotExist:
            return Response(
                data=encrypt({"status": "fail", "message": "Request not found."}),
                status=status.HTTP_404_NOT_FOUND,
            )

        if handle_request.status != "pending":
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": f"This request has already been {handle_request.status}.",
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        decrypted_payload = decrypt(request.data)
        serializer = self.get_serializer(data=decrypted_payload)
        serializer.is_valid(raise_exception=True)

        action = serializer.validated_data["action"]
        admin_note = serializer.validated_data.get("admin_note", "")

        handle_request.status = "approved" if action == "approve" else "rejected"
        handle_request.admin_note = admin_note
        handle_request.reviewed_by = request.user
        handle_request.reviewed_at = timezone.now()
        handle_request.save()

        user = handle_request.user

        if action == "approve":
            survey, _ = MemberSurvey.objects.get_or_create(user=user)
            survey.allow_handle_change = True
            survey.save(update_fields=["allow_handle_change"])

            # Deduct 50 pts for the handle change
            Points.deduct(
                user=user,
                amount=HANDLE_CHANGE_COST,
                reason=f"Handle change fee — {handle_request.get_platform_display()}",
                source="handle_change_fee",
                reference_id=str(handle_request.id),
                triggered_by=request.user,
            )

            send_push_to_user(
                user=user,
                title="Handle Change Approved ✅",
                body=f"Your request to change your {handle_request.get_platform_display()} handle has been approved. {HANDLE_CHANGE_COST} pts have been deducted. You can now update it.",
                data={
                    "type": "handle_change_approved",
                    "platform": handle_request.platform,
                },
            )
            message = "Request approved. 50 pts deducted from user."
        else:
            send_push_to_user(
                user=user,
                title="Handle Change Request Declined",
                body=f"Your request to change your {handle_request.get_platform_display()} handle was not approved.{' ' + admin_note if admin_note else ''}",
                data={
                    "type": "handle_change_rejected",
                    "platform": handle_request.platform,
                },
            )
            message = "Request rejected."

        logger.info(
            "Handle change request %s %s by %s",
            pk,
            handle_request.status,
            request.user.email,
        )
        return Response(
            data=encrypt({"status": "success", "message": message}),
            status=status.HTTP_200_OK,
        )
