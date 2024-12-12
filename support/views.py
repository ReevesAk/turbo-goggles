import logging

from django.db import transaction
from django.core.exceptions import PermissionDenied
from django.contrib.auth.hashers import check_password

# In project imports.
from .serializers import (
    CreateTicketSerializers, AssignTicketSerializers, AgentRatingSerializers, TicketSerializers, UserWithTicketsSerializer
)
from .models import Ticket, AgentRating

# Third party imports.
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.pagination import PageNumberPagination

from accounts.models import User, UserNotification, AccountType
from roles.models import ActivityModel
from permissions import (
    IsSuperAdmin,
)


logger = logging.getLogger(__name__)


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
        logger.info("Received request to create a support ticket.")

        # Clean up the payload
        payload = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in request.data.items()
        }
        logger.debug("Payload after stripping: %s", payload)

        serializer = self.get_serializer(data=payload)
        if not serializer.is_valid(raise_exception=True):
            logger.warning("Serializer validation failed: %s", serializer.errors)
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user_data = serializer.validated_data
        user_email = payload.get("email")
        logger.debug("User email extracted from payload: %s", user_email)

        try:
            user = User.objects.get(email=user_email)
            logger.info("User  found: %s", user)
        except User.DoesNotExist:
            logger.error("User  with email %s not found.", user_email)
            return Response(
                data={"error": "User  not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        category = payload.get("category")
        logger.debug("Creating ticket with category: %s", category)

        # Create the ticket
        ticket = Ticket.objects.create(
            user=user,
            title=category,
            escalation_level="Management",
            status="Queuing",
        )
        logger.info("Ticket created successfully: %s", ticket)

        # Create user notification
        UserNotification.objects.create(
            user=user,
            title="Create Ticket",
            message="Support ticket has been created for your issue."
        )
        logger.info("User  notification created for user: %s", user)

        # Log activity
        ActivityModel.objects.create(
            user=user,
            title="Create Ticket",
            message="Support ticket has been created for your issue"
        )
        logger.info("Activity logged for user: %s", user)

        resp = {
            "status": "success",
            "message": f"Support ticket created for {user.first_name} {user.last_name}, for {category} issues.",
            "data": serializer.data,
            "created_at": user_data["created_at"],
        }
        logger.info("Response prepared successfully: %s", resp)
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
        logger.info("Received request to assign a support ticket.")

        authenticated_user = request.user
        payload = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in request.data.items()
        }
        logger.debug("Payload after stripping: %s", payload)

        serializer = self.get_serializer(data=payload)
        if not serializer.is_valid(raise_exception=True):
            logger.warning("Serializer validation failed: %s", serializer.errors)
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        admin_email = payload.get("agent_email")
        ticket_id = payload.get("ticket_id")
        pin = request.data.get("pin")
        logger.debug("Admin email: %s, Ticket ID: %s", admin_email, ticket_id)

        # Attempt to retrieve the ticket
        try:
            ticket = Ticket.objects.get(id=ticket_id)
            logger.info("Ticket found: %s", ticket)
        except Ticket.DoesNotExist:
            logger.error("Ticket with ID %s does not exist.", ticket_id)
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
            logger.info("User  found: %s", user)
        except User.DoesNotExist:
            logger.error("User  with email %s does not exist.", admin_email)
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
            "UserAdmin",
            "PartnersAdmin",
            "ContentAdmin",
            "IntegrationAdmin",
            "WalletAdmin",
        ]

        is_admin = AccountType.objects.filter(
            user=user, user_type__in=admin_types
        ).exists()

        if not is_admin:
            logger.warning("User  %s exists, but is not an admin.", user.email)
            raise PermissionDenied("User  exists, but is not an admin.")

        if check_password(password=pin, encoded=authenticated_user.admin_pin):
            logger.info("Pin verification successful for user: %s", authenticated_user)

            # Assign the ticket to the user
            ticket.assigned_to = user
            ticket.save()
            logger.info("Ticket %s assigned to user: %s", ticket_id, user.full_name)

            # Log the activity
            ActivityModel.objects.create(
                user=authenticated_user,
                title="Assign Ticket",
                message=f"Support ticket {ticket_id} has been assigned to {user.full_name}."
            )
            logger.info("Activity logged for assigning ticket %s to user: %s", ticket_id, user.full_name)

            response = {
                "status": "success",
                "message": f"Support ticket {ticket_id} has been successfully assigned to {user.full_name}",
                "data": serializer.data,
            }
            logger.info("Response prepared successfully: %s", response)
            return Response(data=response, status=status.HTTP_201_CREATED)
        else:
            logger.warning("Incorrect pin provided for user: %s", authenticated_user)
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
        logger.info("Received request to list all support tickets.")

        tickets = Ticket.objects.all().order_by("-created_at")
        logger.debug("Total tickets found: %d", tickets.count())

        paginator = self.pagination_class()
        paginated_tickets = paginator.paginate_queryset(tickets, request)
        logger.debug("Paginated tickets: %s", paginated_tickets)

        # Prepare response data
        data = []
        for ticket in paginated_tickets:
            data.append(
                {
                    "ticket_number": ticket.ticket_number,
                    "authorised_by": "SuperAdmin",
                    "category": ticket.category,
                    "description": ticket.description,
                    "created_at": ticket.created_at,
                    "assigned_to": ticket.assigned_to,
                    "assigned_at": ticket.assigned_at,
                    "ticket_channel": ticket.channel,
                    "escalation_level": ticket.escalation_level,
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
        logger.info("Response prepared successfully with %d tickets.", len(data))
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
    lookup_field = "ticket_number"

    def retrieve(self, request, *args, **kwargs):
        logger.info("Received request to retrieve support ticket.")

        ticket_id = kwargs.get("ticket_number")
        logger.debug("Attempting to retrieve ticket with ID: %s", ticket_id)

        try:
            ticket = Ticket.objects.get(id=ticket_id)
            logger.info("Ticket found: %s", ticket)

            # Prepare the response data
            response = {
                "status": "success",
                "message": "Support Ticket retrieved successfully!",
                "title": ticket.title,
                "data": {
                    "ticket_id": ticket_id,
                    "category": ticket.category,
                    "description": ticket.description,
                    "created_at": ticket.created_at,
                    "assigned_to": ticket.assigned_to,
                    "assigned_at": ticket.assigned_at,
                    "ticket_channel": ticket.channel,
                    "escalation_level": ticket.escalation_level,
                    "status": ticket.status
                },
            }
            logger.info("Response prepared successfully for ticket ID: %s", ticket_id)
            return Response(data=response, status=status.HTTP_200_OK)

        except Ticket.DoesNotExist:
            logger.error("Ticket with ID %s not found.", ticket_id)
            return Response(
                {"status": "fail", "message": "Ticket not found."},
                status=status.HTTP_404_NOT_FOUND,
            )


class GetTicketByChannel(generics.ListAPIView):
    """
    GetTicketByChannel handles the GET request for searching
    tickets by ticket chanell.
    """

    serializer_class = TicketSerializers
    authentication_classes = [JWTAuthentication, IsSuperAdmin]
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        search_term = kwargs.get("search_term")
        logger.info(f"Received search request for term: {search_term}")

        try:
            # Filter tickets based on channel type.'
            tickets = Ticket.objects.filter(channel=search_term).distinct()

            serializer = self.get_serializer(tickets, many=True)

            if tickets.exists():
                data = {
                    "status": "success",
                    "message": "Tikcets fetched successfully.",
                    "data": serializer.data,
                }
                logger.info(
                    f"Found {tickets.count()} tickets matching the channel search term: {search_term}"
                )
                return Response(data=data, status=status.HTTP_200_OK)
            else:
                data = {
                    "status": "fail",
                    "message": "No tickets matching that query found.",
                    "data": [],
                }
                logger.warning(
                    f"No tickets found matching the channel search term: {search_term}"
                )
                return Response(data=data, status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            logger.exception(f"Error occurred while searching for partners: {e}")
            return Response(
                {
                    "status": "error",
                    "message": "An error occurred while processing the request.",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class RateSupportAgent(generics.GenericAPIView):
    """
    RateSupportAgent is the POST request handler that allows a user to rate asupport agent.
    """

    serializer_class = AgentRatingSerializers
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    lookup_field = "ticket_number"

    def post(self, request, *args, **kwargs):
        logger.info("Received request to retrieve support ticket.")

        authenticated_user = request.user
        payload = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in request.data.items()
        }

        serializer = self.get_serializer(data=payload)
        if not serializer.is_valid(raise_exception=True):
            logger.warning("Serializer validation failed: %s", serializer.errors)
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        ticket_id = kwargs.get("ticket_number")
        agent_id = kwargs.get("agent_id")

        logger.debug("Attempting to retrieve ticket with ID: %s", ticket_id)

        try:
            with transaction.atomic():
                ticket = Ticket.objects.select_for_update().get(id=ticket_id)
                agent = User.objects.get(id=agent_id)

            # Proceed with your logic using `ticket` and `agent`
            # For example, you might want to return some data or perform some action

        except Ticket.DoesNotExist:
            logger.error("Ticket with ID %s does not exist.", ticket_id)
            return Response({"error": "Ticket not found."}, status=status.HTTP_404_NOT_FOUND)

        except User.DoesNotExist:
            logger.error("User  with ID %s does not exist.", agent_id)
            return Response({"error": "User  not found."}, status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            logger.exception("An unexpected error occurred: %s", str(e))
            return Response({"error": "An unexpected error occurred."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        logger.info("Ticket found: %s", ticket)
        AgentRating.objects.create(
            user=authenticated_user,
            agent=agent,
            ticket=ticket,
            rating=request.data.get("rating"),
            rating_comment=request.get("rating_comment")
        )

        # Create user notification
        UserNotification.objects.create(
            user=authenticated_user,
            title="Agent Rating",
            message=f"Your rating of agent: {agent.full_name} has been recorded."
        )
        logger.info("User  notification created for user: %s", authenticated_user)

        # Log activity
        rating = request.data.get("rating")
        ActivityModel.objects.create(
            user=authenticated_user,
            title="Agent Rating",
            message=f"{authenticated_user.first_name} {authenticated_user.last_name} rated {agent.full_name} as {rating}."
        )
        logger.info("Activity logged for user: %s", authenticated_user)

        resp = {
            "status": "success",
            "message": "Agent rating was successful.",
            "data": serializer.data
        }
        return Response(data=resp, status=status.HTTP_201_CREATED)


class UsersWithTickets(generics.ListAPIView):
    """
    UsersWithTickets is the GET request handler that returns a list of
    all users with support tickets.
    """

    serializer_class = TicketSerializers
    permission_classes = [IsAuthenticated,IsSuperAdmin]
    authentication_classes = [JWTAuthentication]

    def get(self, request, *args, **kwargs):
        users_with_tickets = User.objects.filter(user_tickets__isnull=False).distinct()
        serializer = TicketSerializers(users_with_tickets, many=True)
        return Response(
            data={
                "status": "success",
                "message": "Users with tickets retrieved successfully.",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )
