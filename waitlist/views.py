import logging
from datetime import timedelta

from django.db.models import Count
from django.utils import timezone

# Third party imports.
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from drf_spectacular.utils import extend_schema

# In project imports.
from .serializers import (
    WaitlistSerialiser,
    VerifyWaitlistOTPSerializer,
)
from .models import WaitlistModel, Referral
from permissions import IsTaskAdminOrSuperAdmin
from security import encrypt
from accounts.otp import otp_manager
from commons import Messaging

logger = logging.getLogger("accounts")

WAITLIST_TARGET = 1000
WAITLIST_REWARD = 500


@extend_schema(summary="Join or check beta waitlist", tags=["Waitlist"])
class JoinBetaUserWaitList(generics.GenericAPIView):
    """
    JoinBetaUserWaitList handles the POST request method of
    onboarding beta waitlist users.
    """

    serializer_class = WaitlistSerialiser
    permission_classes = (AllowAny,)

    def get(self, request, *args, **kwargs):
        total_users = WaitlistModel.objects.count()
        remaining_slots = max(0, WAITLIST_TARGET - total_users)

        return Response(
            {
                "status": "success",
                "message": "Waitlist slots retrieved successfully.",
                "data": {
                    "waitlist_target": WAITLIST_TARGET,
                    "total_joined": total_users,
                    "remaining_slots": remaining_slots,
                    "reward": WAITLIST_REWARD,
                },
            },
            status=status.HTTP_200_OK,
        )

    def post(self, request, *args, **kwargs):
        data = request.data.copy()
        is_student = data.get("is_student")
        institution = data.get("institution")
        # Only students can select institution
        if not is_student and institution:
            return Response(
                {
                    "status": "fail",
                    "message": "Only students are allowed to select the institution option.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = self.serializer_class(data=data)
        if not serializer.is_valid(raise_exception=True):
            return Response(
                data=(serializer.errors), status=status.HTTP_400_BAD_REQUEST
            )
        waitlist_user = serializer.save()

        if waitlist_user.phone:
            otp = otp_manager.create_otp(user_id=str(waitlist_user.id))
            phone = waitlist_user.phone.lstrip("0")
            Messaging.send_sms(
                phone_number=phone,
                msg=f"Your Picadailys verification code is {otp}. Expires in 5 minutes.",
            )

        # Award 10 points for joining the waitlist
        waitlist_user.points = 10
        waitlist_user.save(update_fields=["points"])

        referral_code = serializer.validated_data.get("referral_code")
        if referral_code:
            try:
                referrer = WaitlistModel.objects.get(referral_code=referral_code)

                if referrer.email == waitlist_user.email:
                    return Response(
                        data={
                            "status": "fail",
                            "message": "User cannot refer himself.",
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                referrer.referral_count = (referrer.referral_count or 0) + 1
                referrer.points = (referrer.points or 0) + 50
                referrer.save(update_fields=["referral_count", "points"])

                # Create a Referral record for this event
                Referral.objects.create(referrer=referrer, referred=waitlist_user)

            except WaitlistModel.DoesNotExist:
                return Response(
                    data={
                        "status": "fail",
                        "message": "Referral deos not found.",
                        "data": serializer.data,
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )

        total_users = WaitlistModel.objects.count()
        remaining_slots = max(0, WAITLIST_TARGET - total_users)

        return Response(
            {
                "status": "success",
                "message": "Successfully joined waitlist",
                "data": {
                    "id": waitlist_user.id,
                    "first_name": waitlist_user.f_name,
                    "last_name": waitlist_user.l_name,
                    "email": waitlist_user.email,
                    "referral_code": waitlist_user.referral_code,
                    "points": waitlist_user.points,
                    "is_verified": waitlist_user.is_verified,
                    "whatsApp_group_link": "http://whatsapp.com/channel/0029Vb8AFp8EFeXqoKuXcu0y",
                    "remaining_slots": remaining_slots,
                },
            },
            status=status.HTTP_201_CREATED,
        )


@extend_schema(summary="Get waitlist user dashboard by email", tags=["Waitlist"])
class WaitlistDashboardView(APIView):
    """Returns a waitlist user's details by email."""

    permission_classes = (AllowAny,)

    def get(self, request, *args, **kwargs):
        email = request.query_params.get("email")

        if not email:
            return Response(
                {"status": "fail", "message": "Email is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = WaitlistModel.objects.get(email=email)
        except WaitlistModel.DoesNotExist:
            return Response(
                {"status": "fail", "message": "User not found on the waitlist."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not user.is_verified:
            if user.phone:
                otp = otp_manager.create_otp(user_id=str(user.id))
                phone = user.phone.lstrip("0")
                Messaging.send_sms(
                    phone_number=phone,
                    msg=f"Your Picadailys verification code is {otp}. Expires in 5 minutes.",
                )
            return Response(
                {
                    "status": "unverified",
                    "message": "Your account is not verified. An OTP has been sent to your phone.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        total_users = WaitlistModel.objects.count()
        remaining_slots = max(0, WAITLIST_TARGET - total_users)

        return Response(
            {
                "status": "success",
                "message": "Waitlist details retrieved.",
                "data": {
                    "id": user.id,
                    "first_name": user.f_name,
                    "last_name": user.l_name,
                    "email": user.email,
                    "phone": user.phone,
                    "referral_code": user.referral_code,
                    "referral_count": user.referral_count or 0,
                    "points": user.points,
                    "is_student": user.is_student,
                    "institution": user.institution,
                    "is_verified": user.is_verified,
                    "remaining_slots": remaining_slots,
                },
            },
            status=status.HTTP_200_OK,
        )


@extend_schema(
    summary="Verify waitlist OTP",
    description="Submit the OTP sent to the user's phone after joining the waitlist. On success, the account is marked as verified.",
    request=VerifyWaitlistOTPSerializer,
)
class VerifyWaitlistOTP(APIView):
    """Verifies OTP sent to a waitlist user's phone and marks them as verified."""

    permission_classes = (AllowAny,)

    def post(self, request, *args, **kwargs):
        email = request.data.get("email", "").strip()
        otp = request.data.get("otp", "").strip()

        if not email or not otp:
            return Response(
                {"status": "fail", "message": "Email and OTP are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = WaitlistModel.objects.get(email=email)
        except WaitlistModel.DoesNotExist:
            return Response(
                {"status": "fail", "message": "User not found on the waitlist."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if user.is_verified:
            return Response(
                {"status": "success", "message": "Account already verified."},
                status=status.HTTP_200_OK,
            )

        user_id = otp_manager.validate_user_otp(otp)
        if not user_id or int(user_id) != user.id:
            return Response(
                {"status": "fail", "message": "Invalid or expired OTP."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.is_verified = True
        user.save(update_fields=["is_verified"])

        return Response(
            {"status": "success", "message": "Phone number verified successfully."},
            status=status.HTTP_200_OK,
        )


class WaitlistPagination(PageNumberPagination):
    page_size = 20


@extend_schema(
    summary="List public waitlist users (limited details)", tags=["Waitlist"]
)
class PublicWaitlistListView(generics.ListAPIView):
    """Public list of waitlist users with limited details."""

    permission_classes = (AllowAny,)
    pagination_class = WaitlistPagination

    def get_queryset(self):
        return WaitlistModel.objects.all().order_by("-points", "-id")

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        total_users = queryset.count()
        remaining_slots = max(0, WAITLIST_TARGET - total_users)
        page = self.paginate_queryset(queryset)
        users = page if page is not None else queryset

        data = [
            {
                "first_name": user.f_name,
                "last_name": user.l_name,
                "referral_code": user.referral_code,
                "points": user.points,
                "joined_at": user.joined_at,
            }
            for user in users
        ]

        if page is not None:
            paginated = self.get_paginated_response(data).data
            paginated["remaining_slots"] = remaining_slots
            return Response(paginated, status=status.HTTP_200_OK)

        return Response(
            {"status": "success", "data": data, "remaining_slots": remaining_slots},
            status=status.HTTP_200_OK,
        )


@extend_schema(
    summary="List all waitlist users with full details (admin)", tags=["Waitlist"]
)
class AdminWaitlistListView(generics.ListAPIView):
    """Admin list of all waitlist users with full details. TaskAdmin & SuperAdmin only."""

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, IsTaskAdminOrSuperAdmin]
    pagination_class = WaitlistPagination

    def get_queryset(self):
        return WaitlistModel.objects.all().order_by("-points", "-id")

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        total_users = queryset.count()
        remaining_slots = max(0, WAITLIST_TARGET - total_users)
        page = self.paginate_queryset(queryset)
        users = page if page is not None else queryset

        data = [
            {
                "id": u.id,
                "first_name": u.f_name,
                "last_name": u.l_name,
                "email": u.email,
                "phone": u.phone,
                "referral_code": u.referral_code,
                "referral_count": u.referral_count or 0,
                "points": u.points,
                "is_student": u.is_student,
                "institution": u.institution,
                "joined_at": u.joined_at.isoformat() if u.joined_at else None,
            }
            for u in users
        ]

        if page is not None:
            paginated = self.get_paginated_response(data).data
            paginated["remaining_slots"] = remaining_slots
            return Response(data=encrypt(paginated), status=status.HTTP_200_OK)

        return Response(
            data=encrypt(
                {"status": "success", "data": data, "remaining_slots": remaining_slots}
            ),
            status=status.HTTP_200_OK,
        )


@extend_schema(summary="Delete duplicate waitlist entries (admin)", tags=["Waitlist"])
class AdminWaitlistDeleteDuplicatesView(generics.GenericAPIView):
    """
    Admin endpoint to delete all duplicate waitlist users (including swapped names).
    TaskAdmin & SuperAdmin only.
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, IsTaskAdminOrSuperAdmin]

    def delete(self, request, *args, **kwargs):
        from collections import defaultdict

        name_map = defaultdict(list)
        for user in WaitlistModel.objects.all():
            f = (user.f_name or "").strip().lower()
            ln = (user.l_name or "").strip().lower()
            key = tuple(sorted([f, ln]))
            name_map[key].append(user.id)
        duplicate_ids = [
            uid for ids in name_map.values() if len(ids) > 1 for uid in ids
        ]
        qs = WaitlistModel.objects.filter(id__in=duplicate_ids)
        count = qs.count()
        qs.delete()
        return Response(
            data={"status": "success", "deleted": count}, status=status.HTTP_200_OK
        )


@extend_schema(summary="Get top 5 referrers for the current week", tags=["Waitlist"])
class WeeklyTopReferrersView(APIView):
    """
    WeeklyTopReferrersView is the GET request method that returns
    the top 5 referrers for the current week.
    """

    permission_classes = (AllowAny,)

    def get(self, request, *args, **kwargs):
        # Get the start and end of the current week (Monday to Sunday)
        now = timezone.now()
        start_of_week = now - timedelta(days=now.weekday())
        end_of_week = start_of_week + timedelta(days=7)

        # Aggregate referrals made this week
        weekly_referrals = (
            Referral.objects.filter(
                created_at__gte=start_of_week, created_at__lt=end_of_week
            )
            .values("referrer")
            .annotate(referral_count=Count("id"))
            .order_by("-referral_count")[:5]
        )
        # Fetch user details for the top referrers
        referrer_ids = [item["referrer"] for item in weekly_referrals]
        users = {u.id: u for u in WaitlistModel.objects.filter(id__in=referrer_ids)}
        data = []
        for item in weekly_referrals:
            user = users.get(item["referrer"])
            if user:
                data.append(
                    {
                        "first_name": user.f_name,
                        "last_name": user.l_name,
                        "email": user.email,
                        "referral_code": user.referral_code,
                        "referral_count": item["referral_count"],
                        "total_points": user.points,
                        "joined_at": user.joined_at,
                    }
                )
        return Response(
            data={
                "status": "success",
                "data": data,
                "week_start": start_of_week.isoformat(),
                "week_end": end_of_week.isoformat(),
            },
            status=status.HTTP_200_OK,
        )


@extend_schema(
    summary="Bulk delete waitlist users by email list (admin)", tags=["Waitlist"]
)
class BulkDeleteWaitlistUsers(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, IsTaskAdminOrSuperAdmin]

    def post(self, request):
        emails = request.data.get("emails", [])
        if not isinstance(emails, list) or not emails:
            return Response(
                {"status": "fail", "message": "A list of emails is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            deleted, _ = WaitlistModel.objects.filter(email__in=emails).delete()
            logger.info("Bulk deleted %d waitlist users.", deleted)
            return Response(
                {"status": "success", "deleted_count": deleted},
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            logger.exception("BulkDeleteWaitlistUsers failed: %s", e)
            return Response(
                {
                    "status": "error",
                    "message": "An error occurred while deleting users.",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
