import logging

from django.db import transaction
from django.contrib.auth.hashers import check_password
from django.contrib.auth.hashers import make_password
from django.core.exceptions import PermissionDenied
from django.contrib.auth import authenticate
from django.core.exceptions import ValidationError
from django.template.loader import render_to_string
from django.utils import timezone

from cloudinary import uploader as cloud

# In project imports.
from .serializers import (
    RegisterAgentManagerSerializer, SupportVerifyOTPSerializer, CreateTicketSerializers, AssignTicketSerializers,
    AgentRatingSerializers, TicketSerializers, TicketEscalateSerializer,
    AddAgentSerializer, AddAgentContdSerializer, SupportAgentLoginSerializers,
    CreateAgentPinSerializer, ListAgentAndModeratorSerializer, TicketAssignmentHistorySerializer,
    UpdateTicketStatusSerializer
)
from .utils import generate_ticket_number
from .models import Ticket, AgentRating, TicketAssignmentHistory, TicketRRTrail

# Third party imports.
from rest_framework import generics, status, serializers
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import MultiPartParser, JSONParser

from accounts.models import User, UserNotification, AccountType, DeviceId
from accounts.tokens import create_jwt_pair_for_user
from accounts.otp import otp_manager
from roles.models import ActivityModel
from permissions import (
    IsSuperAdmin, IsManagerOrSuperAdmin, IsAgent
)
from commons import Messaging

logger = logging.getLogger(__name__)


class CustomPageNumberPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100


class RegisterManager(generics.GenericAPIView):
    """
    RegisterManager handles the POST request of registering an admin Manager,
    It takes in email, phone, active_role, password, and password2.
    Sends an OTP to the phone for validation.
    """
    serializer_class = RegisterAgentManagerSerializer

    def post(self, request):
        # Check if a Manager already exists
        # if User.objects.filter(active_role="Manager").exists():
        #     return Response(
        #         data="Registration is not allowed. Support Agent Manager already exists.",
        #         status=status.HTTP_403_FORBIDDEN,
        #     )
        payload = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in request.data.items()
        }
        serializer = self.serializer_class(data=payload)
        if serializer.is_valid(raise_exception=True):
            try:
                current_user = serializer.save()
                logger.info(
                    f"Support Manager registration initiated for user: {current_user.email}"
                )

                # Set the user's role and create AccountType
                current_user.active_role = "Manager"
                current_user.save()
                logger.info(f"Manager role assigned to user: {current_user.email}")
                AccountType.objects.create(
                    user=current_user,
                    user_type="Manager",
                )
                logger.info(
                    f"AccountType 'Manager' created for user: {current_user.email}"
                )
                # Create and send OTP
                otp = otp_manager.create_otp(user_id=str(current_user.id))
                logger.info(f"OTP generated for user: {current_user.id}, OTP: {otp}")
                msg = f"Welcome Manager! This is a one-time signup. To protect your account, please enter this {otp}."
                recipient = current_user.phone_number[1:]

                # Send OTP message
                Messaging.send_sms(phone_number=recipient, msg=msg)
                logger.info(f"OTP sent to phone number: {recipient}")

                # Log the creation of the SuperUser
                UserNotification.objects.create(
                    user=current_user,
                    title="Create Manager",
                    message="Manager account created Successfully.",
                )
                logger.info(f"UserNotification created for user: {current_user.id}")

                ActivityModel.objects.create(
                    user=current_user,
                    title="Create Manager",
                    description="Manager account created Successfully.",
                )
                logger.info(f"ActivityModel created for user: {current_user.id}")

                response = {
                    "status": "success",
                    "message": "Support Manager account Created Successfully. Check your phone for an OTP.",
                    "data": serializer.data,
                }
                return Response(data=response, status=status.HTTP_201_CREATED)

            except Exception as err:
                logger.error(f"Error occurred while creating Manager: {str(err)}")
                return Response(
                    data={
                        "status": "fail",
                        "message": "An error occurred while creating a Manager",
                        "data": str(err),
                    },
                    status=status.HTTP_409_CONFLICT,
                )
        logger.warning("Invalid data received for Manager registration.")

        return Response(
            data={
                "status": "fail",
                "message": "Invalid data received for Manager registration.",
                "data": serializer.errors,
            },
            status=status.HTTP_400_BAD_REQUEST
        )


