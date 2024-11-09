import logging
from django.core.exceptions import ValidationError
from django.db.models import Count

# In project imports.
from .serializers import (
    CreateTicketSerializers
)
from .models import Ticket

# Third party imports.
from rest_framework import generics, status, exceptions
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.pagination import PageNumberPagination

from accounts.models import User, UserNotification
from roles.models import ActivityModel
from permissions import (
    IsSuperAdmin,
)


class CustomPageNumberPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100


class CreateTicket(generics.CreateAPIView):
    """
    CreateTicket handles the POST request of logging an issue from
    a customer and generating a ticket.
    """
    serializer_class = CreateTicketSerializers

    def create(self, request, *args, **kwargs):
        payload = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in request.data.items()
        }
        serializer = self.get_serializer(data=payload)
        if not serializer.is_valid(raise_exception=True):
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user_data = serializer.validated_data
        user_email = payload.get("email")

        try:
            user = User.objects.get(email=user_email)
        except User.DoesNotExist:
            return Response(
                data={"error": "User not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        title = payload.get("tilte")

        Ticket.objects.create(
            user=user,
            title=payload.get("tilte"),
            escalation_level="Managament",
            status="Queuing",
        )

        UserNotification.objects.create(
            user=user,
            title="Create Ticket",
            message="Support ticket has been created for your issue."
        )

        ActivityModel.objects.create(
            user=user,
            title="Create Ticket",
            message="Support ticket has been created for your issue"
        )

        resp = {
            "status": "success",
            "message": f"Support ticket created for {user.first_name} {user.last_login}, for {title}",
            "data": serializer.data,
            "created_at": user_data["created_at"],
        }
        return Response(data=resp, status=status.HTTP_201_CREATED)
