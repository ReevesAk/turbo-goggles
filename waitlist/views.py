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

logger = logging.getLogger("accounts")


class JoinBetaUserWaitList(generics.GenericAPIView):
    """
    JoinBetaUserWaitList handles the POST request method of
    onboarding beta waitlist users.
    """
    serializer_class = WaitlistSerialiser
    permission_classes = (AllowAny,)

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=WaitlistSerialiser)

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
                    # "referral_link": f"https://yourdomain.com/waitlist?ref={waitlist_user.referral_code}",
                },
            },
            status=status.HTTP_201_CREATED,
        )
    