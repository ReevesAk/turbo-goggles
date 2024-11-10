import logging
from django.core.exceptions import PermissionDenied
from django.db.models import Count
from django.contrib.auth.hashers import check_password

# In project imports.
from .serializers import (
    CreateTicketSerializers, AssignTicketSerializers
)
from .models import Ticket

# Third party imports.
from rest_framework import generics, status, exceptions
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.pagination import PageNumberPagination

from accounts.models import User, UserNotification, AccountType
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


class AssignTicket(generics.GenericAPIView):
    """
    AssignTicket handles the POST request of assigning a support ticket
    to an agent.
    """

    serializer_class = AssignTicketSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsSuperAdmin]

    def post(self, request):
        authenticated_user = request.user
        payload = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in request.data.items()
        }

        serializer = self.get_serializer(data=payload)
        if not serializer.is_valid(raise_exception=True):
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        admin_email = payload.get("agent_email")
        ticket_id = payload.get("ticket_id")
        pin = request.data.get("pin")

        # Attempt to retrieve the ticket
        try:
            ticket = Ticket.objects.get(id=ticket_id)
        except Ticket.DoesNotExist:
            return Response(
                data={
                    "status": "fail",
                    "message": "Ticket does not exist",
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # Attempt to retrieve the user by email
        try:
            user = User.objects.get(email=admin_email)
        except User.DoesNotExist:
            return Response(
                data={
                    "status": "fail",
                    "message": "User  does not exist",
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # Check if the user is an admin
        admin_types = [
            "SuperAdmin",
            "TaskAdmin",
            "AdAdmin",
            "MembersAdmin",
            "User Admin",
            "PartnersAdmin",
            "ContentAdmin",
            "IntegrationAdmin",
            "WalletAdmin",
        ]

        is_admin = AccountType.objects.filter(
            user=user, user_type__in=admin_types
        ).exists()

        if not is_admin:
            raise PermissionDenied("User  exists, but is not an admin.")

        if check_password(password=pin, encoded=authenticated_user.admin_pin):

            # Assign the ticket to the user
            ticket.assigned_to = user
            ticket.save()

            # Log the activity
            ActivityModel.objects.create(
                user=authenticated_user,
                title="Assign Ticket",
                message=f"Support ticket {ticket_id} has been assigned to {user.full_name}."
            )

            response = {
                "status": "success",
                "message": f"Support ticket {ticket_id} has been successfully assigned to {user.full_name}",
                "data": serializer.data,
            }
            return Response(data=response, status=status.HTTP_201_CREATED)
        else:
            return Response(
                data={"status": "fail", "error": "Incorrect pin"},
                status=status.HTTP_401_UNAUTHORIZED,
            )


class GetAllSupportTickets(generics.ListAPIView):
    """
    GetAllSupportTickets is the GET request handler that allows the SuperAdmin to
    retrieve all support tickets created.
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsSuperAdmin)
    serializer_class = CreateTicketSerializers
    pagination_class = CustomPageNumberPagination

    def list(self, request, *args, **kwargs):

        tickets = Ticket.objects.all().order_by("-created_at")

        paginator = self.pagination_class()
        paginated_tickets = paginator.paginate_queryset(tickets, request)

        # Prepare response data
        data = []
        for ticket in paginated_tickets:
            data.append(
                {
                    "ticket_id": ticket.id,
                    "authorised_by": "SuperAdmin",
                    "title": ticket.title,
                    "description": ticket.description,
                    "created_at": ticket.created_at,
                    "assigned_to": ticket.assigned_to,
                    "assigned_at": ticket.assigned_at,
                    "status": ticket.status
                }
            )

        response = {
            "status": "success",
            "message": "All support tickets fetched successfully!",
            "page": paginator.page.number,
            "page_size": paginator.page.paginator.per_page,
            "total_count": paginator.page.paginator.count,
            "data": data,
        }
        return Response(response, status=status.HTTP_200_OK)


class GetSingleTicket(generics.RetrieveAPIView):
    """
    GetSingleTicket is the GET request handler that allows a SuperAdmin to
    check a specific support ticket.
    """

    queryset = Ticket.objects.all()
    serializer_class = CreateTicketSerializers
    permission_classes = [IsAuthenticated, IsSuperAdmin]
    authentication_classes = [JWTAuthentication]
    lookup_field = "ticket_id"

    def retrieve(self, request, *args, **kwargs):
        try:
            ticket_id = kwargs["ticket_id"]
            ticket = Ticket.objects.get(id=ticket_id)

            # Prepare the response data
            response = {
                "status": "success",
                "message": "Support Ticket retrieved successfully!",
                "title": ticket.title,
                "data": {
                    "ticket_id": ticket_id,
                    "description": ticket.description,
                    "created_at": ticket.created_at,
                    "assigned_to": ticket.assigned_to,
                    "assigned_at": ticket.assigned_at,
                    "status": ticket.status
                },
            }
            return Response(data=response, status=status.HTTP_200_OK)

        except Ticket.DoesNotExist:
            return Response(
                {"status": "fail", "message": "Ticket not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
