from django.utils import timezone

import logging

from django.template.loader import render_to_string

# Third party imports.
from rest_framework import generics
from django.contrib.auth import authenticate
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import APIView

from drf_spectacular.utils import extend_schema

# In project imports.
from .serializers import (
    WaitlistSerialiser,
)
from .models import WaitlistModel
from roles.models import ActivityModel
from commons import Messaging
from permissions import IsTaskAdminOrSuperAdmin
from security import encrypt
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from rest_framework_simplejwt.authentication import JWTAuthentication

logger = logging.getLogger("accounts")


class JoinBetaUserWaitList(generics.GenericAPIView):
    """
    JoinBetaUserWaitList handles the POST request method of
    onboarding beta waitlist users.
    """
    serializer_class = WaitlistSerialiser
    permission_classes = (AllowAny,)

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

        referral_code = serializer.validated_data.get("referral_code")
        if referral_code:
            try:
                referrer = WaitlistModel.objects.get(referral_code=referral_code)

                if referrer.email == waitlist_user.email:
                    return Response(
                        data={
                            "status": "fail",
                            "message": "User cannot refer himself."
                        },
                        status=status.HTTP_400_BAD_REQUEST
                    )

                referrer.referral_count = (referrer.referral_count or 0) + 1
                referrer.save(update_fields=["referral_count"])

            except WaitlistModel.DoesNotExist:
                return Response(
                    data={
                        "status": "fail",
                        "message": "Referral deos not found.",
                        "data": serializer.data,
                    },
                    status=status.HTTP_404_NOT_FOUND
                )

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
                    "whatsApp_group_link": "http://whatsapp.com/channel/0029Vb8AFp8EFeXqoKuXcu0y",
                },
            },
            status=status.HTTP_201_CREATED,
        )


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
                    "is_student": user.is_student,
                    "institution": user.institution,
                },
            },
            status=status.HTTP_200_OK,
        )


class WaitlistPagination(PageNumberPagination):
    page_size = 20


class PublicWaitlistListView(generics.ListAPIView):
    """Public list of waitlist users with limited details."""
    permission_classes = (AllowAny,)
    pagination_class = WaitlistPagination

    def get_queryset(self):
        return WaitlistModel.objects.all().order_by("-id")

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        users = page if page is not None else queryset

        data = [
            {
                "first_name": u.f_name,
                "last_name": u.l_name,
                "referral_code": u.referral_code,
            }
            for u in users
        ]

        if page is not None:
            return self.get_paginated_response(data)

        return Response(
            {"status": "success", "data": data},
            status=status.HTTP_200_OK,
        )


class AdminWaitlistListView(generics.ListAPIView):
    """Admin list of all waitlist users with full details. TaskAdmin & SuperAdmin only."""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, IsTaskAdminOrSuperAdmin]
    pagination_class = WaitlistPagination

    def get_queryset(self):
        return WaitlistModel.objects.all().order_by("-id")

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
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
                "is_student": u.is_student,
                "institution": u.institution,
            }
            for u in users
        ]

        if page is not None:
            paginated = self.get_paginated_response(data).data
            return Response(data=encrypt(paginated), status=status.HTTP_200_OK)

        return Response(
            data=encrypt({"status": "success", "data": data}),
            status=status.HTTP_200_OK,
        )
