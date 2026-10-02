import logging

from django.core.cache import cache
from django.utils import timezone

# In project imports.
from .serializers import MemberSerializer, SendPushNotificationSerializer

# Third party imports.
from rest_framework import status, generics
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from accounts.models import User
from gamification.points import Points
from permissions import (
    CanSendUserPush,
    IsNotDisabled,
    IsMemberAdminOrSuperAdminOrTaskAdmin,
)
from user_profile.fcm import send_push_multicast, send_push_to_user
from user_profile.models import DeviceToken
from user_profile.tasks import broadcast_push
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
    permission_classes = [
        IsAuthenticated,
        IsNotDisabled,
        IsMemberAdminOrSuperAdminOrTaskAdmin,
    ]

    def get_queryset(self):
        members = User.objects.filter(account_types__user_type="Member").distinct()
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
    permission_classes = [IsAuthenticated, IsMemberAdminOrSuperAdminOrTaskAdmin]

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
            data=encrypt(
                {
                    "status": "success",
                    "message": "Change requests retrieved successfully",
                    "total": qs.count(),
                    "data": serializer.data,
                }
            ),
            status=status.HTTP_200_OK,
        )


class ReviewHandleChangeRequestView(generics.GenericAPIView):
    serializer_class = ReviewHandleChangeSerializer
    permission_classes = [IsAuthenticated, IsMemberAdminOrSuperAdminOrTaskAdmin]

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

        if action == "approve":
            handle_request.approval_date = timezone.now()
            handle_request.approved_by = request.user

        handle_request.save()

        user = handle_request.user

        if action == "approve":
            survey, _ = MemberSurvey.objects.get_or_create(user=user)
            platform_field = f"{handle_request.platform}_handle"
            setattr(survey, platform_field, handle_request.new_handle)
            survey.allow_handle_change = False
            survey.save(update_fields=[platform_field, "allow_handle_change"])

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
                body=f"Your {handle_request.get_platform_display()} handle has been updated to '{handle_request.new_handle}'. {HANDLE_CHANGE_COST} pts have been deducted.",
                data={
                    "type": "handle_change_approved",
                    "platform": handle_request.platform,
                    "new_handle": handle_request.new_handle,
                },
            )
            message = "Request approved. Handle updated and 50 pts deducted from user."
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


class SendPushNotificationView(generics.GenericAPIView):
    """
    POST - admin sends a custom push notification.
    Body: {"title", "body", "data"?: {...}, and either "user_ids": [..] or
    "all_users": true}. Specific users are sent inline and the response
    reports delivery; all_users is queued (broadcast_push) and returns 202.
    Push only - nothing is written to UserNotification.
    """

    serializer_class = SendPushNotificationSerializer
    permission_classes = [IsAuthenticated, IsNotDisabled, CanSendUserPush]

    def post(self, request):
        serializer = self.get_serializer(data=decrypt(request.data))
        serializer.is_valid(raise_exception=True)
        title = serializer.validated_data["title"]
        body = serializer.validated_data["body"]
        data = serializer.validated_data["data"]

        if serializer.validated_data["all_users"]:
            broadcast_push.delay(title, body, data, sent_by=request.user.email)
            logger.info(
                "Admin %s queued broadcast push (title=%r)", request.user.email, title
            )
            return Response(
                data=encrypt(
                    {
                        "status": "success",
                        "message": "Broadcast queued. It will be delivered to all users with the app shortly.",
                    }
                ),
                status=status.HTTP_202_ACCEPTED,
            )

        user_ids = set(serializer.validated_data["user_ids"])
        found_ids = set(
            User.objects.filter(id__in=user_ids).values_list("id", flat=True)
        )
        tokens = DeviceToken.objects.filter(user_id__in=found_ids).values_list(
            "user_id", "token"
        )
        users_with_device = {uid for uid, _ in tokens}
        sent = send_push_multicast([t for _, t in tokens], title, body, data)

        logger.info(
            "Admin %s sent push to %d users (%d devices delivered, title=%r)",
            request.user.email,
            len(found_ids),
            sent,
            title,
        )
        return Response(
            data=encrypt(
                {
                    "status": "success",
                    "message": f"Push sent to {sent} device(s).",
                    "data": {
                        "users_found": len(found_ids),
                        "devices_sent": sent,
                        "not_found_user_ids": sorted(user_ids - found_ids),
                        "users_without_device": sorted(found_ids - users_with_device),
                    },
                }
            ),
            status=status.HTTP_200_OK,
        )
