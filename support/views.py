import logging

from django.db import transaction
from django.contrib.auth.hashers import check_password
from django.db.models import Avg, Count, Case, When, IntegerField
from django.contrib.auth.hashers import make_password
from django.core.exceptions import PermissionDenied
from django.contrib.auth import authenticate
from django.core.exceptions import ValidationError
from django.template.loader import render_to_string
from django.utils import timezone
from django.db.models import Q

from cloudinary import uploader as cloud

# In project imports.
from .serializers import (
    RegisterAgentManagerSerializer, SupportVerifyOTPSerializer,
    CreateTicketSerializers, AssignTicketSerializers,
    AgentRatingSerializers, TicketSerializers, TicketEscalateSerializer,
    AddAgentSerializer, AddAgentContdSerializer, SupportAgentLoginSerializers,
    CreateAgentPinSerializer, ListAgentModeratorAndManagerSerializer,
    TicketAssignmentHistorySerializer, UpdateTicketStatusSerializer,
    DisableAgentSerializer, EnableAgentSerializer, AgentDeletionSerializer,
    UserProfileSerializer, CompleteTicketSerializer, ForgotPinSerializer,
    VerifyOTPSerializer, ResetPinSerializer, SupportStaffForgotPasswordSerializer,
    SupportStaffPasswordResendOTPSerializer, SupportStaffResetPasswordSerializer
    
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
    IsManagerModeratorOrSuperAdmin, IsManagerOrSuperAdmin, IsAgent
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
    throttle_classes = []

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

                text_content = render_to_string(
                    template_name="empty_email.html",
                    context={
                        "custom_text": f"Dear {current_user.full_name},<br><br>{msg}.",
                        "support_email": "support@picadailys.com",
                        "picadailys_phone":
                            "02012271894  02012271895",
                    },
                )

                Messaging.send_email(
                    email=current_user.email,
                    html_content=text_content,
                    subject="Welcome to Picadailys Support - OTP for Manager Registration",
                    sender_email="notifications@picadailys.com",
                    body=f"Welcome Manager! This is a one-time signup. To protect your account, please enter this {otp}.",
                )
                logger.info(f"OTP sent: {otp}")
                logger.info(f"OTP sent to email: {current_user.email}")

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


class AgentForgotPin(generics.GenericAPIView):
    """
    AgentForgotPin handles the POST request of sending a
    forgot pin request for an agent user.
    """

    serializer_class = ForgotPinSerializer
    throttle_classes = []

    def post(self, request):
        payload = request.data
        user_data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in payload.items()
        }
        serializer = self.serializer_class(data=user_data)
        if not serializer.is_valid(raise_exception=True):
            return Response(
                data=serializer.errors, status=status.HTTP_400_BAD_REQUEST
            )

        email = user_data.get("email")
        try:
            user = User.objects.get(email=email)
            logger.info(f"User found for email: {user.email}")
        except User.DoesNotExist:
            logger.warning(f"No agent found with email: {email}")
            response = {
                "status": "fail",
                "detail": "An agent with this email does not exist",
            }
            return Response(
                data=response,
                status=status.HTTP_404_NOT_FOUND,
            )

        user_id = user.id
        otp = otp_manager.create_otp(user_id=str(user_id))
        msg = f"Enter this {otp} to verify your account and reset your pin"

        text_content = render_to_string(
            template_name="empty_email.html",
            context={
                "custom_text": f"Dear {user.full_name},<br><br>{msg}.",
                "support_email": "support@picadailys.com",
                "picadailys_phone": [
                    "02012271894",
                    "02012271895",
                ],
            },
        )

        Messaging.send_email(
            email=email,
            html_content=text_content,
            subject="Agent Pin Reset",
            sender_email="notifications@picadailys.com",
            body="You have requested a pin reset. Please use the OTP sent to your email to proceed.",
        )
        logger.info(f"OTP sent: {otp}")
        logger.info(f"OTP sent to email: {email}")

        ActivityModel.objects.create(
            user=user,
            title="Agent Pin Reset Request",
            description=f"Agent {user.full_name} submitted a pin reset request.",
        )

        response = {
            "status": "success",
            "message": "Check your mailbox for an OTP",
        }
        return Response(data=response, status=status.HTTP_201_CREATED)