class CreateTicket(generics.CreateAPIView):
    """
    CreateTicket handles the POST request of logging an issue for
    a customer and generating a ticket.
    """
    serializer_class = CreateTicketSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, IsSuperAdmin]
    parser_classes = (
        MultiPartParser,
        JSONParser,
    )

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

        user_email = payload.get("email")
        channel = payload.get("channel")
        description = payload.get("description")
        customer_name = payload.get("customer_name")
        customer_email = payload.get("customer_email")
        attachment = request.FILES.get("attachment")
        title = payload.get("title")
        priority = payload.get("priority")
        pin = payload.get("pin")

        attachment_url = None

        if not check_password(password=pin, encoded=request.user.admin_pin):
            return Response(
                data={
                    "status": "fail",
                    "message": "Incorrect pin"
                },
                status=status.HTTP_401_UNAUTHORIZED
            )
        try:
            user = User.objects.get(email=user_email)
            logger.info("User  found: %s", user)
        except User.DoesNotExist:
            logger.error("User with email %s not found.", user_email)
            return Response(
                data={"error": "User not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if attachment:
            upload_attachment = cloud.upload(attachment)
            attachment_url = upload_attachment["url"]

        category = payload.get("category")
        logger.debug("Creating ticket with category: %s", category)

        # Create the ticket
        ticket = Ticket.objects.create(
            user=user,
            customer_name=customer_name,
            customer_email=customer_email,
            title=title,
            category=category,
            channel=channel,
            description=description,
            attachments=attachment_url,
            priority=priority,
            status="New",
        )

        # Save the ticket to get an ID
        ticket.save()

        # Generate and set the number
        ticket.number = generate_ticket_number()
        ticket.save()

        logger.info("Ticket created successfully: %s", ticket)

        # Create user notification
        UserNotification.objects.create(
            user=user,
            title="Create Ticket",
            message="Support ticket has been created for your issue."
        )
        logger.info("User notification created for user: %s", user)

        # Log activity
        ActivityModel.objects.create(
            user=user,
            title="Create Ticket",
            description=f"Support ticket has been created for user: {user.first_name} {user.last_name}, issue: {category}"
        )
        logger.info("Activity logged for user: %s", user)

        # Serialize the created ticket
        serialized_ticket = self.get_serializer(ticket)

        resp = {
            "status": "success",
            "message": f"Support ticket created for {user.first_name} {user.last_name}, for {category} issues.",
            "data": serialized_ticket.data,
            "created_at": ticket.created_at,
        }
        logger.info("Response prepared successfully: %s", resp)
        return Response(data=resp, status=status.HTTP_201_CREATED)

    def upload_image(self, image_data):
        doc_image = cloud.upload(file=image_data)
        self.uploaded_doc_url = doc_image["url"]


class AssignTicket(generics.GenericAPIView):
    """
    AssignTicket handles Handles FIRST-TIME assignment of a support ticket to an agent
    """

    serializer_class = AssignTicketSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsSuperAdmin]

    def post(self, request, *args, **kwargs):
        logger.info("AssignTicket request received")

        authenticated_user = request.user

        payload = {
            k: v.strip() if isinstance(v, str) else v
            for k, v in request.data.items()
        }

        serializer = self.get_serializer(
            data=payload,
            context={"request": request}
        )
        serializer.is_valid(raise_exception=True)

        ticket_number = kwargs.get("ticket_number")
        pin = serializer.validated_data["pin"]

        ticket = Ticket.objects.filter(number=ticket_number).first()
        if not ticket:
            return Response(
                {"status": "fail", "message": "Ticket does not exist"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # ❗ Must be unassigned
        if ticket.assigned_to:
            return Response(
                {
                    "status": "fail",
                    "message": "Ticket already assigned. Use reassign endpoint."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not check_password(pin, authenticated_user.admin_pin):
            return Response(
                {"status": "fail", "error": "Incorrect pin"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        agent_email = serializer.validated_data["agent_email"]
        agent_role = serializer.validated_data["agent_role"]

        user = User.objects.filter(email=agent_email).first()
        if not user:
            return Response(
                {"status": "fail", "message": "Agent does not exist"},
                status=status.HTTP_404_NOT_FOUND,
            )

        is_agent = AccountType.objects.filter(
            user=user,
            user_type=agent_role
        ).exists()

        if not is_agent:
            raise PermissionDenied("User exists, but is not an agent.")

        ticket.assigned_to = user
        ticket.priority = serializer.validated_data["priority"]
        ticket.status = serializer.validated_data["status"]
        ticket.save()

        TicketAssignmentHistory.objects.create(
            ticket=ticket,
            assigned_by=authenticated_user,
            previous_agent=None,
            new_agent=user,
            priority=serializer.validated_data["priority"],
            reason=serializer.validated_data.get("reason"),
            action="assign",
        )

        ActivityModel.objects.create(
            user=authenticated_user,
            title="Assign Ticket",
            message=f"Ticket {ticket_number} assigned to {user.full_name}",
        )

        return Response(
            {
                "status": "success",
                "message": f"Ticket {ticket_number} successfully assigned to {user.full_name}",
                "data": serializer.data,
            },
            status=status.HTTP_201_CREATED,
        )


class ReassignTicket(generics.GenericAPIView):
    """
    ReassignTicket handles reassignment of a support ticket to a new agent.
    """

    serializer_class = AssignTicketSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsSuperAdmin]

    def post(self, request, *args, **kwargs):
        logger.info("ReassignTicket request received")

        authenticated_user = request.user

        payload = {
            k: v.strip() if isinstance(v, str) else v
            for k, v in request.data.items()
        }

        serializer = self.get_serializer(
            data=payload,
            context={"request": request}
        )
        serializer.is_valid(raise_exception=True)

        ticket_number = kwargs.get("ticket_number")
        pin = serializer.validated_data["pin"]

        ticket = Ticket.objects.filter(number=ticket_number).first()
        if not ticket:
            return Response(
                {"status": "fail", "message": "Ticket does not exist"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # ❗ Must already be assigned
        if not ticket.assigned_to:
            return Response(
                {
                    "status": "fail",
                    "message": "Ticket not yet assigned. Use assign endpoint."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not check_password(pin, authenticated_user.admin_pin):
            return Response(
                {"status": "fail", "error": "Incorrect pin"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        agent_email = serializer.validated_data["agent_email"]
        agent_role = serializer.validated_data["agent_role"]

        user = User.objects.filter(email=agent_email).first()
        if not user:
            return Response(
                {"status": "fail", "message": "Agent does not exist"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if ticket.assigned_to == user:
            return Response(
                {
                    "status": "fail",
                    "message": "Ticket is already assigned to this agent."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        is_agent = AccountType.objects.filter(
            user=user,
            user_type=agent_role
        ).exists()

        if not is_agent:
            raise PermissionDenied("User exists, but is not an agent.")

        previous_agent = ticket.assigned_to

        ticket.assigned_to = user
        ticket.priority = serializer.validated_data["priority"]
        ticket.status = serializer.validated_data["status"]
        ticket.save()

        TicketAssignmentHistory.objects.create(
            ticket=ticket,
            assigned_by=authenticated_user,
            previous_agent=previous_agent,
            new_agent=user,
            priority=serializer.validated_data["priority"],
            reason=serializer.validated_data.get("reason"),
            action="reassign",
        )

        ActivityModel.objects.create(
            user=authenticated_user,
            title="Reassign Ticket",
            message=f"Ticket {ticket_number} reassigned to {user.full_name}",
        )

        return Response(
            {
                "status": "success",
                "message": f"Ticket {ticket_number} successfully reassigned to {user.full_name}",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )


class UpdateTicketStatus(generics.GenericAPIView):
    """
    Handles updating ONLY the status of a support ticket.
    """

    serializer_class = UpdateTicketStatusSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsSuperAdmin]

    def post(self, request, *args, **kwargs):
        logger.info("UpdateTicketStatus request received")

        authenticated_user = request.user

        payload = {
            k: v.strip() if isinstance(v, str) else v
            for k, v in request.data.items()
        }

        serializer = self.get_serializer(data=payload)
        serializer.is_valid(raise_exception=True)

        ticket_number = kwargs.get("ticket_number")
        pin = serializer.validated_data["pin"]
        new_status = serializer.validated_data["status"]

        ticket = Ticket.objects.filter(number=ticket_number).first()
        if not ticket:
            return Response(
                {"status": "fail", "message": "Ticket does not exist"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not check_password(pin, authenticated_user.admin_pin):
            return Response(
                {"status": "fail", "error": "Incorrect pin"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        old_status = ticket.status

        # ❗ Prevent unnecessary updates
        if old_status == new_status:
            return Response(
                {
                    "status": "fail",
                    "message": f"Ticket is already in '{new_status}' status."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        ticket.status = new_status
        ticket.save(update_fields=["status"])

        # Activity log
        ActivityModel.objects.create(
            user=authenticated_user,
            title="Update Ticket Status",
            description=(
                f"Ticket {ticket_number} status changed "
                f"from '{old_status}' to '{new_status}'."
            ),
        )

        logger.info(
            "Ticket %s status updated from %s to %s by %s",
            ticket_number,
            old_status,
            new_status,
            authenticated_user.email,
        )

        return Response(
            {
                "status": "success",
                "message": f"Ticket {ticket_number} status updated successfully.",
                "data": {
                    "ticket_number": ticket_number,
                    "old_status": old_status,
                    "new_status": new_status,
                },
            },
            status=status.HTTP_200_OK,
        )


class EscalateTicketAPIView(APIView):
    serializer_class = TicketEscalateSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsManagerOrSuperAdmin, IsAgent]

    def post(self, request, ticket_id):
        serializer = TicketEscalateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        authenticated_user = request.user

        try:
            ticket = Ticket.objects.get(id=ticket_id)
        except Ticket.DoesNotExist:
            return Response(
                {"detail": "Ticket not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        to_user = User.objects.get(id=serializer.validated_data["to_user_id"])

        from_user = ticket.assigned_to
        from_role = ticket.agent_role
        to_role = serializer.validated_data["to_role"]
        pin = serializer.validated_data["pin"]
        if not check_password(pin, authenticated_user.admin_pin):
            return Response(
                {"status": "fail", "error": "Incorrect pin"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # 1️⃣ RR Trail (single source of truth)
        TicketRRTrail.objects.create(
            ticket=ticket,
            action="Escalated",
            from_user=from_user,
            to_user=to_user,
            from_role=from_role,
            to_role=to_role,
            reason=serializer.validated_data["reason"],
        )

        # 2️⃣ Update ticket
        ticket.assigned_to = to_user
        ticket.agent_role = to_role
        ticket.status = "Escalated"
        ticket.assigned_at = timezone.now()
        ticket.save(
            update_fields=["assigned_to", "agent_role", "status", "assigned_at"]
        )

        return Response(
            {"message": "Ticket escalated successfully"},
            status=status.HTTP_200_OK
        )


class TicketRRTrailAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsManagerOrSuperAdmin, IsAgent]

    def get(self, request, ticket_id):
        try:
            ticket = Ticket.objects.get(id=ticket_id)
        except Ticket.DoesNotExist:
            return Response(
                {"detail": "Ticket not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        trails = ticket.rr_trail.select_related(
            "from_user", "to_user"
        ).order_by("happened_at")

        data = []
        for trail in trails:
            data.append({
                "action": trail.action,
                "from_user": trail.from_user.full_name if trail.from_user else None,
                "to_user": trail.to_user.full_name if trail.to_user else None,
                "from_role": trail.from_role,
                "to_role": trail.to_role,
                "reason": trail.reason,
                "happened_at": trail.happened_at,
            })

        return Response(data, status=status.HTTP_200_OK)


class GetAllSupportTickets(generics.ListAPIView):
    """
    GetAllSupportTickets is the GET request handler that allows the SuperAdmin to
    retrieve all support tickets created.
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsSuperAdmin)
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
                    "ticket_number": ticket.number,
                    "authorised_by": "SuperAdmin",
                    "category": ticket.category,
                    "description": ticket.description,
                    "customer_email": ticket.customer_email,
                    "customer_name": ticket.customer_name,
                    "created_at": ticket.created_at,
                    "assigned_to": ticket.assigned_to,
                    "assigned_at": ticket.assigned_at,
                    "ticket_channel": ticket.channel,
                    "priority": ticket.priority,
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


class GetMyAssignedTickets(generics.ListAPIView):
    """
    Allows an admin to retrieve tickets assigned to them.
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)
    pagination_class = CustomPageNumberPagination

    def list(self, request, *args, **kwargs):
        logger.info(
            "Fetching tickets assigned to user %s", request.user.id
        )

        tickets = Ticket.objects.filter(
            assigned_to=request.user,
            deleted=False
        ).order_by("-created_at")

        paginator = self.pagination_class()
        paginated_tickets = paginator.paginate_queryset(tickets, request)

        data = [
            {
                "ticket_number": ticket.number,
                "authorised_by": request.user.full_name or request.user.phone_number,
                "category": ticket.category,
                "description": ticket.description,
                "created_at": ticket.created_at,
                "assigned_to": ticket.assigned_to.full_name if ticket.assigned_to else None,
                "assigned_at": ticket.assigned_at,
                "ticket_channel": ticket.channel,
                "priority": ticket.priority,
                "status": ticket.status,
            }
            for ticket in paginated_tickets
        ]

        response = {
            "status": "success",
            "message": "Assigned tickets fetched successfully!",
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

    lookup_field = "number"               # DB FIELD
    lookup_url_kwarg = "ticket_number"

    def retrieve(self, request, *args, **kwargs):
        print("🔥 VIEW HIT", kwargs)
        logger.info("Received request to retrieve support ticket.")

        ticket_id = kwargs.get("ticket_number")
        logger.debug("Attempting to retrieve ticket with ID: %s", ticket_id)

        try:
            ticket = (
                Ticket.objects
                .select_related("assigned_to")
                .prefetch_related("assignment_history")
                .get(number=ticket_id)
            )
            logger.info("Ticket found: %s", ticket)

            history = TicketAssignmentHistory.objects.filter(
                ticket=ticket
            ).order_by("created_at")

            history_data = TicketAssignmentHistorySerializer(
                history, many=True
            ).data

            response = {
                "status": "success",
                "message": "Support Ticket retrieved successfully!",
                "title": ticket.title,
                "data": {
                    "ticket_id": ticket_id,
                    "category": ticket.category,
                    "description": ticket.description,
                    "created_at": ticket.created_at,
                    "assigned_to": ticket.assigned_to.full_name if ticket.assigned_to else None,
                    "assigned_at": ticket.assigned_at,
                    "ticket_channel": ticket.channel,
                    "priority": ticket.priority,
                    "customer_email": ticket.customer_email,
                    "customer_name": ticket.customer_name,
                    "status": ticket.status,

                    # 🔥 NEW
                    "assignment_history": history_data,
                },
            }

            logger.info(
                "Ticket %s retrieved with %s assignment history records",
                ticket_id,
                len(history_data),
            )

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


class DeleteTicket(generics.DestroyAPIView):
    """
    DeleteTicket is the DELETE request handler that allows a SuperAdmin to
    delete a specific support ticket using its ticket_number.
    """

    queryset = Ticket.objects.all()
    serializer_class = CreateTicketSerializers
    permission_classes = [IsAuthenticated, IsSuperAdmin]
    authentication_classes = [JWTAuthentication]
    lookup_field = "number"  # This should match your model field
    lookup_url_kwarg = "ticket_number"  # This should match your URL parameter

    def destroy(self, request, *args, **kwargs):
        logger.info("Received request to delete support ticket.")

        ticket_number = kwargs.get("ticket_number")  # Get from URL kwargs
        logger.debug("Attempting to delete ticket with number: %s", ticket_number)

        try:
            ticket = Ticket.objects.get(number=ticket_number)  # Query using model field
            ticket.delete()
            logger.info("Ticket deleted successfully: %s", ticket_number)

            return Response(
                {
                    "status": "success",
                    "message": f"Support ticket with number {ticket_number} has been deleted.",
                },
                status=status.HTTP_204_NO_CONTENT,
            )

        except Ticket.DoesNotExist:
            logger.error("Ticket with number %s not found.", ticket_number)
            return Response(
                {"status": "fail", "message": "Ticket not found."},
                status=status.HTTP_404_NOT_FOUND,
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
    permission_classes = [IsAuthenticated, IsSuperAdmin]
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


class AddAgent(generics.CreateAPIView):
    """
    Add a new support agent(Agent or Moderator).
    Only Managers can create new support agents.
    If the user is successfully created, a JSON object containing the user's data is returned.
    If the user cannot be created, a 400 Bad Request or 403 Forbidden error is returned.
    """

    queryset = User.objects.all()
    serializer_class = AddAgentSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, IsManagerOrSuperAdmin]

    def post(self, request):
        try:
            # Log request initiation
            logger.info("Received request to add a new admin.")

            # Process payload
            payload = {
                key: value.strip() if isinstance(value, str) else value
                for key, value in request.data.items()
            }
            logger.debug(f"Processed payload: {payload}")

            pin = payload.get("pin")
            if not check_password(password=pin, encoded=request.user.admin_pin):
                return Response(
                    data={
                        "status": "fail",
                        "message": "Incorrect pin"
                    },
                    status=status.HTTP_401_UNAUTHORIZED
                )

            if not payload.get("email"):
                return Response(data={"status": "fail", "message": "Email field cannot be empty."}, status=status.HTTP_400_BAD_REQUEST)

            if not payload["role"]:
                return Response(data={"status": "fail", "message": "At least one role must be selected."}, status=status.HTTP_400_BAD_REQUEST)

            # Check if email exists
            if User.objects.filter(email=payload.get("email")).exists():
                logger.warning(
                    f"Attempt to create agent with existing email: {payload.get('email')}"
                )
                return Response(
                    data=(
                        {
                            "status": "fail",
                            "message": "A user with this email already exists.",
                        }
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Validate and save user
            serializer = AddAgentSerializer(data=payload)
            if serializer.is_valid(raise_exception=True):
                user = serializer.save()
                user_data = AddAgentSerializer(user).data
                logger.info(f"Support Agent created successfully: {user.email}")

                # Generate signup link
                signup_link = f"https://support.picadailys.com/sign-up?user_id={user.id}"

                name = user.full_name
                text_content = render_to_string(
                    template_name="empty_email.html",
                    context={
                        "custom_text": f"""
                            Dear {name},<br><br>
                            Your agent account has been created. Follow this
                            <a href="{signup_link}" style="color: #3498db; text-decoration: none;">
                                link
                            </a>
                            to complete your signup.<br><br>
                            If you have any questions, feel free to contact us at our support email or phone below.
                        """,
                        "support_email": "support@picadailys.com",
                        "picadailys_phone": [
                            "02012271894",
                            "02012271895",
                        ],
                    },
                )

                Messaging.send_email(
                    sender_email="notifications@picadailys.com",
                    body=f"Your agent account has been created. Follow this link to complete your signup: {signup_link}",
                    email=user.email,
                    html_content=text_content,
                    subject="Agent Registration",
                )

                # Prepare response
                resp = {
                    "status": "Success",
                    "message": "Created successfully, a link has been sent to your mail",
                    "user_id": user.id,
                    "data": user_data,
                }
                logger.info(f"Response prepared for user creation: {resp}")

                return Response(
                    data=resp,
                    status=status.HTTP_201_CREATED,
                )
        except ValidationError as e:
            logger.warning(f"Validation error: {e}")
            raise ValidationError(message=e, code=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"An unexpected error occurred: {e}")
            error_message = str(e)
            return Response(
                data={"status": "Error", "message": f"An unexpected erroroccurred: {error_message}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class AgentSignUpComplete(generics.UpdateAPIView):
    """
    AgentSignUpComplete is a POST request that handles the support agent signup completion.
    """

    serializer_class = AddAgentContdSerializer
    permission_classes = [AllowAny]

    def get_object(self):
        user_id = self.kwargs.get("user_id")  # Make sure this matches your URL pattern
        logger.debug("Getting object for user ID: %s", user_id)

        try:
            user = User.objects.get(id=user_id)
            agent_types = [
                "Agent",
                "Moderator",
            ]
            is_agent = AccountType.objects.filter(
                user=user, user_type__in=agent_types
            ).exists()

            if not is_agent:
                logger.warning("User %s exists but is not an agent.", user_id)
                return None  # Return None instead of raising exception

            return user

        except User.DoesNotExist:
            logger.warning("User with ID %s not found.", user_id)
            return None

    def update(self, request, *args, **kwargs):
        user_id = kwargs.get("user_id")  # Match the parameter name with get_object()
        logger.info("Update request received for user ID: %s", user_id)

        instance = self.get_object()
        if instance is None:
            logger.warning("User with ID %s not found or not authorized.", user_id)
            return Response(
                data={"status": "fail", "message": "User not found or not authorized."}, 
                status=status.HTTP_404_NOT_FOUND
            )

        payload = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in request.data.items()
        }
        logger.debug("Payload for update: %s", payload)

        serializer = self.get_serializer(instance=instance, data=payload)

        try:
            if serializer.is_valid(raise_exception=True):
                user = serializer.save()  # The serializer handles password hashing
                user.is_verified = True
                user.save()

                ActivityModel.objects.create(
                    user=user,
                    title="Admin Complete Signup.",
                    description=f"Support agent {instance.full_name} completed signup.",
                )
                logger.info(
                    "Support agent registration completed successfully for user ID: %s", user_id
                )
                return Response(
                    data={
                        "status": "success",
                        "message": "Support Agent signup completed successfully.",
                        "data": serializer.data,
                    },
                    status=status.HTTP_200_OK,
                )
        except serializers.ValidationError as e:
            logger.error("Validation error for user ID %s: %s", user_id, e)
            return Response(
                data={"status": "fail", "message": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            logger.error("Unexpected error for user ID %s: %s", user_id, str(e))
            return Response(
                data={"status": "fail", "message": "An unexpected error occurred."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class SupportPhoneVerifyOTP(generics.GenericAPIView):
    """
    SupportPhoneVerifyOTP handles the POST request of verifying a
    registered Manager with valid phone number.
    """

    permission_classes = (AllowAny,)
    serializer_class = SupportVerifyOTPSerializer

    def post(self, request):
        user_data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in request.data.items()
        }
        logger.debug("Received user data for OTP verification: %s", user_data)

        serializer = self.serializer_class(data=user_data)
        if serializer.is_valid(raise_exception=True):
            received_otp = serializer.data["otp"]
            logger.info("OTP received: %s", received_otp)

            # Validate OTP
            user_id = otp_manager.validate_user_otp(received_otp)
            if not user_id:
                logger.warning("Invalid or expired OTP: %s", received_otp)
                return Response(
                    data={
                        "status": "fail", "message": "Invalid or expired OTP"
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                logger.error("Manager with id %s does not exist.", user_id)
                return Response(
                    data={"status": "fail", "message": "Manager not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Send welcome message to user
            msg = "Welcome to Picadailys Support... You are registration as the support manager was successful!."
            recipient = user.phone_number[1:]

            Messaging.send_sms(phone_number=recipient, msg=msg)
            logger.info("Welcome message sent to user %s at %s", user.id, recipient)

            # Render the template with values
            text_content = render_to_string(
                template_name="empty_email.html",
                context={
                    "custom_text": f"Dear {user.first_name},<br><br>{msg}.",
                    "support_email": "support@picadailys.com",
                    "picadailys_phone": [
                        "02012271894",
                        "02012271895",
                    ],
                },
            )

            Messaging.send_email(
                sender_email="notifications@picadailys.com",
                body=msg,
                email=user.email,
                html_content=text_content,
                subject="Welcome To Picadailys Support",
            )

            # Update user verification status
            user.is_verified = True
            user.is_active = True
            user.save()
            logger.info("Support Manager with Id: %s has been verified and activated.", user.id)

            # Log activity
            ActivityModel.objects.create(
                user=user,
                title="Verify Account",
                description=f"{user.first_name} {user.last_name} verified OTP after registration.",
            )
            logger.info("Activity logged for user %s verification.", user.id)

            response = {"status": "success", "message": "Account is verified"}
            return Response(data=response, status=status.HTTP_200_OK)
        else:
            logger.error(
                "Serializer validation failed with errors: %s", serializer.errors
            )
            return Response(
                data=serializer.errors, status=status.HTTP_400_BAD_REQUEST
            )


class LoginAgent(APIView):
    """LoginAPIView handles the POST request of logging in
    a verified user with valid login credentials.
    """

    serializer_class = SupportAgentLoginSerializers

    def post(self, request):
        data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in request.data.items()
        }
        email = data.get("email")
        password = data.get("password")

        try:
            # Retrieve the user by email to get the phone number
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            logger.warning(f"Login attempt failed: User with email {email} not found.")
            return Response(
                data={"status": "fail", "message": "Invalid credentials"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # Authenticate using the phone number and password
        user = authenticate(phone_number=user.phone_number, password=password)

        if user:
            logger.info(f"User {user.email} authenticated successfully.")

            # Check if the user has more than two devices registered
            existing_device_count = DeviceId.objects.filter(user=user).count()
            if existing_device_count >= 2:
                if existing_device_count == 3:
                    oldest_device = DeviceId.objects.filter(user=user).earliest(
                        "created_at"
                    )
                    oldest_device.delete()
                    logger.info(
                        f"Device limit exceeded for user {user.email}. Oldest device deleted."
                    )

                return Response(
                    data={"status": "fail", "message": "Agent cannot login on more than two devices, oldest device ID deleted."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if not user.is_verified:
                logger.warning(
                    f"User {user.email} is not verified. Login attempt blocked."
                )
                return Response(
                    data={"status": "fail", "message": "Please verify your account to login"},
                    status=status.HTTP_401_UNAUTHORIZED,
                )

            logger.info(f"User {user.email} successfully logged in.")

            user_name = (
                "Manager"
                if user.active_role == "Manager"
                else "SuperAdmin"
                if user.active_role == "SuperAdmin"
                else user.full_name
                if user.active_role
                in {
                    "Moderator",
                    "Agent",
                }
                else "Unknown"
            )

            UserNotification.objects.create(
                user=user, title="Login.", message="Login successful."
            )
            ActivityModel.objects.create(
                user=user,
                title="Agent Login.",
                description=f"Support Agent, {user_name} logged in.",
            )

            # Get user roles
            user_roles = AccountType.objects.filter(user=user).values_list(
                "user_type", flat=True
            )
            tokens = create_jwt_pair_for_user(user)

            # Assign a role if active_role is None
            if user.active_role is None and user_roles:
                user.active_role = user_roles[0]

            user_details = {
                "id": user.id,
                "email": user.email,
                "image": user.profile_img_url,
                "phone_number": user.phone_number,
                "full_name": user.full_name,
                "is_verified": user.is_verified,
                "is_admin_pin_set": user.is_admin_pin_set,
                "roles": list(user_roles),
            }
            user.last_login = timezone.now()
            user.save()

            response = {
                "status": "success",
                "message": "Login successful",
                "tokens": tokens,
                "user_data": user_details,
            }
            return Response(data=response, status=status.HTTP_200_OK)
        else:
            logger.warning(
                f"Login attempt failed for user with email {email}. Invalid credentials."
            )
            return Response(
                data={"status": "fail", "message": "Invalid credentials"},
                status=status.HTTP_401_UNAUTHORIZED,
            )


class SetAgentPin(generics.CreateAPIView):
    """
    SetAgentPin handles the POST request of creating a pin for a support agent.
    """

    serializer_class = CreateAgentPinSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsAgent)

    def perform_create(self, serializer, request):
        pin = request.data.get("pin")
        user = request.user
        logger.info(f"Creating admin pin for user: {user.full_name}.")

        if not pin:
            logger.warning(
                f"No pin provided for user: {user.full_name}."
            )
            return Response(
                data={"status": "fail", "message": "Pin is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Hash the pin using make_password.
        hashed_pin = make_password(pin)
        logger.debug(
            "Hashed pin for user %s: %s", user.full_name, hashed_pin
        )

        # Save the hashed pin in the authenticated user's admin_pin field.
        authenticated_user = self.request.user
        authenticated_user.admin_pin = hashed_pin
        authenticated_user.is_admin_pin_set = True
        authenticated_user.save()
        logger.info("Agent pin set for user: %s %s", user.full_name)

        # Create a user notification
        UserNotification.objects.create(
            user=authenticated_user,
            title="Agent Pin",
            message="Agent pin created successfully.",
        )
        logger.info(
            "User  notification created for user: %s %s",
            user.full_name,
        )

    def create(self, request, *args, **kwargs):
        user_data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in request.data.items()
        }
        logger.info("Create request received with data: %s", user_data)

        serializer = self.serializer_class(data=user_data)
        if serializer.is_valid(raise_exception=True):
            self.perform_create(serializer, request)
            response = {
                "status": "success",
                "message": "Agent pin created successfully!",
            }
            logger.info(
                "Admin pin created successfully for user: %s",
                request.user.full_name,
            )
            return Response(data=response, status=status.HTTP_201_CREATED)
        else:
            logger.error("Validation errors occurred: %s", serializer.errors)
            return Response(
                data={"status": "fail", "message": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )


class GetAllAgentAndModeratorUsers(generics.ListAPIView):
    """
    GET request to retrieve the count and list of users with user_type 'Agent' or 'Moderator'.
    """

    queryset = User.objects.all()
    serializer_class = ListAgentAndModeratorSerializer  # You may rename if needed
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsSuperAdmin)
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        logger.info("Retrieving agent and moderator users.")
        users = (
            User.objects.filter(
                account_types__user_type__in=["Agent", "Moderator"]
            )
            .distinct()
            .order_by("account_types__created_at")
        )
        logger.info("Agent and moderator users retrieved successfully.")
        return users

    def list(self, request, *args, **kwargs):
        logger.info("Accessing agent and moderator users list view.")
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)

        # Count Agent and Moderator users
        agent_count = queryset.filter(account_types__user_type="Agent").count()
        moderator_count = queryset.filter(account_types__user_type="Moderator").count()

        response_data = {
            "status": "success",
            "message": "Agent and moderator users retrieved successfully"
            if queryset.exists()
            else "No agent or moderator users found.",
            "num_of_users": queryset.count(),
            "num_of_agents": agent_count,
            "num_of_moderators": moderator_count,
            "users": [],
        }

        if page is not None:
            serialized_users = self.get_serializer(page, many=True)
            response_data["users"] = serialized_users.data
        else:
            logger.warning("No users found for pagination.")

        return Response(data=response_data, status=status.HTTP_200_OK)