class AgentPinVerifyOTP(generics.GenericAPIView):
    """
    AgentPinVerifyOTP handles the POST request of verifying an agent
    user with valid email for pin reset.
    """

    permission_classes = (AllowAny,)
    serializer_class = VerifyOTPSerializer
    throttle_classes = []

    def post(self, request):
        payload = request.data
        user_data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in payload.items()
        }
        logger.debug("Received data for pin reset OTP verification: %s", user_data)

        serializer = self.serializer_class(data=user_data)

        # Validate incoming data with serializer class.
        if not serializer.is_valid(raise_exception=True):
            logger.error(
                "Serializer validation failed with errors: %s", serializer.errors
            )
            return Response(
                data=serializer.errors, status=status.HTTP_400_BAD_REQUEST
            )

        received_otp = serializer.data["otp"]
        logger.info("OTP received for pin reset: %s", received_otp)

        # Validate OTP
        user_id = otp_manager.validate_user_otp(received_otp)
        if not user_id:
            logger.warning("Invalid or expired OTP during pin reset: %s", received_otp)
            return Response(
                data={"status": "fail", "message": "Invalid or expired OTP"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            logger.error(
                "Support agent with id %s not found for pin reset verification.",
                user_id,
            )
            return Response(
                data={"status": "fail", "message": "Support agent not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Send confirmation message to the user
        msg = "Your account is verified... You can reset your pin now!"

        text_content = render_to_string(
            template_name="empty_email.html",
            context={
                "custom_text": f"Dear {user.full_name},<br><br>{msg}.",
                "support_email": "support@picadailys.com",
                "picadailys_phone": "02012271894  02012271895",
            },
        )

        Messaging.send_email(
            email=user.email,
            html_content=text_content,
            subject="Agent Verify OTP",
            sender_email="notifications@picadailys.com",
            body="Your OTP has been verified. You can now proceed to reset your pin.",
        )

        full_name = (
            user.full_name
            or f"{user.first_name or ''} {user.last_name or ''}".strip()
            or user.phone_number
            or user.email
        )

        # Log activity for verification
        ActivityModel.objects.create(
            user=user,
            title="Verify Account",
            description=f"{full_name} verified OTP for pin reset.",
        )
        logger.info(
            "Pin reset OTP verification activity logged for admin user %s.", user.id
        )

        verified_response = {
            "status": "success",
            "message": "Account is verified",
            "user_id": user_id,
        }
        return Response(data=verified_response, status=status.HTTP_200_OK)


class AgentResetPin(generics.CreateAPIView):
    serializer_class = ResetPinSerializer
    throttle_classes = []

    def create(self, request):
        payload = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in request.data.items()
        }
        serializer = self.get_serializer(data=payload)
        if not serializer.is_valid(raise_exception=True):
            return Response(
                data=serializer.errors, status=status.HTTP_400_BAD_REQUEST
            )

        user_data = serializer.validated_data
        agent_id = payload.get("agent_id")

        try:
            user = User.objects.get(id=agent_id)
            logger.info(f"User found for ID: {user.id}")
        except User.DoesNotExist:
            logger.error(f"Support agent not found with ID: {agent_id}")
            return Response(
                data={"status": "fail", "message": "Support agent not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if user_data.get("pin") != user_data.get("pin2"):
            logger.warning("Pins do not match for Agent ID: %s", agent_id)
            return Response(
                data={"status": "fail", "message": "Pins do not match!"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        password = user_data.get("pin")
        user.agent_pin = make_password(password)

        user_token = payload.get("refresh_token")
        if user_token:
            token = RefreshToken(user_token)
            token.blacklist()
            logger.info(f"Refresh token blacklisted for user: {agent_id}")

        user.save()

        full_name = (
            user.full_name
            or f"{user.first_name or ''} {user.last_name or ''}".strip()
            or user.phone_number
            or user.email
        )

        ActivityModel.objects.create(
            user=user,
            title="Agent Pin Reset.",
            description=f"{full_name} reset their pin.",
        )

        response = {"status": "success", "message": "Pin reset successfully"}
        return Response(data=response, status=status.HTTP_200_OK)


class SupportForgotPassword(generics.GenericAPIView):

    serializer_class = SupportStaffForgotPasswordSerializer
    throttle_scope = "password_change"

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response(
                data={
                    "status": "success",
                    "message": "If this account exists, an OTP has been sent."
                },
                status=status.HTTP_200_OK
            )

        # Restrict to staff roles only
        if not user.account_types.filter(
            user_type__in=["Moderator", "Manager", "Agent"]
        ).exists():

            return Response(
                data={
                    "status": "fail",
                    "message": "This account is not authorized for staff portal."
                },
                status=status.HTTP_403_FORBIDDEN
            )

        user_id = user.id
        otp = otp_manager.create_otp(user_id=str(user_id))
        msg = f"Enter this {otp} to verify your account and reset your login password"

        text_content = render_to_string(
            template_name="empty_email.html",
            context={
                "custom_text": f"Dear {user.full_name},<br><br>{msg}.",
                "support_email": "support@picadailys.com",
                "picadailys_phone": "02012271894 02012271895",
            },
        )

        Messaging.send_email(
            email=email,
            html_content=text_content,
            subject="Support Password Reset Request",
            sender_email="notifications@picadailys.com",
            body="You have requested a password reset. Please use the OTP sent to your email to proceed.",
        )
        # TODO: Consider sending OTP to phone as well if phone number is
        # available for added security and convenience.
        logger.info(f"OTP sent: {otp}")
        logger.info(f"OTP sent to email: {email}")

        ActivityModel.objects.create(
            user=user,
            title="Admin Password Reset Request",
            description=f"{user.full_name} submitted a password reset request.",
        )

        response = {
            "status": "success",
            "message": "Check your mailbox for an OTP",
        }
        return Response(data=response, status=status.HTTP_201_CREATED)


class SupportPasswordResendOTP(generics.GenericAPIView):
    """
    StaffPasswordResendOTP handles the POST request of resending an
    OTP to a support agent after password reset.
    """

    permission_classes = (AllowAny,)
    serializer_class = SupportStaffPasswordResendOTPSerializer

    def post(self, request):
        logger.debug("Received OTP resend request data: %s", request.data)

        user_data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in request.data.items()
        }
        serializer = self.serializer_class(data=user_data)

        if serializer.is_valid(raise_exception=True):
            email = serializer.data["email"]
            logger.info("Processing OTP resend for email: %s", email)

            try:
                user = User.objects.get(email=email)
                logger.info("User found with email: %s", email)

                # Generate OTP using the user's ID
                otp = otp_manager.create_otp(user_id=str(user.id))
                msg = msg = f"Enter this {otp} to verify your account and reset your login password"

                text_content = render_to_string(
                    template_name="empty_email.html",
                    context={
                        "custom_text": f"Dear {user.full_name},<br><br>{msg}.",
                        "support_email": "support@picadailys.com",
                        "picadailys_phone": "02012271894 02012271895",
                    },
                )

                Messaging.send_email(
                    email=email,
                    html_content=text_content,
                    subject="Admin Password Reset Request",
                    sender_email="notifications@picadailys.com",
                    body="You have requested a password reset. Please use the OTP sent to your email to proceed.",
                )

                response = {
                    "status": "success",
                    "message": "OTP resent successfully. Check your phone for validation.",
                }
                return Response(data=response, status=status.HTTP_200_OK)

            except User.DoesNotExist:
                logger.warning(
                    "Agent with email %s does not exist.", email
                )
                resp = {
                    "status": "fail",
                    "message": "Agent with the provided email does not exist.",
                }
                return Response(
                    data=resp,
                    status=status.HTTP_404_NOT_FOUND,
                )

        else:
            logger.error("OTP resend validation failed: %s", serializer.errors)
            return Response(
                data=serializer.errors, status=status.HTTP_400_BAD_REQUEST
            )

class SupportEmailVerifyOTP(generics.GenericAPIView):
    """
    SupportEmailVerifyOTP handles the POST request of verifying a
    support agent with a valid email address for password reset.
    """

    permission_classes = (AllowAny,)
    serializer_class = VerifyOTPSerializer

    def post(self, request):
        user_data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in request.data.items()
        }
        logger.debug("Received data for password reset OTP verification: %s", user_data)

        serializer = self.serializer_class(data=user_data)
        if serializer.is_valid(raise_exception=True):
            received_otp = serializer.data["otp"]
            logger.info("OTP received for password reset: %s", received_otp)

            # Validate OTP
            user_id = otp_manager.validate_user_otp(received_otp)
            if not user_id:
                logger.warning(
                    "Invalid or expired OTP during password reset: %s", received_otp
                )
                return Response(
                    data={"status": "fail", "message": "Invalid or expired OTP"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                logger.error(
                    "Agent with id %s not found for password reset verification.",
                    user_id,
                )
                return Response(
                    data={"status": "fail", "message": "Admin not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Send confirmation message to the user
            msg = "Agent is verified... You can reset your password now!"
            recipient = user.email
            text_content = render_to_string(
                template_name="empty_email.html",
                context={
                    "custom_text": f"Dear {user.full_name},<br><br>{msg}.",
                    "support_email": "support@picadailys.com",
                    "picadailys_phone": "02012271894 02012271895",
                },
            )

            Messaging.send_email(
                email=recipient,
                html_content=text_content,
                subject="Verify OTP",
                sender_email="notifications@picadailys.com",
                body=msg,
            )
            logger.info(
                "Password reset verification message sent to admin %s at %s",
                user.id,
                recipient,
            )

            # Log activity for verification
            ActivityModel.objects.create(
                user=user,
                title="Verify Account",
                description=f"{user.full_name} verified OTP for password reset.",
            )
            logger.info(
                "Password reset OTP verification activity logged for user %s.", user.id
            )

            verified_response = {
                "status": "success",
                "message": "Account is verified",
                "user_id": user_id,
            }
            return Response(data=verified_response, status=status.HTTP_200_OK)
        else:
            logger.error(
                "Serializer validation failed with errors: %s", serializer.errors
            )
            return Response(
                data=serializer.errors, status=status.HTTP_400_BAD_REQUEST
            )


class SupportfResetPassword(generics.CreateAPIView):
    serializer_class = SupportStaffResetPasswordSerializer

    def create(self, request):
        payload = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in request.data.items()
        }
        serializer = self.get_serializer(data=payload)
        if not serializer.is_valid(raise_exception=True):
            return Response(
                data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST
            )

        user_data = serializer.validated_data
        user_id = payload.get("agent_id")

        try:
            user = User.objects.get(id=user_id)
            logger.info(f"Agent found for ID: {user.id}")
        except User.DoesNotExist:
            logger.error(f"Agent not found with ID: {user_id}")
            return Response(
                data=encrypt({"error": "Agent not found"}),
                status=status.HTTP_404_NOT_FOUND,
            )

        if user_data["password"] != user_data["password2"]:
            logger.warning("Passwords do not match for agent ID: %s", user_id)
            return Response(
                data=encrypt({"error": "Passwords do not match!"}),
                status=status.HTTP_400_BAD_REQUEST,
            )

        password = user_data["password"]
        user.password = make_password(password)

        user_token = payload.get("refresh_token")
        if user_token:
            token = RefreshToken(user_token)
            token.blacklist()
            logger.info(f"Refresh token blacklisted for user: {user_id}")

        user.save()

        UserNotification.objects.create(
            user=user,
            title="Password Reset.",
            message="Your password reset is successful.",
        )

        ActivityModel.objects.create(
            user=user,
            title="Password Reset.",
            description=f"{user.full_name} reset their password.",
        )

        response = {"status": "success", "message": "Password reset successfully"}
        return Response(data=response, status=status.HTTP_200_OK)



class ListUserDetailsAPI(generics.ListAPIView):
    """
    ListUserDetailsAPI handles the GET request to list all agents and moderators.
    """
    serializer_class = UserProfileSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, IsManagerOrSuperAdmin]
    throttle_classes = []

    def get_queryset(self):
        users = User.objects.all()
        return users

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)

            response = {
                "count": self.paginator.page.paginator.count,
                "next": self.paginator.get_next_link(),
                "previous": self.paginator.get_previous_link(),
                "results": serializer.data,
            }

            return Response(data=response, status=status.HTTP_200_OK)

        serializer = self.get_serializer(queryset, many=True)
        return Response(data=serializer.data, status=status.HTTP_200_OK)
    

class CreateTicket(generics.CreateAPIView):
    """
    CreateTicket handles the POST request of logging an issue for
    a customer and generating a ticket.
    """
    serializer_class = CreateTicketSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, IsManagerModeratorOrSuperAdmin]
    parser_classes = (
        MultiPartParser,
        JSONParser,
    )
    throttle_classes = []

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
        customer_phone_number = payload.get("customer_phone_number")
        # Allow client to provide either `customer_email` or `email`.
        customer_email = payload.get("customer_email") or user_email
        attachment = request.FILES.get("attachment")
        title = payload.get("title")
        priority = payload.get("priority")
        pin = payload.get("pin")

        attachment_url = None

        if not check_password(password=pin, encoded=request.user.agent_pin):
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
            customer_phone_number=customer_phone_number,
            title=title,
            category=category,
            channel=channel,
            description=description,
            attachments=attachment_url,
            priority=priority,
            status="New",
        )

        # Ensure a readable ticket number is generated (use helper)
        try:
            ticket.number = generate_ticket_number()
            ticket.save(update_fields=["number"])
        except Exception:
            # In case generating/saving number fails, keep ticket but log
            logger.exception("Failed to generate/save ticket number for ticket %s", ticket.id)

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

        display_name = customer_name or f"{user.first_name or ''} {user.last_name or ''}".strip() or user.email

        resp = {
            "status": "success",
            "message": f"Support ticket created for {display_name}, for {category} issues.",
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
    permission_classes = [IsAuthenticated, IsManagerModeratorOrSuperAdmin]
    throttle_classes = []

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

        ticket_number = kwargs.get("ticket_number") or kwargs.get("ticket_id")
        pin = serializer.validated_data["pin"]

        ticket = Ticket.objects.filter(number=ticket_number).first()
        if not ticket:
            return Response(
                {"status": "fail", "message": "Ticket does not exist"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Must be unassigned
        if ticket.assigned_to:
            return Response(
                {
                    "status": "fail",
                    "message": "Ticket already assigned. Use reassign resource endpoint."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not check_password(pin, authenticated_user.agent_pin):
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

        allowed_roles = ["Agent", "Manager", "Moderator"]

        is_valid_role = AccountType.objects.filter(
            user=user,
            user_type__in=allowed_roles
        ).exists()

        if not is_valid_role:
            raise PermissionDenied("User exists, but is not allowed to be assigned tickets.")

        ticket.assigned_to = user
        ticket.priority = serializer.validated_data.get("priority")
        ticket.assigned_at = timezone.now()

        # Only update status if provided
        if "status" in serializer.validated_data:
            ticket.status = serializer.validated_data["status"]

        ticket.save()

        TicketAssignmentHistory.objects.create(
            ticket=ticket,
            assigned_by=authenticated_user,
            previous_agent=None,
            new_agent=user,
            priority=serializer.validated_data.get("priority"),
            reason=serializer.validated_data.get("reason"),
            action="assign",
        )

        ActivityModel.objects.create(
            user=authenticated_user,
            title="Assign Ticket",
            description=f"Ticket {ticket_number} assigned to {user.full_name}",
        )

        return Response(
            {
                "status": "success",
                "message": f"Ticket {ticket_number} successfully assigned to {agent_role}, {user.full_name}",
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
    permission_classes = [IsAuthenticated, IsManagerModeratorOrSuperAdmin]
    throttle_classes = []

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

        if not check_password(pin, authenticated_user.agent_pin):
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
            description=f"Ticket {ticket_number} reassigned to {user.full_name}",
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
    permission_classes = [IsAuthenticated, IsAgent]
    throttle_classes = []

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

        if not check_password(pin, authenticated_user.agent_pin):
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
    permission_classes = [IsAuthenticated, IsAgent]
    throttle_classes = []

    def post(self, request, *args, **kwargs):
        serializer = TicketEscalateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        authenticated_user = request.user

        ticket_number = kwargs.get("ticket_number")
        ticket = Ticket.objects.filter(number=ticket_number).first()
        if not ticket:
            return Response(
                {"detail": "Ticket not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        to_user = User.objects.get(id=serializer.validated_data["to_user_id"])
        to_role = serializer.validated_data["to_role"]

        allowed_escalation_roles = ["Moderator", "Manager"]
        if to_role not in allowed_escalation_roles:
            return Response(
                {"status": "fail", "error": "You cannot only escalate tickets to Moderators."},
                status=status.HTTP_403_FORBIDDEN,
            )

        from_user = ticket.assigned_to
        from_role = ticket.agent_role

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
            {"status": "success", "message": "Ticket escalated successfully"},
            status=status.HTTP_200_OK
        )


class TicketRRTrailAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, IsAgent]
    throttle_classes = []

    def get(self, request, *args, **kwargs):
        ticket_id = kwargs.get("ticket_number")

        try:
            # Try to parse as UUID first, then fall back to ticket number
            import uuid
            ticket = None
            try:
                param_uuid = uuid.UUID(str(ticket_id))
                ticket = Ticket.objects.filter(id=param_uuid).first()
            except (ValueError, TypeError):
                # Not a UUID, try as ticket number
                ticket = Ticket.objects.filter(number=ticket_id).first()

            if not ticket:
                return Response(
                    {"detail": "Ticket not found"},
                    status=status.HTTP_404_NOT_FOUND
                )

            trails = TicketAssignmentHistory.objects.filter(
                ticket=ticket
            ).select_related(
                "assigned_by", "previous_agent", "new_agent"
            ).order_by("created_at")

            data = []
            for trail in trails:
                data.append({
                    "action": getattr(trail, "action", None),
                    "assigned_by": getattr(getattr(trail, "assigned_by", None), "full_name", None),
                    "previous_agent": getattr(getattr(trail, "previous_agent", None), "full_name", None),
                    "new_agent": getattr(getattr(trail, "new_agent", None), "full_name", None),
                    "priority": getattr(trail, "priority", None),
                    "reason": getattr(trail, "reason", None),
                    "happened_at": getattr(trail, "created_at", None),
                })

            return Response(
                {
                    "ticket_id": str(ticket.id),
                    "ticket_number": ticket.number,
                    "history_count": trails.count(),
                    "history": data,
                },
                status=status.HTTP_200_OK,
            )
        except Exception as exc:
            logger.exception("Error while fetching RR trail for ticket_id %s: %s", ticket_id, exc)
            return Response(
                {"status": "fail", "message": "Unable to fetch ticket RR trail."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class GetAllSupportTickets(generics.ListAPIView):
    """
    GetAllSupportTickets is the GET request handler that allows the SuperAdmin to
    retrieve all support tickets created.
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, IsManagerModeratorOrSuperAdmin]
    pagination_class = CustomPageNumberPagination
    throttle_classes = []

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
                    "title": ticket.title,
                    "authorised_by": "SuperAdmin",
                    "category": ticket.category,
                    "description": ticket.description,
                    "customer_email": ticket.customer_email,
                    "customer_name": ticket.customer_name,
                    "customer_phone_number": ticket.customer_phone_number,
                    "created_at": ticket.created_at,
                    "assigned_to": {
                        "id": ticket.assigned_to.id if ticket.assigned_to else None,
                        "full_name": ticket.assigned_to.full_name if ticket.assigned_to else None,
                        "email": ticket.assigned_to.email if ticket.assigned_to else None,
                    },
                    "assigned_at": ticket.assigned_at,
                    "resolution_hours": ticket.resolution_hours,
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
    permission_classes = [IsAuthenticated, IsAgent]
    pagination_class = CustomPageNumberPagination
    throttle_classes = []

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
                "customer_info":{
                    "name": ticket.customer_name,
                    "email": ticket.customer_email,
                    "phone_number": ticket.customer_phone_number
                },
                "assigned_at": ticket.assigned_at,
                "resolution_hours": ticket.resolution_hours,
                "remaining_hours": ticket.remaining_time,
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
    permission_classes = [IsAuthenticated, IsAgent]
    authentication_classes = [JWTAuthentication]
    throttle_classes = []

    lookup_field = "number"
    lookup_url_kwarg = "ticket_number"

    def retrieve(self, request, *args, **kwargs):
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

            if not ticket.opened_at:
                ticket.opened_at = timezone.now()
                ticket.resolution_hours = 2
                ticket.save()

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
                    "customer_phone_number": ticket.customer_phone_number,
                    "customer_name": ticket.customer_name,
                    "resolution_hours": ticket.resolution_hours,
                    "remaining_hours": ticket.remaining_time,
                    "status": ticket.status,
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
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, IsAgent]
    throttle_classes = []

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
    permission_classes = [IsAuthenticated, IsManagerOrSuperAdmin]
    authentication_classes = [JWTAuthentication]
    throttle_classes = []
    lookup_field = "number"
    lookup_url_kwarg = "ticket_number"

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
    RateSupportAgent is the POST request handler that allows a user to rate a support agent.
    """

    serializer_class = AgentRatingSerializers
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    throttle_classes = []
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
    permission_classes = [IsAuthenticated, IsManagerOrSuperAdmin]
    authentication_classes = [JWTAuthentication]
    throttle_classes = []

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
    throttle_classes = []

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
            role = payload["role"]
            if not check_password(password=pin, encoded=request.user.agent_pin):
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
                            Your {role} account has been created. Follow this
                            <a href="{signup_link}" style="color: #3498db; text-decoration: none;">
                                link
                            </a>
                            to complete your signup.<br><br>
                            If you have any questions, feel free to contact us at our support email or phone below.
                        """,
                        "support_email": "support@picadailys.com",
                        "picadailys_phone": "02012271894 02012271895"
                    },
                )

                Messaging.send_email(
                    sender_email="notifications@picadailys.com",
                    body=f"Your agent account has been created. Follow this link to complete your signup: {signup_link}",
                    email=user.email,
                    html_content=text_content,
                    subject=f"{role} Registration",
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
    throttle_classes = []

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

        if instance.is_verified:
            logger.warning("Agent with Id: %s has already completed signup.", user_id)
            return Response(
                {
                    "status": "fail",
                    "message": "User has already registered."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        payload = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in request.data.items()
        }
        logger.debug("Payload for update: %s", payload)

        serializer = self.get_serializer(instance=instance, data=payload, partial=True)

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


class DisableAgentrole(generics.RetrieveUpdateAPIView):
    """
    DisableAgentrole handles the POST request of disabling
    an agent user.
    """

    queryset = User.objects.all()
    serializer_class = DisableAgentSerializer
    permission_classes = [IsAuthenticated, IsManagerOrSuperAdmin]
    authentication_classes = [JWTAuthentication]
    throttle_classes = []

    def post(self, request, *args, **kwargs):
        payload = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in request.data.items()
        }
        email = payload.get("email")
        pin = payload.get("pin")
        logger.info("Received request to disable agent for email: %s", email)
        try:
            user = User.objects.filter(Q(email=email)).first()

            if user is None:
                logger.warning("Agent with email '%s' does not exist.", email)
                return Response(
                    data={"status": "fail", "message": f"Agent with '{email}' does not exist."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            if check_password(password=pin, encoded=request.user.agent_pin):
                user.is_agent_disabled = True
                user.save()
                logger.info("Agent account for '%s' has been disabled.", email)

                UserNotification.objects.create(
                    user=user,
                    title="Disable Agent",
                    message="Your account has been disabled!.",
                )
                logger.info("User notification created for agent '%s'.", email)

                ActivityModel.objects.create(
                    user=request.user,
                    title="Disable Agent",
                    description=f"Admin user, {user.full_name} disabled.",
                )
                logger.info("Activity logged for disabling agent '%s'.", user.full_name)

                resp = {
                    "status": "success",
                    "message": "Agent disabled successfully",
                    "data": user.is_agent_disabled,
                }
                return Response(data=resp, status=status.HTTP_200_OK)
            else:
                logger.warning(
                    "Incorrect pin provided for user: %s %s",
                    request.user.first_name,
                    request.user.last_name,
                )
                return Response(
                    data={"status": "fail", "error": "Incorrect pin"},
                    status=status.HTTP_401_UNAUTHORIZED,
                )

        except Exception as e:
            logger.error("An error occurred while disabling agent: %s", str(e))
            return Response(
                data={"status": "fail", "error": "An error occurred."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class EnableAgentrole(generics.RetrieveUpdateAPIView):
    """
    EnableAgentrole handles the POST request of re-enabling
    a disabled agent user.
    """

    queryset = User.objects.all()
    serializer_class = EnableAgentSerializer
    permission_classes = [IsAuthenticated, IsManagerOrSuperAdmin]
    authentication_classes = [JWTAuthentication]
    throttle_classes = []

    def post(self, request, *args, **kwargs):
        payload = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in request.data.items()
        }
        email = payload.get("email")
        pin = payload.get("pin")
        logger.info("Received request to re-enable agent for email: %s", email)

        try:
            user = User.objects.filter(Q(email=email)).first()

            if user is None:
                logger.warning("Agent with email '%s' does not exist.", email)
                return Response(
                    data={"status": "fail", "error": f"Agent with '{email}' does not exist."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            if check_password(password=pin, encoded=request.user.agent_pin):
                user.is_agent_disabled = False
                user.save()
                logger.info("Agent account for '%s' has been re-enabled.", email)

                UserNotification.objects.create(
                    user=user,
                    title="Re-Enable Agent",
                    message="Your account has been re-enabled successfully.",
                )
                logger.info("User  notification created for agent '%s'.", email)

                ActivityModel.objects.create(
                    user=request.user,
                    title="Re-Enable Agent",
                    description=f"Agent user, {user.full_name} was re-enabled.",
                )
                logger.info(
                    "Activity logged for re-enabling agent '%s'.", user.full_name
                )

                resp = {
                    "status": "success",
                    "message": "Admin re-enabled successfully",
                    "data": user.is_agent_disabled,
                }
                return Response(data=resp, status=status.HTTP_200_OK)
            else:
                logger.warning(
                    "Incorrect pin provided for user: %s %s",
                    request.user.first_name,
                    request.user.last_name,
                )
                return Response(
                    data={"status": "fail", "error": "Incorrect pin"},
                    status=status.HTTP_401_UNAUTHORIZED,
                )

        except Exception as e:
            logger.error("An error occurred while re-enabling agent: %s", str(e))
            return Response(
                data={"status": "fail", "error": "An error occurred."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class DeleteAgent(generics.GenericAPIView):
    serializer_class = AgentDeletionSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsManagerOrSuperAdmin)

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid(raise_exception=True):
            email = serializer.validated_data.get("email")
            pin = serializer.validated_data.get("pin")
            logger.info("Received request to delete agent for email: %s", email)
            try:
                user = User.objects.get(email=email)
                logger.info("Agent user found: %s", user.full_name)
                if check_password(password=pin, encoded=request.user.agent_pin):
                    user.delete()
                    logger.info("Agent user '%s' deleted successfully.", user.full_name)

                    UserNotification.objects.create(
                        user=request.user,
                        title="Delete Agent",
                        message=f"Agent with '{email}' deleted successfully.",
                    )
                    logger.info(
                        "User  notification created for agent deletion: %s", email
                    )

                    # Register Admin activity.
                    ActivityModel.objects.create(
                        user=request.user,
                        title="Delete Agent",
                        description=f"Agent user, {user.full_name} deleted successfully.",
                    )
                    logger.info(
                        "Activity logged for deleting agent: %s", user.full_name
                    )

                    text_content = render_to_string(
                        template_name="empty_email.html",
                        context={
                            "custom_text": f"Dear {request.user.first_name},<br><br>Your agent account has been deleted.",
                            "support_email": "support@picadailys.com",
                            "picadailys_phone": "02012271894 02012271895"
                        },
                    )

                    Messaging.send_email(
                        email=request.user.email,
                        sender_email="notifications@picadailys.com",
                        html_content=text_content,
                        subject="Admin Deletion",
                        body="Your admin account has been deleted",
                    )

                    return Response(
                        data={"status": "success", "message": f"Agent with '{email}' deleted successfully."},
                        status=status.HTTP_200_OK,
                    )
                else:
                    logger.warning(
                        "Incorrect pin provided for user: %s %s",
                        request.user.first_name,
                        request.user.last_name,
                    )
                    return Response(
                        data={"status": "fail", "error": "Incorrect pin"},
                        status=status.HTTP_401_UNAUTHORIZED,
                    )
            except User.DoesNotExist:
                logger.warning("Agent with email '%s' does not exist.", email)
                return Response(
                    data={"status": "fail", "error": f"Agent with '{email}' does not exist."},
                    status=status.HTTP_404_NOT_FOUND,
                )
        else:
            logger.error("Serializer validation failed: %s", serializer.errors)
            return Response(
                data={"status": "fail", "error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST
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
            msg = "Welcome to Picadailys Support... Your registration as the support manager was successful!."
            recipient = user.phone_number[1:]

            Messaging.send_sms(phone_number=recipient, msg=msg)
            logger.info("Welcome message sent to user %s at %s", user.id, recipient)

            # Render the template with values
            text_content = render_to_string(
                template_name="empty_email.html",
                context={
                    "custom_text": f"Dear {user.full_name},<br><br>{msg}.",
                    "support_email": "support@picadailys.com",
                    "picadailys_phone":
                        "02012271894  02012271895",
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

        if not email or not password:
            logger.warning("Login attempt with missing email or password.")
            return Response(
                data={"status": "fail", "message": "Email and password are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # Retrieve the user by email to get the phone number
            # Use filter().first() instead of get() to handle duplicates gracefully
            user = User.objects.filter(email=email).first()

            if not user:
                logger.warning(f"Login attempt failed: User with email {email} not found.")
                return Response(
                    data={"status": "fail", "message": "Invalid credentials"},
                    status=status.HTTP_401_UNAUTHORIZED,
                )
        except Exception as e:
            logger.exception(f"Error retrieving user with email {email}: {str(e)}")
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
    throttle_classes = []

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
        authenticated_user.agent_pin = hashed_pin
        authenticated_user.is_agent_pin_set = True
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


class GetAllAgentModeratorAndSupportManager(generics.ListAPIView):
    """
    GetAllAgentModeratorAndSupportManager is the GET request to retrieve the
    count and list of users with user_type 'Agent','Moderator' and 'Manager'.
    """

    queryset = User.objects.all()
    serializer_class = ListAgentModeratorAndManagerSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsAgent)
    pagination_class = CustomPageNumberPagination
    throttle_classes = []

    def get_queryset(self):
        logger.info("Retrieving agent and moderator users.")
        users = (
            User.objects.filter(
                account_types__user_type__in=["Agent", "Moderator", "Manager"]
            )
            .distinct()
            .order_by("account_types__created_at")
        )
        logger.info("Agent, moderator and manager users retrieved successfully.")
        return users

    def list(self, request, *args, **kwargs):
        logger.info("Accessing agent, moderator and manager users list view.")

        agents = User.objects.filter(
            account_types__user_type="Agent"
        ).annotate(
            total_tickets_assigned=Count("assigned_tickets", distinct=True),
            total_tickets_resolved=Count("resolved_tickets", distinct=True),
            average_rating=Avg(
                Case(
                    When(agent_rated__rating="5", then=5),
                    When(agent_rated__rating="4", then=4),
                    When(agent_rated__rating="3", then=3),
                    When(agent_rated__rating="2", then=2),
                    When(agent_rated__rating="1", then=1),
                    output_field=IntegerField()
                )
            ),
            rating_count=Count("agent_rated", distinct=True)
        ).distinct()

        moderators = User.objects.filter(
            account_types__user_type="Moderator"
        ).annotate(
            total_tickets_assigned=Count("assigned_tickets", distinct=True),
            total_tickets_resolved=Count("resolved_tickets", distinct=True),
            average_rating=Avg(
                Case(
                    When(agent_rated__rating="5", then=5),
                    When(agent_rated__rating="4", then=4),
                    When(agent_rated__rating="3", then=3),
                    When(agent_rated__rating="2", then=2),
                    When(agent_rated__rating="1", then=1),
                    output_field=IntegerField()
                )
            ),
            rating_count=Count("agent_rated", distinct=True)
        ).distinct()

        managers = User.objects.filter(
            account_types__user_type="Manager"
        ).annotate(
            total_tickets_assigned=Count("assigned_tickets", distinct=True),
            total_tickets_resolved=Count("resolved_tickets", distinct=True),
            average_rating=Avg(
                Case(
                    When(agent_rated__rating="5", then=5),
                    When(agent_rated__rating="4", then=4),
                    When(agent_rated__rating="3", then=3),
                    When(agent_rated__rating="2", then=2),
                    When(agent_rated__rating="1", then=1),
                    output_field=IntegerField()
                )
            ),
            rating_count=Count("agent_rated", distinct=True)
        ).distinct()

        response_data = {
            "status": "success",
            "message": "Users retrieved successfully",
            "num_of_agents": agents.count(),
            "num_of_moderators": moderators.count(),
            "num_of_managers": managers.count(),
            "agents": self.get_serializer(agents, many=True).data,
            "moderators": self.get_serializer(moderators, many=True).data,
            "managers": self.get_serializer(managers, many=True).data,
        }

        return Response(response_data, status=status.HTTP_200_OK)


class CompleteTicketAPIView(generics.RetrieveUpdateAPIView):
    """
    CompleteTicketAPIView is the POST request to mark a ticket as completed.
    """

    queryset = Ticket.objects.all()
    serializer_class = CompleteTicketSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, IsAgent]
    throttle_classes = []

    def post(self, request, *args, **kwargs):

        authenticated_user = request.user

        payload = {
            k: v.strip() if isinstance(v, str) else v
            for k, v in request.data.items()
        }

        serializer = self.get_serializer(data=payload)
        serializer.is_valid(raise_exception=True)

        ticket_number = kwargs.get("ticket_number")
        attachment = serializer.validated_data["resolution_attachment"]

        ticket = Ticket.objects.filter(number=ticket_number).first()

        ticket.status = "Resolved"
        ticket.resolution_attachment = attachment
        ticket.resolved_by = authenticated_user
        ticket.resolved_at = timezone.now()
        ticket.save()
        
        response_data = {
            "status": "success",
            "message": f"Ticket {ticket_number} marked as completed successfully.",
            "data": {
                "ticket_number": ticket_number,
                "status": ticket.status,
                "resolved_at": ticket.resolved_at,
                "resolved_by": ticket.resolved_by.full_name if ticket.resolved_by else None,
                "resolution_attachment": ticket.resolution_attachment,
            }
        }
