import logging
from django.contrib.auth.hashers import check_password
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Count, Sum, F, FloatField
from django.db.models.functions import Cast
from django.contrib.auth import authenticate
from django.db.models import Q
from django.utils import timezone
from django.core.cache import cache
from datetime import timedelta
from datetime import datetime

from django.template.loader import render_to_string

# In project imports.
from .serializers import (
    RegisterSuperAdminSerializer,
    AdminLoginSerializers,
    AddAdminContdSerializer,
    AddAdminSerializer,
    AddRoleToAdminSerializer,
    RemoveRoleFromAdminSerializer,
    AdminDeletionSerializer,
    ListAdminSerializer,
    DisableAdminSerializer,
    SwitchRolesSerializers,
    CreateAdminPinSerializer,
    EnableAdminSerializer,
    GetAllActivityLogsSerializer,
    ForgotPinSerializer,
    AdminResetPinSerializer,
    AdminDdashboardDataSerializer,
    StaffForgotPasswordSerializer,
    StaffPasswordResendOTPSerializer,
    StaffResetPasswordSerializer,
    AdminKnowledgeBaseSerializer,
    KnowledgeBaseListSerializer,
    KnowledgeBaseDetailSerializer,
    TransactionResolutionSerializer,
)
from user_profile.serializers import GetUserSerializer
from partners.serializers import PartnerProfileSerializer
from adverts.serializers import BrandAdProfileSerializers
from fmcg.serializers import ProductSerializers, AddFmcgPickupAddressSerializers
from banking.serializers import WalletStatusSerializer
from banking.models import WalletModel, TransferModel, FundWithCard
from vas.models import ValueAddedServices
from .models import ActivityModel, knowledgeBaseModel
from fmcg.models import Product, PickupAdress
from accounts.models import AccountType
from accounts.tokens import create_jwt_pair_for_user
from accounts.serializers import VerifyOTPSerializer
from support.models import Ticket
from support.utils import generate_ticket_number

# Third party imports.
from rest_framework import generics, status, exceptions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.parsers import MultiPartParser, JSONParser
from rest_framework.pagination import PageNumberPagination
from rest_framework_simplejwt.tokens import RefreshToken

import rest_framework.serializers as s
from drf_spectacular.utils import extend_schema, OpenApiParameter, inline_serializer
from drf_spectacular.types import OpenApiTypes

from .models import ADMIN_TYPES

from cloudinary import uploader as cloud

from accounts.models import User, UserNotification, TxModel
from accounts.otp import otp_manager
from .analytics import (
    resolve_period,
    compute_trend,
    GRANULARITY_CHOICES,
    get_cashflow_snapshot,
    get_services_snapshot,
    get_customer_insight_snapshot,
    ACTIVE_USER_THRESHOLD_DAYS,
    get_pending_settlement_count,
    get_duplicate_transaction_count,
    get_all_transactions,
    get_picapoints_overview_snapshot,
    get_points_source_breakdown,
    get_task_insight_snapshot,
    get_demographic_breakdown_snapshot,
    get_reconciliation_differences_count,
    get_pending_settlement_list,
    get_transaction_detail_row,
    get_reconciliation_differences_list,
    get_reconciliation_difference_detail,
    get_duplicate_transactions_list,
    get_duplicate_transaction_detail,
    get_fraud_alerts_list,
    SERVICES_TAB_CHOICES,
    SERVICE_TYPE_CHOICES_BY_CATEGORY,
    get_daily_income_expenditure_series,
    bucket_income_expenditure_series,
    get_vas_income_expenditure_breakdown,
    get_transaction_overview_snapshot,
    get_customer_insight_extended,
    get_ads_insight_snapshot,
    get_inbound_credit_sum,
)
from security import encrypt, decrypt
from permissions import (
    IsSuperAdmin,
    IsNotDisabled,
    IsAdmin,
    IsFmcgAdminOrSuperAdmin,
    IsWalletAdminOrSuperAdmin,
)

from commons import Messaging

from tasks.models import SocialTask, TaskSubmission, BrandTaskSubmission
from adverts.models import CreateAd
from gamification.models import StreakChallenge, TRANSACTION_SOURCE_CHOICES
from permissions import IsTaskAdminOrSuperAdmin
from modules.response_mixings import StandardResponseMixin, Pagination


class CustomPageNumberPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100


logger = logging.getLogger(__name__)


class PaginationStyle(PageNumberPagination):
    page_size = 10


@extend_schema(
    summary="Register the super admin account",
    tags=["Admin"],
    description="One-time registration endpoint for the platform's SuperAdmin. Sends an OTP to the registered phone number for verification.",
    request=RegisterSuperAdminSerializer,
    responses={
        201: inline_serializer(
            "RegisterSuperAdminResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        403: inline_serializer(
            "RegisterSuperAdminForbidden",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class RegisterSuperAdmin(generics.GenericAPIView):
    """
    RegisterSuperAdmin handles the POST request of registering a superuser,
    It takes in email, phone, active_role, password, and password2.
    Sends an OTP to the phone for validation.
    """

    serializer_class = RegisterSuperAdminSerializer

    def post(self, request):
        decrypted_payload = decrypt(request.data)
        payload = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_payload.items()
        }

        # Check if an active and enabled SuperAdmin already exists.
        if User.objects.filter(
            active_role="SuperAdmin", is_active=True, is_disabled=False
        ).exists():
            return Response(
                data="Registration is not allowed. Super admin already exists.",
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = self.serializer_class(data=payload)
        if serializer.is_valid(raise_exception=True):
            try:
                current_user = serializer.save()
                logger.info(
                    f"SuperAdmin registration initiated for user: {current_user.email}"
                )
                # Set the user's role and create AccountType
                current_user.active_role = "SuperAdmin"
                current_user.save()
                logger.info(f"SuperAdmin role assigned to user: {current_user.email}")

                AccountType.objects.create(
                    user=current_user,
                    user_type="SuperAdmin",
                )
                logger.info(
                    f"AccountType 'SuperAdmin' created for user: {current_user.email}"
                )

                # Create and send OTP
                otp = otp_manager.create_otp(user_id=str(current_user.id))
                msg = f"Welcome SuperUser! This is a one-time signup. To protect your account, please enter this {otp}."
                recipient = current_user.phone_number[1:]

                logger.info(f"OTP generated for SuperAdmin: {otp}")
                print(f"OTP for SuperAdmin registration: {otp}")
                # Send OTP message — WhatsApp first (registration), SMS fallback
                Messaging.send_otp_whatsapp_first(
                    phone_number=recipient, otp=otp, msg=msg
                )

                # Log the creation of the SuperUser
                UserNotification.objects.create(
                    user=current_user,
                    title="Create SuperUser.",
                    message="SuperUser account created Successfully.",
                )
                logger.info(f"UserNotification created for user: {current_user.id}")

                ActivityModel.objects.create(
                    user=current_user,
                    title="Create SuperUser.",
                    description="SuperUser account created Successfully.",
                )
                logger.info(f"ActivityModel created for user: {current_user.id}")

                response = {
                    "status": "success",
                    "message": "SuperUser Created Successfully. Check your phone for an OTP.",
                    "data": serializer.data,
                }
                return Response(data=encrypt(response), status=status.HTTP_201_CREATED)

            except Exception as err:
                logger.error(
                    f"Error occurred while creating SuperUser: {str(err)}",
                    exc_info=True,
                )
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "message": "Registration failed. Please try again.",
                        }
                    ),
                    status=status.HTTP_409_CONFLICT,
                )

        logger.warning("Invalid data received for SuperAdmin registration.")
        return Response(
            data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST
        )


@extend_schema(
    summary="Admin login",
    tags=["Admin"],
    description="Authenticates an admin user by email and password, returning JWT tokens and user details on success.",
    request=AdminLoginSerializers,
    responses={
        200: inline_serializer(
            "AdminLoginResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "tokens": s.DictField(),
                "user_data": s.DictField(),
            },
        ),
        401: inline_serializer(
            "AdminLoginUnauthorized", fields={"error": s.CharField()}
        ),
    },
)
class LoginAdmin(APIView):
    """LoginAPIView handles the POST request of logging in
    a verified user with valid login credentials.
    """

    serializer_class = AdminLoginSerializers

    def post(self, request):
        decrypted_payload = decrypt(request.data)
        data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_payload.items()
        }
        email = data.get("email")
        password = data.get("password")

        user_obj = User.objects.filter(email=email).first()
        if (
            user_obj
            and user_obj.password_locked_until
            and user_obj.password_locked_until > timezone.now()
        ):
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "Account locked due to too many failed login attempts. Try again later.",
                    }
                ),
                status=status.HTTP_403_FORBIDDEN,
            )
        if not user_obj:
            logger.warning(f"Login attempt failed: User with email {email} not found.")
            return Response(
                data=encrypt({"status": "fail", "message": "Invalid credentials"}),
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if user_obj.is_admin_disabled:
            logger.warning(f"Login attempt blocked: Admin account {email} is disabled.")
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "This admin account has been disabled.",
                    }
                ),
                status=status.HTTP_403_FORBIDDEN,
            )

        # Authenticate using the phone number and password
        user = authenticate(phone_number=user_obj.phone_number, password=password)

        if user:
            logger.info(f"User {user.email} authenticated successfully.")

            # Reset attempts on successful login
            user_obj.password_attempts = 0
            user_obj.password_locked_until = None
            user_obj.save(update_fields=["password_attempts", "password_locked_until"])

            if not user.is_verified:
                logger.warning(
                    f"User {user.email} is not verified. Login attempt blocked."
                )
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "message": "Please verify your account to login",
                        }
                    ),
                    status=status.HTTP_401_UNAUTHORIZED,
                )

            logger.info(f"User {user.email} successfully logged in.")

            user_name = (
                "SuperAdmin"
                if user.active_role == "SuperAdmin"
                else (
                    user.full_name
                    if user.active_role
                    in {
                        "TaskAdmin",
                        "AdAdmin",
                        "MembersAdmin",
                        "UserAdmin",
                        "PartnersAdmin",
                        "ContentAdmin",
                        "IntegrationAdmin",
                        "WalletAdmin",
                        "FmcgAdmin",
                    }
                    else "Unknown"
                )
            )

            UserNotification.objects.create(
                user=user, title="Login.", message="Login successful."
            )
            ActivityModel.objects.create(
                user=user,
                title="Admin Login.",
                description=f"Admin User, {user_name} logged in.",
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
            return Response(data=encrypt(response), status=status.HTTP_200_OK)
        else:
            # Increment attempts and maybe lock
            user_obj.password_attempts = (user_obj.password_attempts or 0) + 1
            if user_obj.password_attempts >= 4:
                user_obj.password_locked_until = timezone.now() + timedelta(minutes=30)
                user_obj.save(
                    update_fields=["password_attempts", "password_locked_until"]
                )
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "message": "Too many failed login attempts. Account locked for 30 minutes.",
                        }
                    ),
                    status=status.HTTP_403_FORBIDDEN,
                )
            else:
                user_obj.save(update_fields=["password_attempts"])
            logger.warning(
                f"Login attempt failed for user with email {email}. Invalid credentials."
            )
            return Response(
                data=encrypt({"error": "Invalid credentials"}),
                status=status.HTTP_401_UNAUTHORIZED,
            )


@extend_schema(
    summary="Add an FMCG product",
    tags=["Admin"],
    description="Allows an FMCG admin or SuperAdmin to upload a new FMCG product, including its images, nutritional data, and storage details.",
    request=ProductSerializers,
    responses={
        201: inline_serializer(
            "AddProductResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "data": s.DictField(),
            },
        ),
        400: inline_serializer(
            "AddProductError",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class AddProduct(generics.GenericAPIView):
    """
    AddProduct is the POST request that handles the creation
    of fmcg products instance.
    """

    serializer_class = ProductSerializers
    permission_classes = [IsAuthenticated, IsFmcgAdminOrSuperAdmin]
    parser_classes = (
        MultiPartParser,
        JSONParser,
    )

    def post(self, request):
        user_data = request.data
        authenticated_user = request.user
        logger.info(f"User {authenticated_user.email} is attempting to add a product.")
        serializer = ProductSerializers(data=user_data)
        if serializer.is_valid(raise_exception=True):
            additional_img_uploads = request.data.getlist("additional_images")
            add_img_urls = []

            try:
                product_upload = request.data.get("image_url")
                upload_product = cloud.upload(product_upload)
                product_url = upload_product["url"]

                if additional_img_uploads:
                    for upload in additional_img_uploads:
                        upload_result = cloud.upload(upload)
                        add_img_url = upload_result["url"]
                        add_img_urls.append(add_img_url)

            except Exception as err:
                logger.error(f"Error uploading product images: {err}")
                return Response(
                    data=encrypt({"error": "An error occurred: {}".format(err)}),
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

            product_entry = Product.objects.create(
                name_and_size=user_data.get("name_and_size"),
                image_url=product_url,
                category=user_data.get("category"),
                price=user_data.get("price"),
                description=user_data.get("description"),
                expiry_date=user_data.get("expiry_date"),
                macro_nutrients=user_data.get("macro_nutrients"),
                micro_nutrients=user_data.get("micro_nutrients"),
                density=user_data.get("density"),
                calories=user_data.get("calories"),
                moisture=user_data.get("moisture"),
                texture=user_data.get("texture"),
                storage=user_data.get("storage"),
                additional_images_urls=",".join(add_img_urls),
                subtitle=user_data.get("subtitle"),
                input_style=user_data.get("input_style"),
            )
            product_entry.additional_images_urls = ",".join(add_img_urls)
            product_entry.save()

            logger.info(
                f"Product {product_entry.name_and_size} added by {authenticated_user.email}."
            )

            ActivityModel.objects.create(
                user=authenticated_user,
                title="Add product",
                description=f"Admin User {authenticated_user.active_role}, added fmcg product {product_entry} to the store.",
            )

            resp = {
                "status": "success",
                "message": "Product added successfully!",
                "data": {
                    "name_and_size": user_data.get("name_and_size"),
                    "image_url": product_url,
                    "category": user_data.get("category"),
                    "price": user_data.get("price"),
                    "description": user_data.get("description"),
                    "expiry_date": user_data.get("expiry_date"),
                    "macro_nutrients": user_data.get("macro_nutrients"),
                    "micro_nutrients": user_data.get("micro_nutrients"),
                    "density": user_data.get("density"),
                    "calories": user_data.get("calories"),
                    "moisture": user_data.get("moisture"),
                    "texture": user_data.get("texture"),
                    "storage": user_data.get("storage"),
                    "additional_images": add_img_urls,
                    "subtitle": user_data.get("subtitle"),
                    "input_style": user_data.get("input_style"),
                },
            }
            return Response(data=encrypt(resp), status=status.HTTP_201_CREATED)

        else:
            logger.warning(
                f"Invalid product data received for user {authenticated_user.email}."
            )
            return Response(
                data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST
            )

    def upload_files(self, doc_file):
        document = cloud.upload(file=doc_file)
        self.uploaded_doc_url = document["url"]


@extend_schema(
    summary="Add an FMCG pickup address",
    tags=["Admin"],
    description="Adds a new pickup address (name and state) for the FMCG store. Requires FMCG admin or SuperAdmin privileges.",
    request=AddFmcgPickupAddressSerializers,
    responses={
        201: inline_serializer(
            "AddAddressResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        400: inline_serializer("AddAddressError", fields={"status": s.CharField()}),
    },
)
class AddAddress(generics.GenericAPIView):
    """
    AddAddress is the POST request that handles the updating of
    of fmcg products store addresses.
    """

    serializer_class = AddFmcgPickupAddressSerializers
    permission_classes = [IsAuthenticated & (IsFmcgAdminOrSuperAdmin)]

    def post(self, request):
        authenticated_user = request.user

        decrypted_payload = decrypt(request.data)
        user_data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_payload.items()
        }

        logger.info(f"User {authenticated_user.email} is attempting to add an address.")

        serializer = self.serializer_class(data=user_data)
        if serializer.is_valid(raise_exception=True):
            PickupAdress.objects.create(
                name=user_data["name"], state=user_data["state"]
            )

            user_name = (
                "Superuser"
                if authenticated_user.active_role == "Superuser"
                else (
                    authenticated_user.full_name
                    if authenticated_user.active_role
                    in {
                        "SuperAdmin",
                        "TaskAdmin",
                        "AdAdmin",
                        "MembersAdmin",
                        "UserAdmin",
                        "PartnersAdmin",
                        "ContentAdmin",
                        "IntegrationAdmin",
                        "WalletAdmin",
                        "FmcgAdmin",
                    }
                    else "Unknown"
                )
            )
            name = user_data["name"]
            state = user_data["state"]

            logger.info(f"Address {name}, {state} added by {authenticated_user.email}.")

            ActivityModel.objects.create(
                user=authenticated_user,
                title="Add FMCG product.",
                description=f"Admin User, {user_name}, added {name, state} as FMCG pickup address.",
            )
            resp = {
                "status": "success.",
                "message": "Store address added successfully.",
                "data": serializer.data,
            }
            return Response(data=encrypt(resp), status=status.HTTP_201_CREATED)
        else:
            error_resp = encrypt({"status": "fail.", "data": serializer.errors})
            logger.warning(
                f"Invalid address data received from user {authenticated_user.email}."
            )
            return Response(data=error_resp, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    summary="Create a new admin user",
    tags=["Admin"],
    description="Creates a new admin user and sends a signup link to their email. Only the SuperAdmin can invoke this endpoint.",
    request=AddAdminSerializer,
    responses={
        201: inline_serializer(
            "AddAdminResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "user_id": s.CharField(),
            },
        ),
        400: inline_serializer(
            "AddAdminError", fields={"status": s.CharField(), "message": s.CharField()}
        ),
    },
)
class AddAdmin(generics.CreateAPIView):
    """
    Create a new admin.
    Only superadmins can create new admins.
    If the user is successfully created, a JSON object containing the user's data is returned.
    If the user cannot be created, a 400 Bad Request or 403 Forbidden error is returned.
    """

    queryset = User.objects.all()
    serializer_class = AddAdminSerializer
    permission_classes = (IsAuthenticated, IsSuperAdmin)

    def post(self, request):
        try:
            # Log request initiation
            logger.info("Received request to add a new admin.")

            decrypted_payload = decrypt(request.data)
            # Process payload
            payload = {
                key: value.strip() if isinstance(value, str) else value
                for key, value in decrypted_payload.items()
            }
            logger.debug("Processed payload.")

            # Check if email exists
            if User.objects.filter(email=payload.get("email")).exists():
                logger.warning(
                    f"Attempt to create admin with existing email: {payload.get('email')}"
                )
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "message": "A user with this email already exists.",
                        }
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if not payload["roles"]:
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "message": "At least one role must be selected.",
                        }
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Validate and save user
            serializer = AddAdminSerializer(data=payload)
            if serializer.is_valid(raise_exception=True):
                user = serializer.save()
                cache.delete_many(["all_admin_users", "admin_users_by_role"])
                user_data = AddAdminSerializer(user).data
                logger.info(f"Admin user created successfully: {user.email}")

                # Generate signup link
                signup_link = f"https://admin.picadailys.com/sign-up?user_id={user.id}"

                name = (user.full_name or "Admin").split()[0]
                text_content = render_to_string(
                    template_name="empty_email.html",
                    context={
                        "custom_text": f"""
                            Dear {name},<br><br>
                            Your admin account has been created. Follow this
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
                            "08134032631",
                        ],
                    },
                )

                Messaging.send_email(
                    sender_email="notifications@picadailys.com",
                    body="Your admin account has been created.",
                    email=user.email,
                    html_content=text_content,
                    subject="Admin Registration",
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
                    data=encrypt(resp),
                    status=status.HTTP_201_CREATED,
                )
        except ValidationError as e:
            logger.warning(f"Validation error: {e}")
            raise ValidationError(encrypt(message=e), code=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"An unexpected error occurred: {e}")
            return Response(
                data=encrypt(
                    {"status": "Error", "message": "An unexpected error occurred."}
                ),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


@extend_schema(
    summary="Complete admin account signup",
    tags=["Admin"],
    description="Completes admin registration by setting a phone number and password for a user who received an invite link.",
    request=AddAdminContdSerializer,
    responses={
        200: inline_serializer(
            "AdAdminContdResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        404: inline_serializer(
            "AdAdminContdNotFound",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class AdAdminContd(generics.UpdateAPIView):
    """
    AdAdminContd is a POST request that handles the admin signup completion.
    """

    serializer_class = AddAdminContdSerializer
    permission_classes = [AllowAny]

    def get_object(self):
        user_id = self.kwargs.get("user_id")

        try:
            user = User.objects.get(id=user_id)
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

            if is_admin:
                return user
            else:
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "message": "User exists, but is not an admin.",
                        }
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )

        except User.DoesNotExist:
            return None

    def update(self, request, *args, **kwargs):
        user_id = kwargs.get("user_id")  # Assuming the user ID is passed in the URL
        logger.info("Update request received for user ID: %s", user_id)

        instance = self.get_object()
        if instance is None:
            logger.warning("User  with ID %s not found.", user_id)
            return Response(
                data=encrypt("User  not found."), status=status.HTTP_404_NOT_FOUND
            )
        elif isinstance(instance, Response):  # Return Response if not an admin
            logger.warning(
                "User  with ID %s is not an admin, returning response.", user_id
            )
            return instance

        decrypted_payload = decrypt(request.data)
        payload = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_payload.items()
        }
        logger.debug("Payload for update received.")

        serializer = self.get_serializer(instance=instance, data=payload)

        if serializer.is_valid(raise_exception=True):
            password = serializer.validated_data.get("password")
            password2 = serializer.validated_data.get("password2")

            if password != password2:
                return Response(
                    encrypt(data={"password": "Passwords do not match."}),
                    status=status.HTTP_400_BAD_REQUEST,
                )

            user = serializer.save()
            user.set_password(
                serializer.validated_data.get("password", user.password)
            )  # Ensure password is set correctly
            user.is_verified = True
            user.save()

            ActivityModel.objects.create(
                user=user,
                title="Admin Complete Signup.",
                description=f"Admin user {instance.full_name} completed signup.",
            )
            logger.info(
                "User  registration completed successfully for user ID: %s", user_id
            )
            return Response(
                data=encrypt(
                    {
                        "status": "success",
                        "message": "User  registration completed successfully.",
                        "data": serializer.data,
                    }
                ),
                status=status.HTTP_200_OK,
            )
        else:
            logger.error(
                "Error during user update for user ID %s: %s",
                user_id,
                serializer.errors,
            )
            return Response(
                data=encrypt({"status": "fail", "message": serializer.errors}),
                status=status.HTTP_400_BAD_REQUEST,
            )


@extend_schema(
    summary="Set admin PIN",
    tags=["Admin"],
    description="Creates a 5-digit transaction PIN for the currently authenticated admin user.",
    request=CreateAdminPinSerializer,
    responses={
        201: inline_serializer(
            "SetAdminPinResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        400: inline_serializer(
            "SetAdminPinError",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class SetAdminPin(generics.CreateAPIView):
    """
    SetWalletPin handles the POST request of creating a pin for a
    customer wallet.
    """

    serializer_class = CreateAdminPinSerializer
    permission_classes = (IsAuthenticated, IsAdmin)

    def perform_create(self, serializer, request):
        decrypted_payload = decrypt(request.data)
        pin = decrypted_payload.get("pin")
        user = request.user
        logger.info(f"Creating admin pin for user: {user.first_name} {user.last_name}")

        if not pin:
            logger.warning(
                f"No pin provided for user: {user.first_name} {user.last_name}"
            )
            return Response(
                data=encrypt({"status": "fail", "message": "Pin is required."}),
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Hash the pin using make_password.
        hashed_pin = make_password(pin)

        # Save the hashed pin in the authenticated user's admin_pin field.
        authenticated_user = self.request.user
        authenticated_user.admin_pin = hashed_pin
        authenticated_user.is_admin_pin_set = True
        authenticated_user.save()
        logger.info("Admin pin set for user: %s %s", user.first_name, user.last_name)

        # Create a user notification
        UserNotification.objects.create(
            user=authenticated_user,
            title="Admin Pin",
            message="Admin pin created successfully.",
        )
        logger.info(
            "User  notification created for user: %s %s",
            user.first_name,
            user.last_name,
        )

    def create(self, request, *args, **kwargs):
        decrypted_payload = decrypt(request.data)
        user_data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_payload.items()
        }
        logger.info("Create request received with data: %s", user_data)

        serializer = self.serializer_class(data=user_data)
        if serializer.is_valid(raise_exception=True):
            self.perform_create(serializer, request)
            response = {
                "status": "success",
                "message": "Admin pin created successfully!",
            }
            logger.info(
                "Admin pin created successfully for user: %s %s",
                request.user.first_name,
                request.user.last_name,
            )
            return Response(data=encrypt(response), status=status.HTTP_201_CREATED)
        else:
            logger.error("Validation errors occurred: %s", serializer.errors)
            return Response(
                data=encrypt({"status": "fail", "message": serializer.errors}),
                status=status.HTTP_400_BAD_REQUEST,
            )


@extend_schema(
    summary="Send OTP for staff forgotten password",
    tags=["Admin"],
    description="Sends a password-reset OTP to a staff member's registered email address. Restricted to recognised staff roles.",
    request=StaffForgotPasswordSerializer,
    responses={
        201: inline_serializer(
            "StaffForgotPasswordResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        403: inline_serializer(
            "StaffForgotPasswordForbidden",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class StaffForgotPassword(generics.GenericAPIView):

    serializer_class = StaffForgotPasswordSerializer
    throttle_scope = "password_change"

    def post(self, request):

        decrypted_payload = decrypt(request.data)

        serializer = self.serializer_class(data=decrypted_payload)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response(
                encrypt(
                    {
                        "status": "success",
                        "message": "If this account exists, an OTP has been sent.",
                    }
                ),
                status=status.HTTP_200_OK,
            )

        # Restrict to staff roles only
        if not user.account_types.filter(
            user_type__in=[
                "SuperAdmin",
                "AdAdmin",
                "MembersAdmin",
                "PartnersAdmin",
                "ContentAdmin",
                "WalletAdmin",
                "FmcgAdmin",
            ]
        ).exists():

            return Response(
                encrypt(
                    {
                        "status": "fail",
                        "message": "This account is not authorized for staff portal.",
                    }
                ),
                status=status.HTTP_403_FORBIDDEN,
            )

        user_id = user.id
        otp = otp_manager.create_otp(user_id=str(user_id))
        msg = f"Enter this {otp} to verify your account and reset your login password"

        text_content = render_to_string(
            template_name="empty_email.html",
            context={
                "custom_text": f"Dear {user.full_name},<br><br>{msg}.",
                "support_email": "support@picadailys.com",
                "picadailys_phone": "02012271894 02012271895 08134032631",
            },
        )

        Messaging.send_email(
            email=email,
            html_content=text_content,
            subject="Admin Password Reset Request",
            sender_email="notifications@picadailys.com",
            body="You have requested a password reset. Please use the OTP sent to your email to proceed.",
        )
        # TODO: Consider sending OTP to phone as well if phone number is available for added security and convenience.
        logger.info(f"OTP sent to email: {email}")

        ActivityModel.objects.create(
            user=user,
            title="Admin Password Reset Request",
            description=f"{user.first_name} {user.last_name} submitted a password reset request.",
        )

        response = {
            "status": "success",
            "message": "Check your mailbox for an OTP",
        }
        encrypted_response = encrypt(response)
        return Response(data=encrypted_response, status=status.HTTP_201_CREATED)


@extend_schema(
    summary="Resend OTP for staff password reset",
    tags=["Admin"],
    description="Resends the password-reset OTP email to the provided staff email address.",
    request=StaffPasswordResendOTPSerializer,
    responses={
        200: inline_serializer(
            "StaffPasswordResendOTPResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        404: inline_serializer(
            "StaffPasswordResendOTPNotFound",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class StaffPasswordResendOTP(generics.GenericAPIView):
    """
    StaffPasswordResendOTP handles the POST request of resending an
    OTP to a admin after password reset.
    """

    permission_classes = (AllowAny,)
    serializer_class = StaffPasswordResendOTPSerializer

    def post(self, request):
        decrypted_payload = decrypt(request.data)

        user_data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_payload.items()
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
                msg = msg = (
                    f"Enter this {otp} to verify your account and reset your login password"
                )

                text_content = render_to_string(
                    template_name="empty_email.html",
                    context={
                        "custom_text": f"Dear {user.full_name},<br><br>{msg}.",
                        "support_email": "support@picadailys.com",
                        "picadailys_phone": "02012271894 02012271895 08134032631",
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
                return Response(data=encrypt(response), status=status.HTTP_200_OK)

            except User.DoesNotExist:
                logger.warning("Admin with email %s does not exist.", email)
                resp = {
                    "status": "fail",
                    "message": "Admin with the provided email does not exist.",
                }
                encrypted_response = encrypt(resp)
                return Response(
                    data=encrypted_response,
                    status=status.HTTP_404_NOT_FOUND,
                )

        else:
            logger.error("OTP resend validation failed.")
            return Response(
                data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST
            )


@extend_schema(
    summary="Verify OTP for staff password reset",
    tags=["Admin"],
    description="Validates the OTP received by a staff member and unlocks the password-reset flow, returning the user ID on success.",
    request=VerifyOTPSerializer,
    responses={
        200: inline_serializer(
            "StaffEmailVerifyOTPResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "user_id": s.CharField(),
            },
        ),
        400: inline_serializer(
            "StaffEmailVerifyOTPError",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class StaffEmailVerifyOTP(generics.GenericAPIView):
    """
    StaffEmailVerifyOTP handles the POST request of verifying a
    staff member with a valid email address for password reset.
    """

    permission_classes = (AllowAny,)
    serializer_class = VerifyOTPSerializer

    def post(self, request):
        decrypted_payload = decrypt(request.data)
        user_data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_payload.items()
        }

        serializer = self.serializer_class(data=user_data)
        if serializer.is_valid(raise_exception=True):
            received_otp = serializer.data["otp"]
            logger.info("OTP received for password reset.")

            # Validate OTP
            user_id = otp_manager.validate_user_otp(received_otp)
            if not user_id:
                logger.warning("Invalid or expired OTP during password reset.")
                return Response(
                    data=encrypt(
                        {"status": "fail", "message": "Invalid or expired OTP"}
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )

            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                logger.error(
                    "Admin with id %s not found for password reset verification.",
                    user_id,
                )
                return Response(
                    data=encrypt({"status": "fail", "message": "Admin not found"}),
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Send confirmation message to the user
            msg = "Admin is verified... You can reset your password now!"
            text_content = render_to_string(
                template_name="empty_email.html",
                context={
                    "custom_text": f"Dear {user.full_name},<br><br>{msg}.",
                    "support_email": "support@picadailys.com",
                    "picadailys_phone": "02012271894 02012271895 08134032631",
                },
            )

            recipient = user.email
            Messaging.send_email(
                email=recipient,
                html_content=text_content,
                subject="Admin Password Reset Request",
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
                description=f"{user.first_name} {user.last_name} verified OTP for password reset.",
            )
            logger.info(
                "Password reset OTP verification activity logged for user %s.", user.id
            )

            verified_response = {
                "status": "success",
                "message": "Account is verified",
                "user_id": user_id,
            }
            encrypted_response = encrypt(verified_response)
            return Response(data=encrypted_response, status=status.HTTP_200_OK)
        else:
            logger.error(
                "Serializer validation failed with errors: %s", serializer.errors
            )
            return Response(
                data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST
            )


@extend_schema(
    summary="Reset staff account password",
    tags=["Admin"],
    description="Resets the password for a staff member identified by admin_id after OTP verification. Optionally invalidates the refresh token.",
    request=StaffResetPasswordSerializer,
    responses={
        200: inline_serializer(
            "StaffResetPasswordResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        400: inline_serializer(
            "StaffResetPasswordError", fields={"error": s.CharField()}
        ),
    },
)
class StaffResetPassword(generics.CreateAPIView):
    serializer_class = StaffResetPasswordSerializer

    def create(self, request):
        decrypted_payload = decrypt(request.data)
        payload = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_payload.items()
        }
        serializer = self.get_serializer(data=payload)
        if not serializer.is_valid(raise_exception=True):
            return Response(
                data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST
            )

        user_data = serializer.validated_data
        user_id = payload.get("admin_id")

        try:
            user = User.objects.get(id=user_id)
            logger.info(f"Admin found for ID: {user.id}")
        except User.DoesNotExist:
            logger.error(f"Admin not found with ID: {user_id}")
            return Response(
                data=encrypt({"error": "Admin not found"}),
                status=status.HTTP_404_NOT_FOUND,
            )

        if user_data["password"] != user_data["password2"]:
            logger.warning("Passwords do not match for admin ID: %s", user_id)
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
        encrypted_response = encrypt(response)
        return Response(data=encrypted_response, status=status.HTTP_200_OK)


@extend_schema(
    summary="Send OTP for admin forgotten PIN",
    tags=["Admin"],
    description="Sends a PIN-reset OTP to the admin's registered email address.",
    request=ForgotPinSerializer,
    responses={
        201: inline_serializer(
            "AdminForgotPinResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        404: inline_serializer(
            "AdminForgotPinNotFound",
            fields={"status": s.CharField(), "detail": s.CharField()},
        ),
    },
)
class AdminForgotPin(generics.GenericAPIView):
    """
    AdminForgotPin handles the POST request of sending a
    forgot pin request for an admin user.
    """

    throttle_scope = "password_change"
    serializer_class = ForgotPinSerializer

    def post(self, request):
        decrypted_payload = decrypt(request.data)
        user_data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_payload.items()
        }
        serializer = self.serializer_class(data=user_data)
        if not serializer.is_valid(raise_exception=True):
            return Response(
                data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST
            )

        email = user_data.get("email")
        try:
            user = User.objects.get(email=email)
            logger.info(f"User found for email: {user.email}")
        except User.DoesNotExist:
            logger.warning(f"No admin found with email: {email}")
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "detail": "An admin with this email does not exist",
                    }
                ),
                status=status.HTTP_404_NOT_FOUND,
            )

        user_id = user.id
        otp = otp_manager.create_otp(user_id=str(user_id))
        msg = f"Enter this {otp} to verify your account and reset your pin"

        text_content = render_to_string(
            template_name="empty_email.html",
            context={
                "custom_text": f"Dear {user.first_name},<br><br>{msg}.",
                "support_email": "support@picadailys.com",
                "picadailys_phone": "02012271894 02012271895 08134032631",
            },
        )

        Messaging.send_email(
            email=email,
            html_content=text_content,
            subject="Admin Pin Reset",
            sender_email="notifications@picadailys.com",
            body="You have requested a pin reset. Please use the OTP sent to your email to proceed.",
        )
        logger.info(f"OTP sent to email: {email}")

        ActivityModel.objects.create(
            user=user,
            title="Admin Pin Reset Request",
            description=f"{user.first_name} {user.last_name} submitted a pin reset request.",
        )

        response = {
            "status": "success",
            "message": "Check your mailbox for an OTP",
        }
        encrypted_response = encrypt(response)
        return Response(data=encrypted_response, status=status.HTTP_201_CREATED)


@extend_schema(
    summary="Verify OTP for admin PIN reset",
    tags=["Admin"],
    description="Validates the OTP submitted for admin PIN reset and returns the user ID to proceed with the new PIN.",
    request=VerifyOTPSerializer,
    responses={
        200: inline_serializer(
            "RolesPinVerifyOTPResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "user_id": s.CharField(),
            },
        ),
        400: inline_serializer(
            "RolesPinVerifyOTPError",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class PinVerifyOTP(generics.GenericAPIView):
    """
    PinVerifyOTP handles the POST request of verifying an admin
    user with valid email for pin reset.
    """

    permission_classes = (AllowAny,)
    serializer_class = VerifyOTPSerializer

    def post(self, request):
        decrypted_payload = decrypt(request.data)
        user_data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_payload.items()
        }
        logger.debug("Received data for pin reset OTP verification.")

        serializer = self.serializer_class(data=user_data)

        # Validate incoming data with serializer class.
        if not serializer.is_valid(raise_exception=True):
            logger.error("Serializer validation failed.")
            return Response(
                data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST
            )

        received_otp = serializer.data["otp"]

        # Validate OTP
        user_id = otp_manager.validate_user_otp(received_otp)
        if not user_id:
            logger.warning("Invalid or expired OTP during pin reset.")
            return Response(
                data=encrypt({"status": "fail", "message": "Invalid or expired OTP"}),
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            logger.error(
                "Admin user with id %s not found for pin reset verification.",
                user_id,
            )
            return Response(
                data=encrypt({"status": "fail", "message": "Admin user not found"}),
                status=status.HTTP_404_NOT_FOUND,
            )

        # Send confirmation message to the user
        msg = "User is verified... You can reset your pin now!"

        text_content = render_to_string(
            template_name="empty_email.html",
            context={
                "custom_text": f"Dear {user.first_name},<br><br>{msg}.",
                "support_email": "support@picadailys.com",
                "picadailys_phone": [
                    "02012271894",
                    "02012271895",
                    "08134032631",
                ],
            },
        )

        Messaging.send_email(
            email=user.email,
            html_content=text_content,
            subject="Admin Verify OTP",
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
        encrypted_response = encrypt(verified_response)
        return Response(data=encrypted_response, status=status.HTTP_200_OK)


@extend_schema(
    summary="Reset admin PIN",
    tags=["Admin"],
    description="Sets a new PIN for the admin identified by admin_id. Both pin and pin2 must match.",
    request=AdminResetPinSerializer,
    responses={
        200: inline_serializer(
            "RolesResetPinResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        400: inline_serializer("RolesResetPinError", fields={"error": s.CharField()}),
    },
)
class ResetPin(generics.CreateAPIView):
    serializer_class = AdminResetPinSerializer

    def create(self, request):
        decrypted_payload = decrypt(request.data)
        payload = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_payload.items()
        }
        serializer = self.get_serializer(data=payload)
        if not serializer.is_valid(raise_exception=True):
            return Response(
                data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST
            )

        user_data = serializer.validated_data
        admin_id = payload.get("admin_id")

        try:
            user = User.objects.get(id=admin_id)
            logger.info(f"User found for ID: {user.id}")
        except User.DoesNotExist:
            logger.error(f"Admin not found with ID: {admin_id}")
            return Response(
                data=encrypt({"status": "fail", "message": "Admin not found"}),
                status=status.HTTP_404_NOT_FOUND,
            )

        if user_data.get("pin") != user_data.get("pin2"):
            logger.warning("Pins do not match for Admin ID: %s", admin_id)
            return Response(
                data=encrypt({"error": "Pins do not match!"}),
                status=status.HTTP_400_BAD_REQUEST,
            )

        password = user_data.get("pin")
        user.admin_pin = make_password(password)

        user_token = payload.get("refresh_token")
        if user_token:
            token = RefreshToken(user_token)
            token.blacklist()

        user.save()

        full_name = (
            user.full_name
            or f"{user.first_name or ''} {user.last_name or ''}".strip()
            or user.phone_number
            or user.email
        )

        ActivityModel.objects.create(
            user=user,
            title="Admin Pin Reset.",
            description=f"{full_name} reset their pin.",
        )

        response = {"status": "success", "message": "Pin reset successfully"}
        encrypted_response = encrypt(response)
        return Response(data=encrypted_response, status=status.HTTP_200_OK)


@extend_schema(
    summary="Add a role to an admin user",
    tags=["Admin"],
    description="Assigns an additional role to an existing admin user. Requires the SuperAdmin's PIN for confirmation.",
    request=AddRoleToAdminSerializer,
    responses={
        200: inline_serializer(
            "AddRoleToAdminResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "new_role": s.CharField(),
            },
        ),
        401: inline_serializer(
            "AddRoleToAdminUnauthorized",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class AddRoleToAdmin(generics.GenericAPIView):
    serializer_class = AddRoleToAdminSerializer
    permission_classes = (IsAuthenticated, IsSuperAdmin)

    def post(self, request):
        """Add a role to an admin."""
        decrypted_payload = decrypt(request.data)
        email = decrypted_payload.get("email")
        pin = decrypted_payload.get("pin")
        logger.info("Received request to add role for email: %s", email)

        is_user = User.objects.filter(email=email).first()
        if not is_user:
            logger.warning("User  not found for email: %s", email)
            return Response(
                data=encrypt("User  not found."), status=status.HTTP_404_NOT_FOUND
            )

        new_role = decrypted_payload.get("role")
        logger.info("Checking if user already has the role: %s", new_role)

        # Check if the role already exists
        if AccountType.objects.filter(user=is_user, user_type=new_role).exists():
            logger.warning("User  already has the role: %s", new_role)
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": f"User  already has {new_role} as part of their roles.",
                        "role": new_role,
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        if (
            request.user.agent_pin_locked_until
            and request.user.agent_pin_locked_until > timezone.now()
        ):
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "Too many wrong pin attempts. Try again later.",
                    }
                ),
                status=status.HTTP_403_FORBIDDEN,
            )
        if not request.user.admin_pin or not check_password(
            password=pin, encoded=request.user.admin_pin
        ):
            request.user.agent_pin_attempts = (request.user.agent_pin_attempts or 0) + 1
            if request.user.agent_pin_attempts >= 4:
                request.user.agent_pin_locked_until = timezone.now() + timedelta(
                    minutes=30
                )
                request.user.save(
                    update_fields=["agent_pin_attempts", "agent_pin_locked_until"]
                )
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "message": "Too many wrong pin attempts. Locked for 30 minutes.",
                        }
                    ),
                    status=status.HTTP_403_FORBIDDEN,
                )
            else:
                request.user.save(update_fields=["agent_pin_attempts"])
                return Response(
                    data=encrypt({"status": "fail", "message": "Incorrect pin"}),
                    status=status.HTTP_401_UNAUTHORIZED,
                )
        # Reset attempts on success
        if request.user.agent_pin_attempts:
            request.user.agent_pin_attempts = 0
            request.user.agent_pin_locked_until = None
            request.user.save(
                update_fields=["agent_pin_attempts", "agent_pin_locked_until"]
            )
        if request.user.admin_pin and check_password(
            password=pin, encoded=request.user.admin_pin
        ):
            # Add the role
            AccountType.objects.create(user=is_user, user_type=new_role)
            logger.info("Role '%s' assigned to user: %s", new_role, is_user.email)

            UserNotification.objects.create(
                user=is_user,
                title="Updated Admin Role.",
                message=f"'{new_role}' has been added to your Admin's roles.",
            )
            logger.info("User  notification created for user: %s", is_user.email)

            ActivityModel.objects.create(
                user=is_user,
                title="Admin Role Updated.",
                description=f"Admin, {is_user.full_name} assigned new role: {new_role}.",
            )
            logger.info(
                "Activity logged for user: %s with new role: %s",
                is_user.email,
                new_role,
            )

            return Response(
                data=encrypt(
                    {
                        "status": "success",
                        "message": f"'{new_role}' assigned to the user.",
                        "new_role": new_role,
                    }
                ),
                status=status.HTTP_200_OK,
            )
        else:
            logger.warning(
                "Incorrect pin provided for user: %s %s",
                request.user.first_name,
                request.user.last_name,
            )
            return Response(
                data=encrypt({"status": "fail", "error": "Incorrect pin"}),
                status=status.HTTP_401_UNAUTHORIZED,
            )


@extend_schema(
    summary="Remove a role from an admin user",
    tags=["Admin"],
    description="Removes a specified role from an admin user. Requires the SuperAdmin's PIN for confirmation.",
    request=RemoveRoleFromAdminSerializer,
    responses={
        200: inline_serializer(
            "RemoveAdminRoleResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "removed_role": s.CharField(),
            },
        ),
        401: inline_serializer(
            "RemoveAdminRoleUnauthorized",
            fields={"status": s.CharField(), "error": s.CharField()},
        ),
    },
)
class RemoveAdminRole(generics.GenericAPIView):
    serializer_class = RemoveRoleFromAdminSerializer
    permission_classes = (IsAuthenticated, IsSuperAdmin)

    def delete(self, request):
        """Remove a role from an admin."""
        decrypted_payload = decrypt(request.data)
        email = decrypted_payload.get("email")
        pin = decrypted_payload.get("pin")
        logger.info("Received request to remove role for email: %s", email)

        is_user = User.objects.filter(email=email).first()
        if not is_user:
            logger.warning("User not found for email: %s", email)
            return Response(
                data=encrypt("User  not found."), status=status.HTTP_404_NOT_FOUND
            )

        role_to_remove = decrypted_payload.get("role_to_remove")
        logger.info("Attempting to remove role: %s for user: %s", role_to_remove, email)

        # Check if the role exists for the user
        account_type_instance = AccountType.objects.filter(
            user=is_user, user_type=role_to_remove
        ).first()

        from datetime import timedelta

        if (
            request.user.agent_pin_locked_until
            and request.user.agent_pin_locked_until > timezone.now()
        ):
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "Too many wrong pin attempts. Try again later.",
                    }
                ),
                status=status.HTTP_403_FORBIDDEN,
            )
        if not request.user.admin_pin or not check_password(
            password=pin, encoded=request.user.admin_pin
        ):
            request.user.agent_pin_attempts = (request.user.agent_pin_attempts or 0) + 1
            if request.user.agent_pin_attempts >= 4:
                request.user.agent_pin_locked_until = timezone.now() + timedelta(
                    minutes=30
                )
                request.user.save(
                    update_fields=["agent_pin_attempts", "agent_pin_locked_until"]
                )
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "message": "Too many wrong pin attempts. Locked for 30 minutes.",
                        }
                    ),
                    status=status.HTTP_403_FORBIDDEN,
                )
            else:
                request.user.save(update_fields=["agent_pin_attempts"])
                return Response(
                    data=encrypt({"status": "fail", "error": "Incorrect pin"}),
                    status=status.HTTP_401_UNAUTHORIZED,
                )
        # Reset attempts on success
        if request.user.agent_pin_attempts:
            request.user.agent_pin_attempts = 0
            request.user.agent_pin_locked_until = None
            request.user.save(
                update_fields=["agent_pin_attempts", "agent_pin_locked_until"]
            )
        if not account_type_instance:
            logger.warning("Role '%s' not found for user: %s", role_to_remove, email)
            return Response(
                data=encrypt("Role not found for the user."),
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Remove the role
        account_type_instance.delete()
        logger.info("Role '%s' removed for user: %s", role_to_remove, email)

        UserNotification.objects.create(
            user=is_user,
            title="Role Removed",
            message=f"The role '{role_to_remove}' has been removed from your account.",
        )
        logger.info(
            "User  notification created for user: %s regarding role removal", email
        )

        ActivityModel.objects.create(
            user=is_user,
            title="Role Removed",
            description=f"'{role_to_remove}' has been removed as part of Admin, {is_user.full_name} roles.",
        )
        logger.info(
            "Activity logged for user: %s with removed role: %s",
            email,
            role_to_remove,
        )

        return Response(
            data=encrypt(
                {
                    "status": "success",
                    "message": f"Role '{role_to_remove}' removed successfully.",
                    "removed_role": role_to_remove,
                }
            ),
            status=status.HTTP_200_OK,
        )


@extend_schema(
    summary="Disable an admin user account",
    tags=["Admin"],
    description="Disables an admin account by email, preventing login. Requires the SuperAdmin's PIN for confirmation.",
    request=DisableAdminSerializer,
    responses={
        200: inline_serializer(
            "DisableAdminroleResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        401: inline_serializer(
            "DisableAdminroleUnauthorized",
            fields={"status": s.CharField(), "error": s.CharField()},
        ),
    },
)
class DisableAdminrole(APIView):
    """
    DisableAdminrole handles the POST request of disabling
    an admin user.
    """

    queryset = User.objects.all()
    serializer_class = DisableAdminSerializer
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def post(self, request, *args, **kwargs):
        decrypted_payload = decrypt(request.data)
        payload = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_payload.items()
        }
        email = payload.get("email")
        pin = payload.get("pin")
        logger.info("Received request to disable admin for email: %s", email)

        try:
            user = User.objects.filter(Q(email=email)).first()

            if user is None:
                logger.warning("Admin with email '%s' does not exist.", email)
                return Response(
                    data=encrypt(f"Admin with '{email}' does not exist."),
                    status=status.HTTP_404_NOT_FOUND,
                )

            from datetime import timedelta

            if (
                request.user.agent_pin_locked_until
                and request.user.agent_pin_locked_until > timezone.now()
            ):
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "message": "Too many wrong pin attempts. Try again later.",
                        }
                    ),
                    status=status.HTTP_403_FORBIDDEN,
                )
            if not request.user.admin_pin or not check_password(
                password=pin, encoded=request.user.admin_pin
            ):
                request.user.agent_pin_attempts = (
                    request.user.agent_pin_attempts or 0
                ) + 1
                if request.user.agent_pin_attempts >= 4:
                    request.user.agent_pin_locked_until = timezone.now() + timedelta(
                        minutes=30
                    )
                    request.user.save(
                        update_fields=["agent_pin_attempts", "agent_pin_locked_until"]
                    )
                    return Response(
                        data=encrypt(
                            {
                                "status": "fail",
                                "message": "Too many wrong pin attempts. Locked for 30 minutes.",
                            }
                        ),
                        status=status.HTTP_403_FORBIDDEN,
                    )
                else:
                    request.user.save(update_fields=["agent_pin_attempts"])
                    return Response(
                        data=encrypt({"status": "fail", "error": "Incorrect pin"}),
                        status=status.HTTP_401_UNAUTHORIZED,
                    )
            # Reset attempts on success
            if request.user.agent_pin_attempts:
                request.user.agent_pin_attempts = 0
                request.user.agent_pin_locked_until = None
                request.user.save(
                    update_fields=["agent_pin_attempts", "agent_pin_locked_until"]
                )
            user.is_admin_disabled = True
            user.save()
            cache.delete_many(["all_admin_users", "admin_users_by_role"])
            logger.info("Admin account for '%s' has been disabled.", email)

            UserNotification.objects.create(
                user=user,
                title="Disable Admin.",
                message="Your account has been disabled!.",
            )
            logger.info("User  notification created for admin '%s'.", email)

            ActivityModel.objects.create(
                user=request.user,
                title="Disable Admin.",
                description=f"Admin user, {user.full_name} disabled.",
            )
            logger.info("Activity logged for disabling admin '%s'.", user.full_name)

            resp = {
                "status": "success",
                "message": "Admin disabled successfully",
                "data": user.is_admin_disabled,
            }
            return Response(data=encrypt(resp), status=status.HTTP_200_OK)

        except Exception as e:
            logger.error("An error occurred while disabling admin: %s", str(e))
            return Response(
                data=encrypt({"status": "fail", "error": "An error occurred."}),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


@extend_schema(
    summary="Re-enable a disabled admin user account",
    tags=["Admin"],
    description="Re-enables a previously disabled admin account. Requires the SuperAdmin's PIN for confirmation.",
    request=EnableAdminSerializer,
    responses={
        200: inline_serializer(
            "EnableAdminroleResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        401: inline_serializer(
            "EnableAdminroleUnauthorized",
            fields={"status": s.CharField(), "error": s.CharField()},
        ),
    },
)
class EnableAdminrole(generics.RetrieveUpdateAPIView):
    """
    EnableAdminrole handles the POST request of re-enabling
    a disabled admin user.
    """

    queryset = User.objects.all()
    serializer_class = EnableAdminSerializer
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def post(self, request, *args, **kwargs):
        decrypted_payload = decrypt(request.data)
        payload = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_payload.items()
        }
        email = payload.get("email")
        pin = payload.get("pin")
        logger.info("Received request to re-enable admin for email: %s", email)

        try:
            user = User.objects.filter(Q(email=email)).first()

            if user is None:
                logger.warning("Admin with email '%s' does not exist.", email)
                return Response(
                    data=encrypt(f"Admin with '{email}' does not exist."),
                    status=status.HTTP_404_NOT_FOUND,
                )

            from datetime import timedelta

            if (
                request.user.agent_pin_locked_until
                and request.user.agent_pin_locked_until > timezone.now()
            ):
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "message": "Too many wrong pin attempts. Try again later.",
                        }
                    ),
                    status=status.HTTP_403_FORBIDDEN,
                )
            if not request.user.admin_pin or not check_password(
                password=pin, encoded=request.user.admin_pin
            ):
                request.user.agent_pin_attempts = (
                    request.user.agent_pin_attempts or 0
                ) + 1
                if request.user.agent_pin_attempts >= 4:
                    request.user.agent_pin_locked_until = timezone.now() + timedelta(
                        minutes=30
                    )
                    request.user.save(
                        update_fields=["agent_pin_attempts", "agent_pin_locked_until"]
                    )
                    return Response(
                        data=encrypt(
                            {
                                "status": "fail",
                                "message": "Too many wrong pin attempts. Locked for 30 minutes.",
                            }
                        ),
                        status=status.HTTP_403_FORBIDDEN,
                    )
                else:
                    request.user.save(update_fields=["agent_pin_attempts"])
                    return Response(
                        data=encrypt({"status": "fail", "error": "Incorrect pin"}),
                        status=status.HTTP_401_UNAUTHORIZED,
                    )
            # Reset attempts on success
            if request.user.agent_pin_attempts:
                request.user.agent_pin_attempts = 0
                request.user.agent_pin_locked_until = None
                request.user.save(
                    update_fields=["agent_pin_attempts", "agent_pin_locked_until"]
                )
            user.is_admin_disabled = False
            user.save()
            cache.delete_many(["all_admin_users", "admin_users_by_role"])
            logger.info("Admin account for '%s' has been re-enabled.", email)

            UserNotification.objects.create(
                user=user,
                title="Re-Enable Admin.",
                message="Your account has been re-enabled successfully.",
            )
            logger.info("User  notification created for admin '%s'.", email)

            ActivityModel.objects.create(
                user=request.user,
                title="Re-Enable Admin.",
                description=f"Admin user, {user.full_name} was re-enabled.",
            )
            logger.info("Activity logged for re-enabling admin '%s'.", user.full_name)

            resp = {
                "status": "success",
                "message": "Admin re-enabled successfully",
                "data": user.is_admin_disabled,
            }
            return Response(data=encrypt(resp), status=status.HTTP_200_OK)

        except Exception as e:
            logger.error("An error occurred while re-enabling admin: %s", str(e))
            return Response(
                data=encrypt({"status": "fail", "error": "An error occurred."}),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


@extend_schema(
    summary="Delete an admin user",
    tags=["Admin"],
    description="Permanently deletes an admin user account by email or ID. Requires the SuperAdmin's PIN and sends a deletion notification.",
    request=AdminDeletionSerializer,
    responses={
        204: inline_serializer(
            "DeleteAdminResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        401: inline_serializer(
            "DeleteAdminUnauthorized",
            fields={"status": s.CharField(), "error": s.CharField()},
        ),
    },
)
class DeleteAdmin(generics.GenericAPIView):
    serializer_class = AdminDeletionSerializer
    permission_classes = (IsAuthenticated, IsSuperAdmin)

    def post(self, request, *args, **kwargs):
        decrypted_payload = decrypt(request.data)
        serializer = self.serializer_class(data=decrypted_payload)
        if serializer.is_valid(raise_exception=True):
            email = serializer.validated_data.get("email")
            pin = serializer.validated_data.get("pin")
            logger.info("Received request to delete admin for email: %s", email)

            try:
                user = User.objects.get(email=email)
                logger.info("Admin user found: %s", user.full_name)

                from datetime import timedelta

                if (
                    request.user.agent_pin_locked_until
                    and request.user.agent_pin_locked_until > timezone.now()
                ):
                    return Response(
                        data=encrypt(
                            {
                                "status": "fail",
                                "message": "Too many wrong pin attempts. Try again later.",
                            }
                        ),
                        status=status.HTTP_403_FORBIDDEN,
                    )
                if not request.user.admin_pin or not check_password(
                    password=pin, encoded=request.user.admin_pin
                ):
                    request.user.agent_pin_attempts = (
                        request.user.agent_pin_attempts or 0
                    ) + 1
                    if request.user.agent_pin_attempts >= 4:
                        request.user.agent_pin_locked_until = (
                            timezone.now() + timedelta(minutes=30)
                        )
                        request.user.save(
                            update_fields=[
                                "agent_pin_attempts",
                                "agent_pin_locked_until",
                            ]
                        )
                        return Response(
                            data=encrypt(
                                {
                                    "status": "fail",
                                    "message": "Too many wrong pin attempts. Locked for 30 minutes.",
                                }
                            ),
                            status=status.HTTP_403_FORBIDDEN,
                        )
                    else:
                        request.user.save(update_fields=["agent_pin_attempts"])
                        return Response(
                            data=encrypt({"status": "fail", "error": "Incorrect pin"}),
                            status=status.HTTP_401_UNAUTHORIZED,
                        )
                # Reset attempts on success
                if request.user.agent_pin_attempts:
                    request.user.agent_pin_attempts = 0
                    request.user.agent_pin_locked_until = None
                    request.user.save(
                        update_fields=["agent_pin_attempts", "agent_pin_locked_until"]
                    )

                # Capture before deletion
                deleted_name = user.full_name or user.first_name
                deleted_email = user.email

                user.delete()
                cache.delete_many(["all_admin_users", "admin_users_by_role"])
                logger.info("Admin user '%s' deleted successfully.", deleted_name)

                ActivityModel.objects.create(
                    user=request.user,
                    title="Delete Admin.",
                    description=f"Admin user, {deleted_name} deleted successfully.",
                )
                logger.info("Activity logged for deleting admin: %s", deleted_name)

                text_content = render_to_string(
                    template_name="empty_email.html",
                    context={
                        "custom_text": f"Dear {deleted_name},<br><br>Your admin account has been deleted.",
                        "support_email": "support@picadailys.com",
                        "picadailys_phone": [
                            "02012271894",
                            "02012271895",
                            "08134032631",
                        ],
                    },
                )

                Messaging.send_email(
                    email=deleted_email,
                    sender_email="notifications@picadailys.com",
                    html_content=text_content,
                    subject="Admin Deletion",
                    body="Your admin account has been deleted",
                )

                return Response(
                    data=encrypt(
                        {
                            "status": "success",
                            "message": f"Admin with '{email}' deleted successfully.",
                        }
                    ),
                    status=status.HTTP_200_OK,
                )
            except User.DoesNotExist:
                logger.warning("Admin with email '%s' does not exist.", email)
                return Response(
                    data=encrypt(f"Admin with '{email}' does not exist."),
                    status=status.HTTP_404_NOT_FOUND,
                )
        else:
            logger.error("Serializer validation failed: %s", serializer.errors)
            return Response(
                data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST
            )


@extend_schema(
    summary="List all verified users",
    tags=["Admin"],
    description="Returns a paginated list of all platform users that have completed phone/email verification.",
    responses={200: GetUserSerializer(many=True)},
)
class VerifiedUsersCount(generics.ListAPIView):
    """
    VerifiedUsersCount is the GET request to retrieve the count
    of all verified users.
    """

    serializer_class = GetUserSerializer
    permission_classes = (IsAuthenticated, IsSuperAdmin, IsNotDisabled)
    pagination_class = PaginationStyle

    def get_queryset(self):
        return User.objects.filter(is_verified=True, is_member=True).order_by("id")

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)

        if page is not None:
            serialized_users = self.get_serializer(page, many=True)
            return Response(
                data=encrypt(
                    {
                        "status": "success",
                        "message": "Verified users retrieved successfully",
                        "verified_users_count": queryset.count(),
                        "verified_users": serialized_users.data,
                    }
                ),
                status=status.HTTP_200_OK,
            )


@extend_schema(
    summary="List all verified partner users",
    tags=["Admin"],
    description="Returns a paginated list of users whose business has been verified on the platform.",
    responses={200: PartnerProfileSerializer(many=True)},
)
class VerifiedPartnersCount(generics.ListAPIView):
    """
    VerifiedPartnersCount is the GET request to retrieve the count
    of all verified Partners.
    """

    serializer_class = PartnerProfileSerializer
    permission_classes = (IsAuthenticated, IsSuperAdmin, IsNotDisabled)
    pagination_class = PaginationStyle

    def get_queryset(self):
        return User.objects.filter(business_verified=True).order_by("created_at")

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)

        if page is not None:
            serialized_users = self.get_serializer(page, many=True)
            return Response(
                data=encrypt(
                    {
                        "status": "success",
                        "message": "Verified Partners retrieved successfully",
                        "verified_business_count": queryset.count(),
                        "verified_businesses": serialized_users.data,
                    }
                ),
                status=status.HTTP_200_OK,
            )


@extend_schema(
    summary="List all promoted brand ad users",
    tags=["Admin"],
    description="Returns a paginated list of users that have run at least one promoted brand ad campaign.",
    responses={200: BrandAdProfileSerializers(many=True)},
)
class VerifiedBrandAdsCount(generics.ListAPIView):
    """
    VerifiedBrandAdsCount is the GET request to retrieve the count
    of all verified promoted brandads.
    """

    serializer_class = BrandAdProfileSerializers
    permission_classes = (IsAuthenticated, IsSuperAdmin, IsNotDisabled)
    pagination_class = PaginationStyle

    def get_queryset(self):
        return User.objects.filter(has_promoted=True).order_by("created_at")

    def list(self, request, *args, **kwargs):
        logger.info("Accessing VerifiedBrandAdsCount view.")
        queryset = self.get_queryset()
        promoted_ads_count = queryset.count()
        logger.info("Number of promoted ads retrieved: %d", promoted_ads_count)

        page = self.paginate_queryset(queryset)

        if page is not None:
            serialized_users = self.get_serializer(page, many=True)
            logger.info("Successfully serialized promoted ads.")
            return Response(
                data=encrypt(
                    {
                        "status": "success",
                        "message": "Promoted Ads retrieved successfully",
                        "promotedAds_count": promoted_ads_count,
                        "promotedAds": serialized_users.data,
                    }
                ),
                status=status.HTTP_200_OK,
            )
        else:
            logger.warning("No promoted ads found for pagination.")
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "No promoted ads found.",
                        "promotedAds_count": promoted_ads_count,
                        "promotedAds": [],
                    }
                ),
                status=status.HTTP_200_OK,
            )


@extend_schema(
    summary="List all admin users",
    tags=["Admin"],
    description="Returns a paginated list of all admin users with counts for active and disabled accounts.",
    responses={200: ListAdminSerializer(many=True)},
)
class GetAllAdminUsers(generics.ListAPIView):
    """
    GetAllAdminUsers is the GET request to retrieve the count
    of all admin users.
    """

    queryset = User.objects.all()
    serializer_class = ListAdminSerializer
    permission_classes = (IsAuthenticated, IsSuperAdmin)
    pagination_class = PaginationStyle

    def get_queryset(self):
        logger.info("Retrieving admin users.")
        admin_users = (
            User.objects.filter(account_types__user_type__icontains="Admin")
            .distinct()
            .order_by("id")
        )
        logger.info("Admin users retrieved successfully.")
        return admin_users

    def list(self, request, *args, **kwargs):
        cache_key = "all_admin_users"
        cached_response = cache.get(cache_key)

        if cached_response:
            logger.info("Returning cached admin users list")
            return Response(data=encrypt(cached_response), status=status.HTTP_200_OK)

        logger.info("Accessing admin users list view.")
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        active_admin_count = queryset.filter(is_admin_disabled=False).count()
        disabled_admin_count = queryset.filter(is_admin_disabled=True).count()

        logger.info("Count of active admin users: %d", active_admin_count)
        logger.info("Count of disabled admin users: %d", disabled_admin_count)

        if page is not None:
            serialized_users = self.get_serializer(page, many=True)
            logger.info("Admin users serialized successfully.")
            response_data = {
                "status": "success",
                "message": "All admin users retrieved successfully",
                "num_of_admin_users": queryset.count(),
                "num_of_active_admin_users": active_admin_count,
                "num_of_disabled_admin_users": disabled_admin_count,
                "admin_users": serialized_users.data,
            }
            cache.set(cache_key, response_data, timeout=900)
            return Response(
                data=encrypt(response_data),
                status=status.HTTP_200_OK,
            )
        else:
            logger.warning("No admin users found for pagination.")
            response_data = {
                "status": "success",
                "message": "No admin users found.",
                "num_of_admin_users": queryset.count(),
                "num_of_active_admin_users": active_admin_count,
                "num_of_disabled_admin_users": disabled_admin_count,
                "admin_users": [],
            }
            return Response(
                data=encrypt(response_data),
                status=status.HTTP_200_OK,
            )


@extend_schema(
    summary="List admin users grouped by role type",
    tags=["Admin"],
    description="Returns a count of admin users broken down by each admin role type.",
    responses={
        200: inline_serializer(
            "AdminUserTypesResponse",
            fields={"status": s.CharField(), "admin_role_counts": s.DictField()},
        )
    },
)
class GetAllAdminUsersTypes(generics.ListAPIView):
    """
    GetAllAdminUsersTypes is the GET request to retrieve the count
    of all admin users, grouped by each admin role.
    """

    queryset = User.objects.all()
    serializer_class = ListAdminSerializer
    permission_classes = (IsAuthenticated, IsSuperAdmin)
    pagination_class = PaginationStyle

    def get_queryset(self):
        return (
            User.objects.filter(account_types__user_type__icontains="Admin")
            .distinct()
            .order_by("account_types__created_at")
        )

    def list(self, request, *args, **kwargs):
        cache_key = "admin_users_by_role"
        cached_response = cache.get(cache_key)

        if cached_response:
            logger.info("Returning cached admin users grouped by role")
            return Response(data=encrypt(cached_response), status=status.HTTP_200_OK)

        queryset = self.get_queryset()

        # Count the number of admins by each role
        role_counts = (
            queryset.values("account_types__user_type")  # Changed from accounttype
            .annotate(role_count=Count("id"))
            .order_by("account_types__user_type")  # Changed from accounttype
        )

        # Transform role counts into a dictionary
        role_counts_dict = {
            role["account_types__user_type"]: role["role_count"]
            for role in role_counts  # Changed from accounttype
        }

        response_data = {
            "status": "success",
            "message": "All admin users retrieved successfully",
            "num_of_admin_users": queryset.count(),
            "admin_role_counts": role_counts_dict,
        }

        # Save to cache (short TTL)
        cache.set(cache_key, response_data, timeout=1000)  # 16.67 minutes

        return Response(data=encrypt(response_data), status=status.HTTP_200_OK)


@extend_schema(
    summary="List all wallet statuses",
    tags=["Admin"],
    description="Returns the status and balance of every wallet on the platform for wallet admins.",
    responses={200: WalletStatusSerializer(many=True)},
)
class GetAllWalletStatus(generics.ListAPIView):
    """
    GetAllWalletStatus is the GET request to retrieve the status
    of all wallets, including balance and activation status.
    """

    queryset = WalletModel.objects.all()
    serializer_class = WalletStatusSerializer
    permission_classes = (IsAuthenticated, IsWalletAdminOrSuperAdmin)

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serialized_wallets = self.get_serializer(queryset, many=True)

        return Response(
            data=encrypt(
                {
                    "status": "success",
                    "message": "Wallet statuses retrieved successfully",
                    "wallet_statuses": serialized_wallets.data,
                }
            ),
            status=status.HTTP_200_OK,
        )


@extend_schema(
    summary="List all wallet admin users",
    tags=["Admin"],
    description="Returns a paginated list of users with the WalletAdmin role.",
    responses={200: ListAdminSerializer(many=True)},
)
class GetAllWalletAdminUsers(generics.ListAPIView):
    """
    GetAllWalletAdminUsers is the GET request to retrieve the count
    of all wallet admin users.
    """

    queryset = User.objects.all()
    serializer_class = ListAdminSerializer
    permission_classes = (IsAuthenticated, IsSuperAdmin)
    pagination_class = PaginationStyle

    def get_queryset(self):
        wallet_admin_users = (
            User.objects.filter(
                account_types__user_type__icontains="WalletAdmin"
            )  # Changed
            .distinct()
            .order_by("account_types__created_at")  # Changed
        )
        return wallet_admin_users

    def list(self, request, *args, **kwargs):
        cache_key = "admin_users_by_role"
        cached_response = cache.get(cache_key)

        if cached_response:
            logger.info("Returning cached wallet admin users list")
            return Response(data=encrypt(cached_response), status=status.HTTP_200_OK)

        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)

        if page is not None:
            serialized_users = self.get_serializer(page, many=True)
            response_data = {
                "status": "success",
                "message": "All wallet admin users retrieved successfully",
                "num_of_wallet_admin_users": queryset.count(),
                "wallet_admin_users": serialized_users.data,
            }
            # Save to cache (short TTL)
            cache.set(cache_key, response_data, timeout=1000)
            return Response(data=encrypt(response_data), status=status.HTTP_200_OK)


@extend_schema(
    summary="Switch active admin role",
    tags=["Admin"],
    description="Allows an admin with multiple roles to switch their active role to another one they have been assigned.",
    request=SwitchRolesSerializers,
    responses={
        200: inline_serializer(
            "SwitchRolesResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "data": s.CharField(),
            },
        ),
        400: inline_serializer(
            "SwitchRolesError",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class SwitchRoles(generics.RetrieveAPIView):
    """
    SwitchRoles is the PUT request method for updating and switching
    amongst assigned admin roles.
    """

    serializer_class = SwitchRolesSerializers
    permission_classes = (IsAuthenticated, IsAdmin)

    def get_object(self):
        return self.request.user

    def put(self, request):
        logger.info("Received request to switch roles.")

        # Process the incoming request data
        decrypted_payload = decrypt(request.data)
        payload = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_payload.items()
        }
        logger.debug("Processed payload.")

        current_user = self.get_object()
        logger.info(
            f"Processing role switch for user: {current_user.full_name} (ID: {current_user.id})"
        )

        new_role = payload.get("user_type")
        logger.debug(f"Requested new role: {new_role}")

        serializer = SwitchRolesSerializers(data=payload)
        if serializer.is_valid(raise_exception=True):
            try:
                account_types = AccountType.objects.filter(user=current_user)
                logger.debug(
                    f"Found account types for user: {account_types.values_list('user_type', flat=True)}"
                )

                # Check if the user has the role they want to switch to
                if not account_types.filter(user_type=new_role).exists():
                    logger.warning(
                        f"User {current_user.full_name} does not have the role: {new_role}"
                    )
                    data = {
                        "status": "fail",
                        "message": f"Sorry, you have not been assigned the role of {new_role}.",
                        "data": current_user.active_role,
                    }
                    return Response(
                        data=encrypt(data), status=status.HTTP_400_BAD_REQUEST
                    )

            except AccountType.DoesNotExist:
                logger.error(
                    f"AccountType does not exist for user: {current_user.full_name} (ID: {current_user.id})"
                )
                raise exceptions.ValidationError(
                    "AccountType for the user does not exist."
                )

            # Handle case where user is already on the desired role
            if current_user.active_role == new_role:
                logger.info(
                    f"User {current_user.full_name} is already in the role: {new_role}"
                )
                data = {
                    "status": "success",
                    "message": f"You are already on the {new_role} screen.",
                    "data": current_user.active_role,
                }
                return Response(data=encrypt(data), status=status.HTTP_200_OK)

            # Register Admin activity
            try:
                ActivityModel.objects.create(
                    user=current_user,
                    title="Switch Admin Roles.",
                    description=f"Admin user, {current_user.full_name} switched from {current_user.active_role} to {new_role}.",
                )
                logger.info(
                    f"Activity logged for role switch: {current_user.full_name} switched to {new_role}."
                )
            except Exception as e:
                logger.error(
                    f"Failed to log activity for user {current_user.full_name}: {e}"
                )

            # Switch the user's active role
            current_user.active_role = new_role
            current_user.save()
            logger.info(
                f"User {current_user.full_name}'s role successfully switched to: {new_role}"
            )

            data = {
                "status": "success",
                "message": f"Account type switched to {new_role} successfully.",
                "data": current_user.active_role,
            }
            return Response(data=encrypt(data), status=status.HTTP_200_OK)
        else:
            logger.warning(
                f"Validation errors for role switch request: {serializer.errors}"
            )
            return Response(
                data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST
            )


@extend_schema(
    summary="Get admin profile image",
    tags=["Admin"],
    description="Returns the URL of the currently authenticated admin's profile picture.",
    responses={
        200: inline_serializer(
            "GetProfileImageResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "image": s.CharField(),
            },
        )
    },
)
class GetProfileImage(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        user = request.user.profile_img_url
        if user:
            response = {
                "status": "success",
                "message": "Profile picture retrived successfully",
                "image": request.user.profile_img_url,
            }
            return Response(
                data=encrypt(response),
                status=status.HTTP_200_OK,
            )
        else:
            response = {
                "status": "fail",
                "message": "User has not uploaded a profile picture.",
                "image": request.user.profile_img_url,
            }
            return Response(
                data=encrypt(response),
                status=status.HTTP_200_OK,
            )


@extend_schema(
    summary="List all app (non-admin) activity logs",
    tags=["Admin"],
    description="Returns paginated activity logs generated by regular app users (Members, Partners, BrandAds).",
    responses={200: GetAllActivityLogsSerializer(many=True)},
)
class GetAllAppActivites(generics.ListAPIView):
    """
    GetAllAdminActivities is the GET request handler that allows the SuperAdmin to
    receive all app activity logs.
    """

    permission_classes = (IsAuthenticated, IsSuperAdmin)
    serializer_class = GetAllActivityLogsSerializer
    pagination_class = CustomPageNumberPagination

    def list(self, request, *args, **kwargs):
        logger.info("Fetching app activity logs.")

        # Define non-admin roles (adjust these based on your application's logic)
        non_admin_roles = {"User", "Member", "Partner", "BrandAd"}
        logger.debug(f"Filtering activities for non-admin roles: {non_admin_roles}")

        try:
            activities = ActivityModel.objects.filter(
                user__active_role__in=non_admin_roles
            ).order_by("-created_at")
            logger.debug(f"Found {activities.count()} activities matching criteria.")
        except Exception as e:
            logger.error(f"Error fetching activities: {e}")
            return Response(
                data=encrypt(
                    {"status": "fail", "message": "Error fetching activity logs."}
                ),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Paginate the activities
        paginator = self.pagination_class()
        try:
            paginated_activities = paginator.paginate_queryset(activities, request)
            logger.info(
                f"Paginated activities: page {paginator.page.number}, size {paginator.page.paginator.per_page}"
            )
        except Exception as e:
            logger.error(f"Pagination error: {e}")
            return Response(
                data=encrypt({"status": "fail", "message": "Error during pagination."}),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Prepare response data
        data = []
        for activity in paginated_activities:
            authorised_by = (
                f"{activity.user.first_name} {activity.user.last_name}"
                if activity.user
                else "Unknown"
            )
            logger.debug(
                f"Processed activity ID {activity.id}: authorised_by={authorised_by}"
            )
            encrypted_activity = {
                "activity_id": str(activity.id),
                "authorised_by": authorised_by,
                "role": activity.user.active_role,
                "title": activity.title,
                "description": activity.description,
                "created_at": (
                    activity.created_at.isoformat() if activity.created_at else None
                ),
                "last_login": (
                    activity.user.last_login.isoformat()
                    if activity.user.last_login
                    else None
                ),
            }
            data.append(encrypted_activity)

        response = encrypt(
            {
                "status": "success",
                "message": "App activity logs fetched successfully!",
                "page": paginator.page.number,
                "page_size": paginator.page.paginator.per_page,
                "total_count": paginator.page.paginator.count,
                "data": data,
            }
        )
        logger.info("Activity logs fetched and prepared for response.")

        return Response(data=response, status=status.HTTP_200_OK)


@extend_schema(
    summary="List all admin activity logs",
    tags=["Admin"],
    description="Returns paginated activity logs for all admin-role actions, including the name of the admin who performed each action.",
    responses={200: GetAllActivityLogsSerializer(many=True)},
)
class GetAllAdminActivites(generics.ListAPIView):
    """
    GetAllAdminActivities is the GET request handler that allows the SuperAdmin to
    receive all activity logs, including the name of the admin user who
    created the activity.
    """

    permission_classes = (IsAuthenticated, IsSuperAdmin)
    serializer_class = GetAllActivityLogsSerializer
    pagination_class = CustomPageNumberPagination

    def get(self, request, *args, **kwargs):
        logger.info("Accessing admin activity logs.")

        # Define admin roles to include only admin logs
        admin_roles = {
            "SuperAdmin",
            "TaskAdmin",
            "AdAdmin",
            "MembersAdmin",
            "User Admin",
            "PartnersAdmin",
            "ContentAdmin",
            "IntegrationAdmin",
            "WalletAdmin",
            "FmcgAdmin",
        }

        # Filter activities based on admin roles
        activities = ActivityModel.objects.filter(
            user__active_role__in=admin_roles
        ).order_by("-created_at")

        logger.info("Total activities found for admin roles: %d", activities.count())

        # Apply pagination
        paginator = self.pagination_class()
        paginated_activities = paginator.paginate_queryset(activities, request)

        logger.info("Paginated activities: %d", len(paginated_activities))

        # Prepare response data
        data = []
        for activity in paginated_activities:
            authorised_by = (
                activity.user.full_name
                if activity.user and activity.user.full_name
                else activity.user.email if activity.user else "Unknown"
            )
            data.append(
                {
                    "activity_id": str(activity.id),
                    "authorised_by": authorised_by,
                    "role": activity.user.active_role,
                    "title": activity.title,
                    "description": activity.description,
                    "created_at": (
                        activity.created_at.isoformat() if activity.created_at else None
                    ),
                    "last_login": (
                        activity.user.last_login.isoformat()
                        if activity.user.last_login
                        else None
                    ),
                }
            )

        # Custom response with pagination metadata
        response = {
            "status": "success",
            "message": "Admin activity logs fetched successfully!",
            "page": paginator.page.number,
            "page_size": paginator.page.paginator.per_page,
            "total_count": paginator.page.paginator.count,
            "data": data,
        }

        logger.info(
            "Returning response with %d activities on page %d.",
            len(data),
            paginator.page.number,
        )
        return Response(data=encrypt(response), status=status.HTTP_200_OK)


@extend_schema(
    summary="Get a single activity log by ID",
    tags=["Admin"],
    description="Retrieves the details of a specific activity log entry identified by its UUID.",
    responses={
        200: inline_serializer(
            "GetSingleAdminActivityResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "data": s.DictField(),
            },
        ),
        404: inline_serializer(
            "GetSingleAdminActivityNotFound",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class GetSingleAdminActivity(generics.RetrieveAPIView):
    """
    GetSingleAdminActivity is the GET request handler that allows a SuperAdmin to
    check a specific admin activity log.
    """

    queryset = ActivityModel.objects.all()
    serializer_class = GetAllActivityLogsSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "activity_id"

    def retrieve(self, request, *args, **kwargs):
        logger.info("Accessing retrieve activity log endpoint.")

        activity_id = kwargs.get("activity_id")
        logger.debug("Requested activity ID: %s", activity_id)

        try:
            activity = ActivityModel.objects.get(id=activity_id)
            logger.info("Activity log found: %s", activity)

            authorised_by = (
                "Superuser"
                if activity.user.active_role == "Superuser"
                else (
                    activity.user.full_name
                    if activity.user.active_role
                    in {
                        "SuperAdmin",
                        "TaskAdmin",
                        "AdAdmin",
                        "MembersAdmin",
                        "User Admin",
                        "PartnersAdmin",
                        "ContentAdmin",
                        "IntegrationAdmin",
                        "WalletAdmin",
                        "FmcgAdmin",
                    }
                    else (
                        activity.user.first_name + " " + activity.user.last_name
                        if activity.user.active_role
                        in {
                            "User ",
                            "Member",
                            "Partner",
                            "BrandAd",
                        }
                        else "Unknown"
                    )
                )
            )

            # Prepare the response data
            response = {
                "status": "success",
                "message": "Activity log retrieved successfully!",
                "title": activity.title,
                "data": {
                    "activity_id": str(activity_id),
                    "description": activity.description,
                    "profile_image_url": activity.user.profile_img_url,
                    "email": activity.user.email,
                    "authorised_by": authorised_by,
                    "role": activity.user.active_role,
                    "created_at": (
                        activity.created_at.isoformat() if activity.created_at else None
                    ),
                    "last_login": (
                        activity.user.last_login.isoformat()
                        if activity.user.last_login
                        else None
                    ),
                },
            }
            logger.info(
                "Response prepared successfully for activity ID: %s", activity_id
            )
            return Response(data=encrypt(response), status=status.HTTP_200_OK)

        except ActivityModel.DoesNotExist:
            logger.error("Activity log not found for ID: %s", activity_id)
            return Response(
                data=encrypt({"status": "fail", "message": "Activity log not found."}),
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as e:
            logger.exception(
                "An error occurred while retrieving activity log: %s", str(e)
            )
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "An error occurred while retrieving the activity log.",
                    }
                ),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


@extend_schema(
    summary="List all activity logs for a specific admin user",
    tags=["Admin"],
    description="Returns all activity log entries for the admin user identified by email address.",
    responses={
        200: inline_serializer(
            "GetAllSingleAdminUserActivityResponse",
            fields={"status": s.CharField(), "data": s.ListField()},
        ),
        404: inline_serializer(
            "GetAllSingleAdminUserActivityNotFound",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class GetAllSingleAdminUserActivity(generics.ListAPIView):
    """
    GetAllSingleAdminUserActivity is the GET request handler that allows a SuperAdmin to
    check a specific admin activity log for a single Admin user.
    """

    queryset = ActivityModel.objects.all()
    serializer_class = GetAllActivityLogsSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "email"

    def get_queryset(self):
        admin_email = self.kwargs["email"]
        logger.debug("Fetching activities for admin email: %s", admin_email)

        try:
            user = User.objects.get(email=admin_email)
            logger.info("User  found: %s", user)
            return ActivityModel.objects.filter(user=user).order_by("-created_at")
        except User.DoesNotExist:
            logger.warning("User  with email %s does not exist.", admin_email)
            return ActivityModel.objects.none()

    def list(self, request, *args, **kwargs):
        logger.info(
            "Accessing list of activity logs for admin email: %s", kwargs["email"]
        )

        queryset = self.get_queryset()

        if not queryset.exists():
            logger.info("No activity logs found for admin email: %s", kwargs["email"])
            return Response(
                data=encrypt({"status": "fail", "message": "Activity log not found."}),
                status=status.HTTP_404_NOT_FOUND,
            )

        # Prepare response data for all activities
        response_data = []
        for activity in queryset:
            authorised_by = (
                "Superuser"
                if activity.user.active_role == "Superuser"
                else (
                    activity.user.full_name
                    if activity.user.active_role
                    in {
                        "SuperAdmin",
                        "TaskAdmin",
                        "AdAdmin",
                        "MembersAdmin",
                        "User Admin",
                        "PartnersAdmin",
                        "ContentAdmin",
                        "IntegrationAdmin",
                        "WalletAdmin",
                        "FmcgAdmin",
                    }
                    else (
                        activity.user.first_name + " " + activity.user.last_name
                        if activity.user.active_role
                        in {
                            "User ",
                            "Member",
                            "Partner",
                            "BrandAd",
                        }
                        else "Unknown"
                    )
                )
            )
            response_data.append(
                {
                    "activity_id": str(activity.id),
                    "title": activity.title,
                    "description": activity.description,
                    "authorised_by": authorised_by,
                    "role": activity.user.active_role,
                    "created_at": (
                        activity.created_at.isoformat() if activity.created_at else None
                    ),
                    "last_login": (
                        activity.user.last_login.isoformat()
                        if activity.user.last_login
                        else None
                    ),
                }
            )

        response = {
            "status": "success",
            "message": "Activity logs retrieved successfully!",
            "data": response_data,
        }
        logger.info(
            "Successfully retrieved %d activity logs for admin email: %s",
            len(response_data),
            kwargs["email"],
        )
        return Response(data=encrypt(response), status=status.HTTP_200_OK)


@extend_schema(
    summary="List available admin role types",
    tags=["Admin"],
    description="Returns the full list of available admin role types defined in the system.",
    responses={
        200: inline_serializer(
            "AdminTypesListResponse",
            fields={
                "status": s.CharField(),
                "categories": s.ListField(child=s.CharField()),
            },
        )
    },
)
class AdminTypesListView(APIView):
    """
    AdminTypesListView is the GET request handler that returns a list of admin types.
    """

    permission_classes = (IsAuthenticated, IsSuperAdmin)

    def get(self, request):
        cache_key = "admin_types_list"
        response_data = cache.get(cache_key)

        if not response_data:
            admin_types = [admin_type[1] for admin_type in ADMIN_TYPES]
            response_data = {
                "status": "success.",
                "message": "Admin types retrieved successfully.",
                "categories": admin_types,
            }
            cache.set(cache_key, response_data, timeout=None)  # cache forever

        return Response(data=encrypt(response_data), status=status.HTTP_200_OK)


@extend_schema(
    summary="List all unique activity log titles",
    tags=["Admin"],
    description="Returns distinct admin and non-admin activity log titles, useful for filtering the activity feed.",
    responses={
        200: inline_serializer(
            "ActivityTitleListResponse",
            fields={
                "status": s.CharField(),
                "admin_titles": s.ListField(),
                "non_admin_titles": s.ListField(),
            },
        )
    },
)
class ActivityTitleListView(APIView):
    """
    Retrieve all unique activity titles.
    """

    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get(self, request, *args, **kwargs):
        logger.info("Accessing the get method to fetch unique activity titles.")

        # Define admin roles based on user type choices
        admin_roles = {
            "SuperAdmin",
            "TaskAdmin",
            "AdAdmin",
            "MembersAdmin",
            "User Admin",
            "PartnersAdmin",
            "ContentAdmin",
            "IntegrationAdmin",
            "WalletAdmin",
            "FmcgAdmin",
        }
        logger.debug("Defined admin roles: %s", admin_roles)

        try:
            # Filter titles based on the user type through AccountType model
            admin_titles = (
                ActivityModel.objects.filter(
                    Q(user__account_types__user_type__in=admin_roles)
                )
                .values_list("title", flat=True)
                .distinct()
            )
            logger.info("Fetched %d unique admin titles.", admin_titles.count())
            non_admin_titles = (
                ActivityModel.objects.exclude(
                    Q(user__account_types__user_type__in=admin_roles)
                )
                .values_list("title", flat=True)
                .distinct()
            )
            logger.info("Fetched %d unique non-admin titles.", non_admin_titles.count())

            # Prepare the response containing unique admin and non-admin activity titles
            response = {
                "status": "success",
                "message": "All unique activity titles fetched successfully!",
                "admin_titles": list(admin_titles),
                "non_admin_titles": list(non_admin_titles),
            }
            logger.info(
                "Response prepared successfully with admin and non-admin titles."
            )
            return Response(data=encrypt(response), status=status.HTTP_200_OK)

        except Exception as e:
            logger.exception(
                "An error occurred while fetching activity titles: %s", str(e)
            )
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "An error occurred while fetching activity titles.",
                    }
                ),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


@extend_schema(
    summary="Get admin dashboard summary data",
    tags=["Admin"],
    description="Returns aggregated platform statistics for the admin dashboard, including user counts, ticket counts, and cashflow breakdown.",
    responses={200: AdminDdashboardDataSerializer},
)
class AdminDashboardDataView(APIView):
    serializer_class = AdminDdashboardDataSerializer
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get(self, request):
        today = timezone.now().date()
        ADMIN_ROLES = [
            "AdAdmin",
            "SuperAdmin",
            "TaskAdmin",
            "MembersAdmin",
            "UserAdmin",
            "PartnersAdmin",
            "ContentAdmin",
            "IntegrationAdmin",
            "WalletAdmin",
        ]

        # --- Cashflow (income activity) calculations ---
        now = timezone.now()
        start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start_of_week = start_of_today - timedelta(days=start_of_today.weekday())
        start_of_month = start_of_today.replace(day=1)
        start_of_year = start_of_today.replace(month=1, day=1)

        def get_transfer_sum(start, end, direction=None):
            # Outbound only - TransferModel never carries an inbound row, see
            # roles.analytics.get_transfer_sum's docstring. Inbound uses
            # get_inbound_credit_sum (imported above) instead.
            qs = TransferModel.objects.filter(created_at__gte=start, created_at__lt=end)
            if direction == "outbound":
                qs = qs.filter(
                    Q(transaction_type__in=["OUTBOUND", "DEBIT"])
                    | Q(
                        transaction_type="INTRA_BANK",
                        sender_account_number__isnull=False,
                    )
                )
            return qs.aggregate(total=Sum("amount")).get("total") or 0

        def get_card_deposit_sum(start, end):
            return (
                FundWithCard.objects.filter(
                    created_at__gte=start, created_at__lt=end, amount__isnull=False
                )
                .aggregate(total=Sum("amount"))
                .get("total")
                or 0
            )

        def get_bill_payment_sum(start, end):
            bills = ValueAddedServices.objects.filter(
                created_at__gte=start,
                created_at__lt=end,
                status__in=["successful", "paid", "success", "pending"],
            )
            # Cast amount to float for aggregation
            return (
                bills.annotate(amount_float=Cast("amount", FloatField()))
                .aggregate(total=models.Sum("amount_float"))
                .get("total")
                or 0
            )

        def get_cashflow(start, end):
            inbound = get_inbound_credit_sum(start, end)
            outbound = get_transfer_sum(start, end, direction="outbound")
            card_deposit = get_card_deposit_sum(start, end)
            bill_payments = get_bill_payment_sum(start, end)
            return {
                "inbound": float(inbound),
                "outbound": float(outbound),
                "card_deposit": float(card_deposit),
                "bill_payments": float(bill_payments),
                "net": float(inbound)
                + float(card_deposit)
                - float(outbound)
                - float(bill_payments),
            }

        cashflow = {
            "daily": get_cashflow(start_of_today, now),
            "weekly": get_cashflow(start_of_week, now),
            "monthly": get_cashflow(start_of_month, now),
            "yearly": get_cashflow(start_of_year, now),
        }

        data = {
            "total_wallet_users": User.objects.filter(has_wallet=True).count(),
            "total_partners": User.objects.filter(account_types__user_type="Partner")
            .distinct()
            .count(),
            "total_brand_ads": User.objects.filter(account_types__user_type="BrandAd")
            .distinct()
            .count(),
            "total_admins": User.objects.filter(active_role__in=ADMIN_ROLES).count(),
            "total_active_admins": User.objects.filter(
                active_role__in=ADMIN_ROLES, is_admin_disabled=False
            ).count(),
            "total_disabled_admins": User.objects.filter(
                is_admin_disabled=True
            ).count(),
            "total_verified_users": User.objects.filter(
                is_verified=True, is_member=True
            ).count(),
            "total_verified_partners": User.objects.filter(business_verified=True)
            .distinct()
            .count(),
            "total_verified_brandAds": User.objects.filter(has_promoted=True).count(),
            "total_support_tickets": Ticket.objects.count(),
            "total_live_tickets": Ticket.objects.exclude(
                status__in=["Resolved", "Closed"]
            ).count(),
            "total_closed_tickets": Ticket.objects.filter(status="Closed").count(),
            "total_logins": User.objects.filter(last_login__date=today).count(),
            "cashflow": cashflow,
        }

        serializer = AdminDdashboardDataSerializer(data)
        response_data = {
            "status": "success",
            "data": serializer.data,
        }
        return Response(encrypt(response_data), status=status.HTTP_200_OK)


# ==========================================
# Public / User-facing Knowledge Base endpoints
# ==========================================


@extend_schema(
    summary="List knowledge base articles",
    tags=["Knowledge Base"],
    description="Returns a paginated list of knowledge base articles. Supports filtering by section, content_type, and category.",
    parameters=[
        OpenApiParameter(
            name="section",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            description="Filter articles by section (Airtime & Data, Electricity, Cable TV, Banking, Brand Ads, Partners)",
            required=False,
        ),
        OpenApiParameter(
            name="content_type",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            description="Filter articles by content type (Website, Social Post, Email)",
            required=False,
        ),
        OpenApiParameter(
            name="category",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            description="Filter articles by category",
            required=False,
        ),
        OpenApiParameter(
            name="page",
            type=OpenApiTypes.INT,
            location=OpenApiParameter.QUERY,
            description="Page number for pagination",
            required=False,
        ),
        OpenApiParameter(
            name="page_size",
            type=OpenApiTypes.INT,
            location=OpenApiParameter.QUERY,
            description="Number of results per page (max 50)",
            required=False,
        ),
    ],
    responses={
        200: inline_serializer(
            "KnowledgeBaseListResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "data": s.DictField(),
            },
        ),
        400: inline_serializer(
            "KnowledgeBaseListError",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class KnowledgeBaseListView(StandardResponseMixin, generics.ListAPIView):
    """
    GET /knowledge-base/

    Public knowledge base listing. Returns paginated articles.
    Supports `section`, `content_type`, and `category` filters.
    """

    serializer_class = KnowledgeBaseListSerializer
    permission_classes = [AllowAny]
    pagination_class = Pagination

    def get_queryset(self):
        qs = knowledgeBaseModel.objects.all().order_by("-created_at")

        section = self.request.query_params.get("section")
        if section:
            qs = qs.filter(section__iexact=section)

        content_type = self.request.query_params.get("content_type")
        if content_type:
            qs = qs.filter(content_type__iexact=content_type)

        category = self.request.query_params.get("category")
        if category:
            qs = qs.filter(category__iexact=category)

        return qs

    def list(self, request, *args, **kwargs):
        logger.info(
            "Public knowledge base list requested. Filters: %s",
            dict(request.query_params),
        )
        return self.paginated_response(
            self.get_queryset(),
            KnowledgeBaseListSerializer,
            request,
            "Knowledge base articles retrieved successfully.",
        )


@extend_schema(
    summary="Retrieve a single knowledge base article",
    tags=["Knowledge Base"],
    description="Retrieves a single knowledge base article by ID. Returns 404 if the article does not exist.",
    parameters=[
        OpenApiParameter(
            name="id",
            type=OpenApiTypes.INT,
            location=OpenApiParameter.PATH,
            description="The ID of the knowledge base article",
            required=True,
        ),
    ],
    responses={
        200: inline_serializer(
            "KnowledgeBaseDetailResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "data": s.DictField(),
            },
        ),
        404: inline_serializer(
            "KnowledgeBaseDetailNotFound",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class KnowledgeBaseDetailView(StandardResponseMixin, generics.RetrieveAPIView):
    """
    GET /knowledge-base/<id>/

    Retrieves a single knowledge base article by ID.
    Returns 404 if the article does not exist.
    """

    serializer_class = KnowledgeBaseDetailSerializer
    permission_classes = [AllowAny]
    lookup_field = "id"

    def get_queryset(self):
        return knowledgeBaseModel.objects.all()

    def retrieve(self, request, *args, **kwargs):
        try:
            article = self.get_queryset().get(id=kwargs["id"])
        except knowledgeBaseModel.DoesNotExist:
            logger.info("Knowledge base article not found: id=%s", kwargs["id"])
            return self.error_response(
                message="Knowledge base article not found.",
                status_code=status.HTTP_404_NOT_FOUND,
                should_encrypt=False,
            )

        data = KnowledgeBaseDetailSerializer(article).data
        return self.success_response(
            message="Knowledge base article retrieved successfully.",
            data=data,
            should_encrypt=False,
        )


@extend_schema(
    summary="Create a knowledge base entry",
    tags=["Admin"],
    description="Creates a new knowledge base article with optional media uploads. Supports scheduled publishing.",
    request=AdminKnowledgeBaseSerializer,
    responses={
        201: inline_serializer(
            "CreateKnowledgeBaseResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        400: inline_serializer(
            "CreateKnowledgeBaseError", fields={"status": s.CharField()}
        ),
    },
)
class CreateKnowledgeBaseView(generics.GenericAPIView):
    serializer_class = AdminKnowledgeBaseSerializer
    permission_classes = [IsAuthenticated, IsAdmin]
    parser_classes = [MultiPartParser, JSONParser]

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid(raise_exception=True):
            entry = serializer.save()
            ActivityModel.objects.create(
                user=request.user,
                title="Create Knowledge Base Entry",
                description=f"Admin {request.user.active_role} created knowledge base entry: {entry.caption}.",
            )
            return Response(
                data=encrypt(
                    {
                        "status": "success",
                        "message": "Entry created successfully.",
                        "data": serializer.data,
                    }
                ),
                status=status.HTTP_201_CREATED,
            )
        return Response(
            data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST
        )


@extend_schema(
    summary="List all knowledge base entries",
    tags=["Admin"],
    description="Returns a paginated list of knowledge base articles, filterable by category, section, and content type.",
    responses={200: AdminKnowledgeBaseSerializer(many=True)},
)
class AdminKnowledgeBaseListView(generics.ListAPIView):
    serializer_class = AdminKnowledgeBaseSerializer
    permission_classes = [IsAuthenticated, IsAdmin]
    pagination_class = PaginationStyle

    def get_queryset(self):
        qs = knowledgeBaseModel.objects.all().order_by("-created_at")
        category = self.request.query_params.get("category")
        section = self.request.query_params.get("section")
        content_type = self.request.query_params.get("content_type")
        if category:
            qs = qs.filter(category__icontains=category)
        if section:
            qs = qs.filter(section__icontains=section)
        if content_type:
            qs = qs.filter(content_type__icontains=content_type)
        return qs

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return Response(
                data=encrypt(
                    {
                        "status": "success",
                        "count": queryset.count(),
                        "data": serializer.data,
                    }
                ),
                status=status.HTTP_200_OK,
            )
        serializer = self.get_serializer(queryset, many=True)
        return Response(
            data=encrypt(
                {
                    "status": "success",
                    "count": queryset.count(),
                    "data": serializer.data,
                }
            ),
            status=status.HTTP_200_OK,
        )


@extend_schema(
    summary="Retrieve, update or delete a knowledge base entry",
    tags=["Admin"],
    description="GET retrieves, PATCH partially updates, and DELETE removes a specific knowledge base entry by primary key.",
    responses={
        200: AdminKnowledgeBaseSerializer,
        404: inline_serializer(
            "KnowledgeBaseDetailNotFound",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class AdminKnowledgeBaseDetailView(generics.GenericAPIView):
    serializer_class = AdminKnowledgeBaseSerializer
    permission_classes = [IsAuthenticated, IsAdmin]
    parser_classes = [MultiPartParser, JSONParser]

    def get_object(self, pk):
        try:
            return knowledgeBaseModel.objects.get(pk=pk)
        except knowledgeBaseModel.DoesNotExist:
            return None

    def get(self, request, pk):
        entry = self.get_object(pk)
        if not entry:
            return Response(
                data=encrypt({"status": "fail", "message": "Entry not found."}),
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = self.serializer_class(entry)
        return Response(
            data=encrypt({"status": "success", "data": serializer.data}),
            status=status.HTTP_200_OK,
        )

    def patch(self, request, pk):
        entry = self.get_object(pk)
        if not entry:
            return Response(
                data=encrypt({"status": "fail", "message": "Entry not found."}),
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = self.serializer_class(entry, data=request.data, partial=True)
        if serializer.is_valid(raise_exception=True):
            serializer.save()
            ActivityModel.objects.create(
                user=request.user,
                title="Update Knowledge Base Entry",
                description=f"Admin {request.user.active_role} updated knowledge base entry ID: {pk}.",
            )
            return Response(
                data=encrypt(
                    {
                        "status": "success",
                        "message": "Entry updated successfully.",
                        "data": serializer.data,
                    }
                ),
                status=status.HTTP_200_OK,
            )
        return Response(
            data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST
        )

    def delete(self, request, pk):
        entry = self.get_object(pk)
        if not entry:
            return Response(
                data=encrypt({"status": "fail", "message": "Entry not found."}),
                status=status.HTTP_404_NOT_FOUND,
            )
        caption = entry.caption
        entry.delete()
        ActivityModel.objects.create(
            user=request.user,
            title="Delete Knowledge Base Entry",
            description=f"Admin {request.user.active_role} deleted knowledge base entry: {caption}.",
        )
        return Response(
            data=encrypt(
                {"status": "success", "message": "Entry deleted successfully."}
            ),
            status=status.HTTP_204_NO_CONTENT,
        )


@extend_schema(
    summary="Gamification dashboard data",
    tags=["Admin"],
    description=(
        "Returns all stats needed for the Gamification admin dashboard: summary cards, "
        "weekly Task vs Campaign chart, and In App / Brand Task breakdowns. "
        "Accepts optional `start_date` and `end_date` query params (YYYY-MM-DD) for the "
        "date-range panel and chart; defaults to the current calendar week."
    ),
    parameters=[
        OpenApiParameter(
            "start_date", OpenApiTypes.DATE, OpenApiParameter.QUERY, required=False
        ),
        OpenApiParameter(
            "end_date", OpenApiTypes.DATE, OpenApiParameter.QUERY, required=False
        ),
    ],
    responses={
        200: inline_serializer(
            "GamificationDashboardResponse",
            fields={"status": s.CharField(), "data": s.DictField()},
        )
    },
)
class GamificationDashboardView(APIView):
    permission_classes = [IsAuthenticated, IsTaskAdminOrSuperAdmin]

    def get(self, request):

        now = timezone.now()
        today = now.date()

        raw_start = request.query_params.get("start_date")
        raw_end = request.query_params.get("end_date")

        try:
            start_date = (
                datetime.strptime(raw_start, "%Y-%m-%d").date()
                if raw_start
                else today - timedelta(days=today.weekday())
            )
            end_date = (
                datetime.strptime(raw_end, "%Y-%m-%d").date() if raw_end else today
            )
        except ValueError:
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "Invalid date format. Use YYYY-MM-DD.",
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ── Summary cards ────────────────────────────────────────────────────
        total_rewards = User.objects.aggregate(total=Sum("total_points"))["total"] or 0

        active_tasks = (
            SocialTask.objects.filter(is_active=True)
            .exclude(expires_at__lt=now)
            .count()
        )

        verif_qs = TaskSubmission.objects
        task_verif = {
            "total": verif_qs.count(),
            "pending": verif_qs.filter(status="Pending").count(),
            "approved": verif_qs.filter(status="Approved").count(),
            "rejected": verif_qs.filter(status="Rejected").count(),
        }

        brand_task_total = CreateAd.objects.count()

        # ── Weekly chart: Task vs Campaign per day ───────────────────────────
        days_in_range = (end_date - start_date).days + 1
        chart = []
        for i in range(min(days_in_range, 7)):
            day = start_date + timedelta(days=i)
            chart.append(
                {
                    "day": day.strftime("%A"),
                    "date": day.isoformat(),
                    "tasks": SocialTask.objects.filter(created_at__date=day).count(),
                    "campaigns": StreakChallenge.objects.filter(
                        created_at__date=day
                    ).count(),
                }
            )

        # ── In App (StreakChallenge) — reward_points × participant_cap ───────
        def streak_reward_total(qs):
            return (
                qs.annotate(cap=F("participant_cap")).aggregate(
                    total=Sum(F("reward_points") * F("participant_cap"))
                )["total"]
                or 0
            )

        sc_active = StreakChallenge.objects.filter(
            is_active=True,
            is_cancelled=False,
            is_paused=False,
            start_date__lte=end_date,
            end_date__gte=start_date,
        )
        sc_scheduled = StreakChallenge.objects.filter(
            is_cancelled=False, start_date__gt=now
        )
        sc_expired = StreakChallenge.objects.filter(
            is_cancelled=False, end_date__lt=now
        )
        sc_cancelled = StreakChallenge.objects.filter(is_cancelled=True)

        in_app = {
            "active": streak_reward_total(sc_active),
            "scheduled": streak_reward_total(sc_scheduled),
            "expired": streak_reward_total(sc_expired),
            "cancelled": streak_reward_total(sc_cancelled),
        }

        # ── Brand Task (CreateAd) — reward_points × slot_cap ────────────────
        def ad_reward_total(qs):
            return (
                qs.aggregate(total=Sum(F("reward_points") * F("slot_cap")))["total"]
                or 0
            )

        ad_active = CreateAd.objects.filter(is_active=True, expiry_date__gt=now)
        ad_expired = CreateAd.objects.filter(
            Q(expiry_date__lt=now) | Q(is_active=False)
        )
        ad_watch = CreateAd.objects.filter(
            task_type="watch_video", is_active=True, expiry_date__gt=now
        )

        brand_task = {
            "verification_requests": BrandTaskSubmission.objects.filter(
                status="Pending"
            ).count(),
            "active": ad_reward_total(ad_active),
            "expired": ad_reward_total(ad_expired),
            "watch_videos": ad_reward_total(ad_watch),
        }

        return Response(
            data=encrypt(
                {
                    "status": "success",
                    "data": {
                        "date_range": {
                            "start": start_date.isoformat(),
                            "end": end_date.isoformat(),
                        },
                        "summary": {
                            "total_rewards_distributed": total_rewards,
                            "active_tasks": active_tasks,
                            "task_verifications": task_verif,
                            "brand_task_creation": brand_task_total,
                        },
                        "chart": chart,
                        "in_app": in_app,
                        "brand_task": brand_task,
                    },
                }
            ),
            status=status.HTTP_200_OK,
        )


@extend_schema(
    summary="Income Activity dashboard data",
    tags=["Admin"],
    description=(
        "Returns cash inflow/outflow, card deposits, VAS bill payments, "
        "self-service + partner-service revenue, and gamification (points "
        "redeemed to wallet) for a selected period, each with a "
        "period-over-period trend badge (value/change_pct/direction, "
        "or label='New' when there's no prior-period baseline to compare "
        "against). Pass `granularity` (daily/weekly/monthly/quarterly/yearly, "
        "default weekly) or an explicit `start_date`/`end_date` range - the "
        "prior period compared against is always the immediately preceding "
        "period of equal length, not a fixed calendar unit."
    ),
    parameters=[
        OpenApiParameter(
            "granularity",
            OpenApiTypes.STR,
            OpenApiParameter.QUERY,
            required=False,
            description=f"One of {GRANULARITY_CHOICES}. Ignored if start_date/end_date are passed.",
        ),
        OpenApiParameter(
            "start_date", OpenApiTypes.DATE, OpenApiParameter.QUERY, required=False
        ),
        OpenApiParameter(
            "end_date", OpenApiTypes.DATE, OpenApiParameter.QUERY, required=False
        ),
    ],
    responses={
        200: inline_serializer(
            "IncomeActivityDashboardResponse",
            fields={"status": s.CharField(), "data": s.DictField()},
        ),
        400: inline_serializer(
            "IncomeActivityDashboardError",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class IncomeActivityDashboardView(APIView):
    """
    Separate from AdminDashboardDataView by design - this endpoint is scoped
    to the Income Activity panel only (one date range in, one set of KPI
    tiles out), so the frontend can refresh it independently of the rest of
    the dashboard.
    """

    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get(self, request):
        granularity = request.query_params.get("granularity", "weekly")
        raw_start = request.query_params.get("start_date")
        raw_end = request.query_params.get("end_date")
        logger.info(
            "IncomeActivityDashboardView query_params: %s", dict(request.query_params)
        )

        try:
            if raw_start and raw_end:
                start_date = datetime.strptime(raw_start, "%Y-%m-%d").date()
                end_date = datetime.strptime(raw_end, "%Y-%m-%d").date()
                current_start, current_end, prior_start, prior_end = resolve_period(
                    start_date=start_date, end_date=end_date
                )
                resolved_granularity = "custom"
            elif granularity in GRANULARITY_CHOICES:
                current_start, current_end, prior_start, prior_end = resolve_period(
                    granularity=granularity
                )
                resolved_granularity = granularity
            else:
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "message": f"Invalid granularity. Use one of {GRANULARITY_CHOICES}, or pass start_date/end_date.",
                        }
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )
        except ValueError:
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "Invalid date format. Use YYYY-MM-DD.",
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        current_snapshot = get_cashflow_snapshot(current_start, current_end)
        prior_snapshot = get_cashflow_snapshot(prior_start, prior_end)

        data = {
            key: compute_trend(current_snapshot[key], prior_snapshot[key])
            for key in current_snapshot
        }

        return Response(
            data=encrypt(
                {
                    "status": "success",
                    "data": {
                        "granularity": resolved_granularity,
                        "date_range": {
                            "start": current_start.date().isoformat(),
                            "end": current_end.date().isoformat(),
                        },
                        **data,
                    },
                }
            ),
            status=status.HTTP_200_OK,
        )


MAX_CHART_RANGE_DAYS = 400


@extend_schema(
    summary="Cash In vs Cash Out chart data",
    tags=["Admin"],
    description=(
        "Returns cash_in/cash_out bucketed by calendar day for the selected "
        "period. Pass `granularity` (daily/weekly/monthly/quarterly/yearly, "
        "default weekly) alone to have it pick the date range too, or an "
        "explicit `start_date`/`end_date` range (capped at "
        f"{MAX_CHART_RANGE_DAYS} days) - `granularity` may still be passed "
        "alongside start_date/end_date purely to control bucket size (e.g. "
        "roll a frontend-computed date range up into months); the date range "
        "always comes from start_date/end_date when both are given. Response "
        "rows are one per calendar day if no granularity is resolved at all. "
        "cash_in is inbound transfers + card deposits; cash_out is outbound "
        "transfers + VAS bill payments + self-service/partner spend."
    ),
    parameters=[
        OpenApiParameter(
            "granularity",
            OpenApiTypes.STR,
            OpenApiParameter.QUERY,
            required=False,
            description=(
                f"One of {GRANULARITY_CHOICES}. Controls the date range when "
                "start_date/end_date aren't passed; when they are, still "
                "controls how the series is bucketed (e.g. start_date/"
                "end_date + granularity=monthly returns one row per month "
                "within that range)."
            ),
        ),
        OpenApiParameter(
            "start_date", OpenApiTypes.DATE, OpenApiParameter.QUERY, required=False
        ),
        OpenApiParameter(
            "end_date", OpenApiTypes.DATE, OpenApiParameter.QUERY, required=False
        ),
    ],
    responses={
        200: inline_serializer(
            "CashInVsCashOutChartResponse",
            fields={"status": s.CharField(), "data": s.DictField()},
        ),
        400: inline_serializer(
            "CashInVsCashOutChartError",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class CashInVsCashOutChartView(APIView):
    """Separate from IncomeActivityDashboardView - this is chart data (a
    series of points), not KPI tiles, so the two can be fetched/cached
    independently. Also backs the Services dashboard's per-tab Cash Flow
    graph / Income vs Expenditure table via the category/service_type
    params - see get_daily_income_expenditure_series."""

    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get(self, request):
        granularity = request.query_params.get("granularity", "weekly")
        raw_start = request.query_params.get("start_date")
        raw_end = request.query_params.get("end_date")
        category = request.query_params.get("category", "all")
        service_type = request.query_params.get("service_type")
        logger.info(
            "CashInVsCashOutChartView query_params: %s", dict(request.query_params)
        )

        if category not in SERVICES_TAB_CHOICES:
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": f"Invalid category. Use one of {SERVICES_TAB_CHOICES}.",
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        valid_service_types = SERVICE_TYPE_CHOICES_BY_CATEGORY.get(category)
        if service_type is not None and (
            valid_service_types is None or service_type not in valid_service_types
        ):
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": (
                            f"service_type is not valid for category={category}. "
                            f"Valid categories for service_type: {list(SERVICE_TYPE_CHOICES_BY_CATEGORY)}."
                        ),
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            if raw_start and raw_end:
                start_date = datetime.strptime(raw_start, "%Y-%m-%d").date()
                end_date = datetime.strptime(raw_end, "%Y-%m-%d").date()
                if (end_date - start_date).days > MAX_CHART_RANGE_DAYS:
                    return Response(
                        data=encrypt(
                            {
                                "status": "fail",
                                "message": f"Range too wide - max {MAX_CHART_RANGE_DAYS} days.",
                            }
                        ),
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                current_start, current_end, _, _ = resolve_period(
                    start_date=start_date, end_date=end_date
                )
                # The date range always comes from start_date/end_date here -
                # but granularity may still be passed alongside them purely
                # to control how the series gets bucketed (see
                # bucket_income_expenditure_series below). Falls back to
                # "custom" (no bucketing, one row per day) if granularity
                # wasn't also passed.
                resolved_granularity = (
                    granularity if granularity in GRANULARITY_CHOICES else "custom"
                )
            elif granularity in GRANULARITY_CHOICES:
                current_start, current_end, _, _ = resolve_period(
                    granularity=granularity
                )
                resolved_granularity = granularity
            else:
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "message": f"Invalid granularity. Use one of {GRANULARITY_CHOICES}, or pass start_date/end_date.",
                        }
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )
        except ValueError:
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "Invalid date format. Use YYYY-MM-DD.",
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        series = get_daily_income_expenditure_series(
            current_start, current_end, category=category, service_type=service_type
        )
        if resolved_granularity in GRANULARITY_CHOICES:
            series = bucket_income_expenditure_series(series, resolved_granularity)

        return Response(
            data=encrypt(
                {
                    "status": "success",
                    "data": {
                        "granularity": resolved_granularity,
                        "date_range": {
                            "start": current_start.date().isoformat(),
                            "end": current_end.date().isoformat(),
                        },
                        "category": category,
                        "service_type": service_type,
                        "series": series,
                    },
                }
            ),
            status=status.HTTP_200_OK,
        )


@extend_schema(
    summary="VAS Income vs Expenditure breakdown",
    tags=["Admin"],
    description=(
        "Row-per-VAS-sub-service variant of the Income vs Expenditure table "
        "for the Services dashboard's VAS tab - Airtime, Data, Electricity "
        "Bill, Cable TV, each with a Credit (successful amount) and Debit "
        "(failed amount) trend badge vs the immediately preceding period of "
        "equal length. Separate from CashInVsCashOutChartView, which stays "
        "day-bucketed for the Cash Flow graph. Electricity Bill/Cable TV are "
        "split from TxModel.description, so periods with purchases made "
        "before this split existed will undercount both rows. Pass "
        "`granularity` (daily/weekly/monthly/quarterly/yearly, default "
        "weekly) or an explicit `start_date`/`end_date` range."
    ),
    parameters=[
        OpenApiParameter(
            "granularity",
            OpenApiTypes.STR,
            OpenApiParameter.QUERY,
            required=False,
            description=f"One of {GRANULARITY_CHOICES}. Ignored if start_date/end_date are passed.",
        ),
        OpenApiParameter(
            "start_date", OpenApiTypes.DATE, OpenApiParameter.QUERY, required=False
        ),
        OpenApiParameter(
            "end_date", OpenApiTypes.DATE, OpenApiParameter.QUERY, required=False
        ),
    ],
    responses={
        200: inline_serializer(
            "VasIncomeExpenditureBreakdownResponse",
            fields={"status": s.CharField(), "data": s.DictField()},
        ),
        400: inline_serializer(
            "VasIncomeExpenditureBreakdownError",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class VasIncomeExpenditureBreakdownView(APIView):
    """Services dashboard, VAS tab: the Income vs Expenditure tile there
    shows one row per sub-service instead of CashInVsCashOutChartView's
    per-day rows - see get_vas_income_expenditure_breakdown."""

    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get(self, request):
        granularity = request.query_params.get("granularity", "weekly")
        raw_start = request.query_params.get("start_date")
        raw_end = request.query_params.get("end_date")

        try:
            if raw_start and raw_end:
                start_date = datetime.strptime(raw_start, "%Y-%m-%d").date()
                end_date = datetime.strptime(raw_end, "%Y-%m-%d").date()
                current_start, current_end, prior_start, prior_end = resolve_period(
                    start_date=start_date, end_date=end_date
                )
                resolved_granularity = "custom"
            elif granularity in GRANULARITY_CHOICES:
                current_start, current_end, prior_start, prior_end = resolve_period(
                    granularity=granularity
                )
                resolved_granularity = granularity
            else:
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "message": f"Invalid granularity. Use one of {GRANULARITY_CHOICES}, or pass start_date/end_date.",
                        }
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )
        except ValueError:
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "Invalid date format. Use YYYY-MM-DD.",
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        rows = get_vas_income_expenditure_breakdown(
            current_start, current_end, prior_start, prior_end
        )

        return Response(
            data=encrypt(
                {
                    "status": "success",
                    "data": {
                        "granularity": resolved_granularity,
                        "date_range": {
                            "start": current_start.date().isoformat(),
                            "end": current_end.date().isoformat(),
                        },
                        "rows": rows,
                    },
                }
            ),
            status=status.HTTP_200_OK,
        )


@extend_schema(
    summary="Services breakdown dashboard data",
    tags=["Admin"],
    description=(
        "Returns revenue for each Services-donut category - VAS, Self "
        "Services, Brand Ads, Partners - each with a trend badge and its "
        "% share of the combined total. Self Services and Partners are a "
        "mutually exclusive split of self-service TxModel revenue by "
        "whether the booking is linked to a specific PartnerServices "
        "listing. vas_cashback is included since VAS is currently the only "
        "category with a real cashback mechanism (CashbackRule) - Self "
        "Services/Brand Ads/Partners have none yet, so no cashback field is "
        "returned for them rather than reporting a misleading 0. Pass "
        "`granularity` (daily/weekly/monthly/quarterly/yearly, default "
        "weekly) or an explicit `start_date`/`end_date` range."
    ),
    parameters=[
        OpenApiParameter(
            "granularity",
            OpenApiTypes.STR,
            OpenApiParameter.QUERY,
            required=False,
            description=f"One of {GRANULARITY_CHOICES}. Ignored if start_date/end_date are passed.",
        ),
        OpenApiParameter(
            "start_date", OpenApiTypes.DATE, OpenApiParameter.QUERY, required=False
        ),
        OpenApiParameter(
            "end_date", OpenApiTypes.DATE, OpenApiParameter.QUERY, required=False
        ),
    ],
    responses={
        200: inline_serializer(
            "ServicesBreakdownResponse",
            fields={"status": s.CharField(), "data": s.DictField()},
        ),
        400: inline_serializer(
            "ServicesBreakdownError",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class ServicesBreakdownView(APIView):
    """Separate from IncomeActivityDashboardView/CashInVsCashOutChartView -
    this is the Services panel (donut + per-category revenue), fetched and
    refreshed independently."""

    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get(self, request):
        granularity = request.query_params.get("granularity", "weekly")
        raw_start = request.query_params.get("start_date")
        raw_end = request.query_params.get("end_date")

        try:
            if raw_start and raw_end:
                start_date = datetime.strptime(raw_start, "%Y-%m-%d").date()
                end_date = datetime.strptime(raw_end, "%Y-%m-%d").date()
                current_start, current_end, prior_start, prior_end = resolve_period(
                    start_date=start_date, end_date=end_date
                )
                resolved_granularity = "custom"
            elif granularity in GRANULARITY_CHOICES:
                current_start, current_end, prior_start, prior_end = resolve_period(
                    granularity=granularity
                )
                resolved_granularity = granularity
            else:
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "message": f"Invalid granularity. Use one of {GRANULARITY_CHOICES}, or pass start_date/end_date.",
                        }
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )
        except ValueError:
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "Invalid date format. Use YYYY-MM-DD.",
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        current_snapshot = get_services_snapshot(current_start, current_end)
        prior_snapshot = get_services_snapshot(prior_start, prior_end)

        category_keys = ["vas", "self_services", "brand_ads", "partners"]
        total = sum(current_snapshot[key] for key in category_keys)

        categories = {}
        for key in category_keys:
            trend = compute_trend(current_snapshot[key], prior_snapshot[key])
            trend["percentage"] = (
                round(current_snapshot[key] / total * 100, 2) if total else 0
            )
            categories[key] = trend

        categories["vas_cashback"] = compute_trend(
            current_snapshot["vas_cashback"], prior_snapshot["vas_cashback"]
        )

        return Response(
            data=encrypt(
                {
                    "status": "success",
                    "data": {
                        "granularity": resolved_granularity,
                        "date_range": {
                            "start": current_start.date().isoformat(),
                            "end": current_end.date().isoformat(),
                        },
                        **categories,
                    },
                }
            ),
            status=status.HTTP_200_OK,
        )


@extend_schema(
    summary="Customer Insight dashboard data",
    tags=["Admin"],
    description=(
        "Returns New/Active/Dormant/Deleted user counts. New and Deleted "
        "are period-scoped (date_joined/deleted_at within the selected "
        "range) with a trend badge. Active/Dormant are current-moment "
        f"snapshots (logged in within the last {ACTIVE_USER_THRESHOLD_DAYS} "
        "days = Active, otherwise Dormant) and have no trend badge - only "
        "the single most recent login is stored, so a past period's active "
        "count can't be reconstructed. Pass `granularity` "
        "(daily/weekly/monthly/quarterly/yearly, default weekly) or an "
        "explicit `start_date`/`end_date` range."
    ),
    parameters=[
        OpenApiParameter(
            "granularity",
            OpenApiTypes.STR,
            OpenApiParameter.QUERY,
            required=False,
            description=f"One of {GRANULARITY_CHOICES}. Ignored if start_date/end_date are passed.",
        ),
        OpenApiParameter(
            "start_date", OpenApiTypes.DATE, OpenApiParameter.QUERY, required=False
        ),
        OpenApiParameter(
            "end_date", OpenApiTypes.DATE, OpenApiParameter.QUERY, required=False
        ),
    ],
    responses={
        200: inline_serializer(
            "CustomerInsightResponse",
            fields={"status": s.CharField(), "data": s.DictField()},
        ),
        400: inline_serializer(
            "CustomerInsightError",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class CustomerInsightView(APIView):
    """Separate from the other dashboard panels - Customer Insight is
    fetched/refreshed independently. Passing `category` switches to the
    Services dashboard tab-specific shape (see
    get_customer_insight_extended) instead of the default New/Active/
    Dormant/Deleted shape."""

    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get(self, request):
        granularity = request.query_params.get("granularity", "weekly")
        raw_start = request.query_params.get("start_date")
        raw_end = request.query_params.get("end_date")
        category = request.query_params.get("category")

        if category is not None and category not in SERVICES_TAB_CHOICES:
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": f"Invalid category. Use one of {SERVICES_TAB_CHOICES}.",
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            if raw_start and raw_end:
                start_date = datetime.strptime(raw_start, "%Y-%m-%d").date()
                end_date = datetime.strptime(raw_end, "%Y-%m-%d").date()
                current_start, current_end, prior_start, prior_end = resolve_period(
                    start_date=start_date, end_date=end_date
                )
                resolved_granularity = "custom"
            elif granularity in GRANULARITY_CHOICES:
                current_start, current_end, prior_start, prior_end = resolve_period(
                    granularity=granularity
                )
                resolved_granularity = granularity
            else:
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "message": f"Invalid granularity. Use one of {GRANULARITY_CHOICES}, or pass start_date/end_date.",
                        }
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )
        except ValueError:
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "Invalid date format. Use YYYY-MM-DD.",
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        if category is not None:
            data = get_customer_insight_extended(
                current_start, current_end, prior_start, prior_end, category=category
            )
        else:
            current_snapshot = get_customer_insight_snapshot(current_start, current_end)
            prior_snapshot = get_customer_insight_snapshot(prior_start, prior_end)
            data = {
                "new_users": compute_trend(
                    current_snapshot["new_users"], prior_snapshot["new_users"]
                ),
                "deleted_users": compute_trend(
                    current_snapshot["deleted_users"],
                    prior_snapshot["deleted_users"],
                ),
                # Snapshots, not period-scoped - no trend badge (see
                # get_customer_insight_snapshot docstring).
                "active_users": {"value": current_snapshot["active_users"]},
                "dormant_users": {"value": current_snapshot["dormant_users"]},
            }

        return Response(
            data=encrypt(
                {
                    "status": "success",
                    "data": {
                        "granularity": resolved_granularity,
                        "date_range": {
                            "start": current_start.date().isoformat(),
                            "end": current_end.date().isoformat(),
                        },
                        **data,
                    },
                }
            ),
            status=status.HTTP_200_OK,
        )


@extend_schema(
    summary="Transaction Overview - Services dashboard",
    tags=["Admin"],
    description=(
        "Successful/duplicate/failed transaction counts + support ticket "
        "count for the Services dashboard tabs. `category` (default "
        f"'all') is one of {SERVICES_TAB_CHOICES}; `service_type` further "
        f"scopes category=vas/self_services - see {SERVICE_TYPE_CHOICES_BY_CATEGORY}. "
        "support_contact is the same across every tab - tickets aren't "
        "tagged by service category in the schema. duplicate_transactions "
        "is always 0 for category=vas - VAS purchases aren't covered by "
        "the duplicate-detection heuristic yet. Pass `granularity` "
        "(daily/weekly/monthly/quarterly/yearly, default weekly) or an "
        "explicit `start_date`/`end_date` range."
    ),
    parameters=[
        OpenApiParameter(
            "granularity",
            OpenApiTypes.STR,
            OpenApiParameter.QUERY,
            required=False,
            description=f"One of {GRANULARITY_CHOICES}. Ignored if start_date/end_date are passed.",
        ),
        OpenApiParameter(
            "start_date", OpenApiTypes.DATE, OpenApiParameter.QUERY, required=False
        ),
        OpenApiParameter(
            "end_date", OpenApiTypes.DATE, OpenApiParameter.QUERY, required=False
        ),
        OpenApiParameter(
            "category",
            OpenApiTypes.STR,
            OpenApiParameter.QUERY,
            required=False,
            description=f"One of {SERVICES_TAB_CHOICES}. Default 'all'.",
        ),
        OpenApiParameter(
            "service_type",
            OpenApiTypes.STR,
            OpenApiParameter.QUERY,
            required=False,
            description=f"Only valid with category=vas or self_services. See {SERVICE_TYPE_CHOICES_BY_CATEGORY}.",
        ),
    ],
    responses={
        200: inline_serializer(
            "TransactionOverviewResponse",
            fields={"status": s.CharField(), "data": s.DictField()},
        ),
        400: inline_serializer(
            "TransactionOverviewError",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class TransactionOverviewView(APIView):
    """Services dashboard's Transaction Overview panel - successful/
    duplicate/failed counts + support contact count, per tab."""

    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get(self, request):
        granularity = request.query_params.get("granularity", "weekly")
        raw_start = request.query_params.get("start_date")
        raw_end = request.query_params.get("end_date")
        category = request.query_params.get("category", "all")
        service_type = request.query_params.get("service_type")

        if category not in SERVICES_TAB_CHOICES:
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": f"Invalid category. Use one of {SERVICES_TAB_CHOICES}.",
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        valid_service_types = SERVICE_TYPE_CHOICES_BY_CATEGORY.get(category)
        if service_type is not None and (
            valid_service_types is None or service_type not in valid_service_types
        ):
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": (
                            f"service_type is not valid for category={category}. "
                            f"Valid categories for service_type: {list(SERVICE_TYPE_CHOICES_BY_CATEGORY)}."
                        ),
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            if raw_start and raw_end:
                start_date = datetime.strptime(raw_start, "%Y-%m-%d").date()
                end_date = datetime.strptime(raw_end, "%Y-%m-%d").date()
                current_start, current_end, _, _ = resolve_period(
                    start_date=start_date, end_date=end_date
                )
                resolved_granularity = "custom"
            elif granularity in GRANULARITY_CHOICES:
                current_start, current_end, _, _ = resolve_period(
                    granularity=granularity
                )
                resolved_granularity = granularity
            else:
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "message": f"Invalid granularity. Use one of {GRANULARITY_CHOICES}, or pass start_date/end_date.",
                        }
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )
        except ValueError:
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "Invalid date format. Use YYYY-MM-DD.",
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        overview = get_transaction_overview_snapshot(
            current_start, current_end, category=category, service_type=service_type
        )

        return Response(
            data=encrypt(
                {
                    "status": "success",
                    "data": {
                        "granularity": resolved_granularity,
                        "date_range": {
                            "start": current_start.date().isoformat(),
                            "end": current_end.date().isoformat(),
                        },
                        "category": category,
                        "service_type": service_type,
                        **overview,
                    },
                }
            ),
            status=status.HTTP_200_OK,
        )


@extend_schema(
    summary="Ads Insight - Brand Adverts services tab",
    tags=["Admin"],
    description=(
        "Created/Ongoing/Expired/Cash Backs breakdown for the Services "
        "dashboard's Brand Adverts tab donut. Not a strict partition - an "
        "ad created in the period can also be ongoing - each is its own "
        "count with a rough percentage-of-total, not a mutually exclusive "
        "share. Cash Backs is always 0 - no ads cashback mechanism exists "
        "in the codebase. Pass `granularity` "
        "(daily/weekly/monthly/quarterly/yearly, default weekly) or an "
        "explicit `start_date`/`end_date` range."
    ),
    parameters=[
        OpenApiParameter(
            "granularity",
            OpenApiTypes.STR,
            OpenApiParameter.QUERY,
            required=False,
            description=f"One of {GRANULARITY_CHOICES}. Ignored if start_date/end_date are passed.",
        ),
        OpenApiParameter(
            "start_date", OpenApiTypes.DATE, OpenApiParameter.QUERY, required=False
        ),
        OpenApiParameter(
            "end_date", OpenApiTypes.DATE, OpenApiParameter.QUERY, required=False
        ),
    ],
    responses={
        200: inline_serializer(
            "AdsInsightResponse",
            fields={"status": s.CharField(), "data": s.DictField()},
        ),
        400: inline_serializer(
            "AdsInsightError",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class AdsInsightView(APIView):
    """Services dashboard's Brand Adverts tab - Ads Insight donut."""

    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get(self, request):
        granularity = request.query_params.get("granularity", "weekly")
        raw_start = request.query_params.get("start_date")
        raw_end = request.query_params.get("end_date")

        try:
            if raw_start and raw_end:
                start_date = datetime.strptime(raw_start, "%Y-%m-%d").date()
                end_date = datetime.strptime(raw_end, "%Y-%m-%d").date()
                current_start, current_end, _, _ = resolve_period(
                    start_date=start_date, end_date=end_date
                )
                resolved_granularity = "custom"
            elif granularity in GRANULARITY_CHOICES:
                current_start, current_end, _, _ = resolve_period(
                    granularity=granularity
                )
                resolved_granularity = granularity
            else:
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "message": f"Invalid granularity. Use one of {GRANULARITY_CHOICES}, or pass start_date/end_date.",
                        }
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )
        except ValueError:
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "Invalid date format. Use YYYY-MM-DD.",
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        ads_insight = get_ads_insight_snapshot(current_start, current_end)

        return Response(
            data=encrypt(
                {
                    "status": "success",
                    "data": {
                        "granularity": resolved_granularity,
                        "date_range": {
                            "start": current_start.date().isoformat(),
                            "end": current_end.date().isoformat(),
                        },
                        **ads_insight,
                    },
                }
            ),
            status=status.HTTP_200_OK,
        )


@extend_schema(
    summary="Alert and Risk dashboard data",
    tags=["Admin"],
    description=(
        "Returns the Alert and Risk panel. pending_settlement is a current "
        "backlog snapshot (transactions stuck in PENDING right now, not "
        "period-scoped). duplicate_transactions is period-scoped with a "
        "trend badge, using a heuristic (same user + tx_type + amount within "
        "a short window counts as a duplicate) since there's no first-class "
        "dedup concept in the schema. reconciliation_differences is "
        "period-scoped with a trend badge, scoped to partner-linked "
        "purchases where the underlying transaction succeeded but the "
        "partner hasn't been marked settled after a grace period (see "
        "PartnerPurchase.settled). fraud_alerts is always 0 - no fraud "
        "ruleset is defined anywhere yet. Each row is drillable - see "
        "the pending-settlement/reconciliation-differences/duplicate-"
        "transactions/fraud-alerts list endpoints. Pass `granularity` "
        "(daily/weekly/monthly/quarterly/yearly, default weekly) or an "
        "explicit `start_date`/`end_date` range."
    ),
    parameters=[
        OpenApiParameter(
            "granularity",
            OpenApiTypes.STR,
            OpenApiParameter.QUERY,
            required=False,
            description=f"One of {GRANULARITY_CHOICES}. Ignored if start_date/end_date are passed.",
        ),
        OpenApiParameter(
            "start_date", OpenApiTypes.DATE, OpenApiParameter.QUERY, required=False
        ),
        OpenApiParameter(
            "end_date", OpenApiTypes.DATE, OpenApiParameter.QUERY, required=False
        ),
    ],
    responses={
        200: inline_serializer(
            "AlertAndRiskResponse",
            fields={"status": s.CharField(), "data": s.DictField()},
        ),
        400: inline_serializer(
            "AlertAndRiskError",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class AlertAndRiskView(APIView):
    """Separate from the other dashboard panels - Alert and Risk is
    fetched/refreshed independently."""

    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get(self, request):
        granularity = request.query_params.get("granularity", "weekly")
        raw_start = request.query_params.get("start_date")
        raw_end = request.query_params.get("end_date")

        try:
            if raw_start and raw_end:
                start_date = datetime.strptime(raw_start, "%Y-%m-%d").date()
                end_date = datetime.strptime(raw_end, "%Y-%m-%d").date()
                current_start, current_end, prior_start, prior_end = resolve_period(
                    start_date=start_date, end_date=end_date
                )
                resolved_granularity = "custom"
            elif granularity in GRANULARITY_CHOICES:
                current_start, current_end, prior_start, prior_end = resolve_period(
                    granularity=granularity
                )
                resolved_granularity = granularity
            else:
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "message": f"Invalid granularity. Use one of {GRANULARITY_CHOICES}, or pass start_date/end_date.",
                        }
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )
        except ValueError:
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "Invalid date format. Use YYYY-MM-DD.",
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        current_duplicates = get_duplicate_transaction_count(current_start, current_end)
        prior_duplicates = get_duplicate_transaction_count(prior_start, prior_end)
        current_reconciliation = get_reconciliation_differences_count(
            current_start, current_end
        )
        prior_reconciliation = get_reconciliation_differences_count(
            prior_start, prior_end
        )

        data = {
            # Snapshot, not period-scoped - no trend badge (see docstring).
            "pending_settlement": {"value": get_pending_settlement_count()},
            "duplicate_transactions": compute_trend(
                current_duplicates, prior_duplicates
            ),
            "reconciliation_differences": compute_trend(
                current_reconciliation, prior_reconciliation
            ),
            # Always 0 - no fraud ruleset exists yet (see get_fraud_alerts_list).
            "fraud_alerts": {"value": 0},
        }

        return Response(
            data=encrypt(
                {
                    "status": "success",
                    "data": {
                        "granularity": resolved_granularity,
                        "date_range": {
                            "start": current_start.date().isoformat(),
                            "end": current_end.date().isoformat(),
                        },
                        **data,
                    },
                }
            ),
            status=status.HTTP_200_OK,
        )


@extend_schema(
    summary="All Transactions dashboard data",
    tags=["Admin"],
    description=(
        "Returns a merged, paginated transaction list spanning TxModel "
        "(self-service, partners, brand ads/UGC, wallet transfers), VAS "
        "(airtime/data/electricity/cable), and FMCG orders - three "
        "differently-shaped models merged and sorted by date in Python, "
        "since none of them share a single ledger table. Pass `granularity` "
        "(daily/weekly/monthly/quarterly/yearly, default weekly) or an "
        "explicit `start_date`/`end_date` range, plus optional `status` and "
        "`category` filters (category is one of: Self Services, Partners, "
        "Brand Ads, Wallet, VAS, FMCG, Other) and `page`/`page_size`."
    ),
    parameters=[
        OpenApiParameter(
            "granularity",
            OpenApiTypes.STR,
            OpenApiParameter.QUERY,
            required=False,
            description=f"One of {GRANULARITY_CHOICES}. Ignored if start_date/end_date are passed.",
        ),
        OpenApiParameter(
            "start_date", OpenApiTypes.DATE, OpenApiParameter.QUERY, required=False
        ),
        OpenApiParameter(
            "end_date", OpenApiTypes.DATE, OpenApiParameter.QUERY, required=False
        ),
        OpenApiParameter(
            "status", OpenApiTypes.STR, OpenApiParameter.QUERY, required=False
        ),
        OpenApiParameter(
            "category", OpenApiTypes.STR, OpenApiParameter.QUERY, required=False
        ),
        OpenApiParameter(
            "page", OpenApiTypes.INT, OpenApiParameter.QUERY, required=False
        ),
        OpenApiParameter(
            "page_size", OpenApiTypes.INT, OpenApiParameter.QUERY, required=False
        ),
    ],
    responses={
        200: inline_serializer(
            "AllTransactionsResponse",
            fields={"status": s.CharField(), "data": s.DictField()},
        ),
        400: inline_serializer(
            "AllTransactionsError",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class AllTransactionsView(APIView):
    """Separate from the other dashboard panels - All Transactions is a raw
    list, not an aggregate, so it's paginated rather than trend-badged."""

    permission_classes = [IsAuthenticated, IsSuperAdmin]
    MAX_PAGE_SIZE = 100

    def get(self, request):
        granularity = request.query_params.get("granularity", "weekly")
        raw_start = request.query_params.get("start_date")
        raw_end = request.query_params.get("end_date")
        status_filter = request.query_params.get("status")
        category_filter = request.query_params.get("category")

        try:
            if raw_start and raw_end:
                start_date = datetime.strptime(raw_start, "%Y-%m-%d").date()
                end_date = datetime.strptime(raw_end, "%Y-%m-%d").date()
                current_start, current_end, _, _ = resolve_period(
                    start_date=start_date, end_date=end_date
                )
                resolved_granularity = "custom"
            elif granularity in GRANULARITY_CHOICES:
                current_start, current_end, _, _ = resolve_period(
                    granularity=granularity
                )
                resolved_granularity = granularity
            else:
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "message": f"Invalid granularity. Use one of {GRANULARITY_CHOICES}, or pass start_date/end_date.",
                        }
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )
        except ValueError:
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "Invalid date format. Use YYYY-MM-DD.",
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            page = max(int(request.query_params.get("page", 1)), 1)
            page_size = min(
                max(int(request.query_params.get("page_size", 20)), 1),
                self.MAX_PAGE_SIZE,
            )
        except ValueError:
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "page and page_size must be integers.",
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        all_rows = get_all_transactions(
            current_start, current_end, status_filter, category_filter
        )
        total = len(all_rows)
        offset = (page - 1) * page_size
        page_rows = all_rows[offset : offset + page_size]

        return Response(
            data=encrypt(
                {
                    "status": "success",
                    "data": {
                        "granularity": resolved_granularity,
                        "date_range": {
                            "start": current_start.date().isoformat(),
                            "end": current_end.date().isoformat(),
                        },
                        "count": total,
                        "page": page,
                        "page_size": page_size,
                        "results": page_rows,
                    },
                }
            ),
            status=status.HTTP_200_OK,
        )


@extend_schema(
    summary="Gamification Picapoints Overview",
    tags=["Admin"],
    description=(
        "Returns Picapoints Created (awarded) and Distributed (redeemed to "
        "wallet) for the selected period, each with a trend badge, plus "
        "average points in circulation - a current snapshot (average "
        "Points.balance across all users), not period-scoped, so no trend "
        "badge. created_naira/distributed_naira are the naira equivalent of "
        "Created/Distributed - distributed_naira is exact (the real amount "
        "credited to wallets by RedeemPointsToWallet); created_naira is an "
        "estimate, since points are a virtual reward until redeemed and "
        "PointTransaction doesn't snapshot the tier rate at award time - "
        "each user's points created are valued at their CURRENT tier rate, "
        "not whatever tier they were on when the points were actually "
        "earned - see get_picapoints_overview_snapshot. auto_boost_points "
        "is returned as null: it exists as a config field on UGC task "
        "creation but nothing in the codebase ever reads it to actually "
        "award points, so there's no real figure to report yet. Pass "
        "`granularity` (daily/weekly/monthly/quarterly/yearly, default "
        "weekly) or an explicit `start_date`/`end_date` range."
    ),
    parameters=[
        OpenApiParameter(
            "granularity",
            OpenApiTypes.STR,
            OpenApiParameter.QUERY,
            required=False,
            description=f"One of {GRANULARITY_CHOICES}. Ignored if start_date/end_date are passed.",
        ),
        OpenApiParameter(
            "start_date", OpenApiTypes.DATE, OpenApiParameter.QUERY, required=False
        ),
        OpenApiParameter(
            "end_date", OpenApiTypes.DATE, OpenApiParameter.QUERY, required=False
        ),
    ],
    responses={
        200: inline_serializer(
            "GamificationPicapointsOverviewResponse",
            fields={"status": s.CharField(), "data": s.DictField()},
        ),
        400: inline_serializer(
            "GamificationPicapointsOverviewError",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class GamificationPicapointsOverviewView(APIView):
    """Separate from the other dashboard panels - Picapoints Overview is
    fetched/refreshed independently."""

    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get(self, request):
        granularity = request.query_params.get("granularity", "weekly")
        raw_start = request.query_params.get("start_date")
        raw_end = request.query_params.get("end_date")

        try:
            if raw_start and raw_end:
                start_date = datetime.strptime(raw_start, "%Y-%m-%d").date()
                end_date = datetime.strptime(raw_end, "%Y-%m-%d").date()
                current_start, current_end, prior_start, prior_end = resolve_period(
                    start_date=start_date, end_date=end_date
                )
                resolved_granularity = "custom"
            elif granularity in GRANULARITY_CHOICES:
                current_start, current_end, prior_start, prior_end = resolve_period(
                    granularity=granularity
                )
                resolved_granularity = granularity
            else:
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "message": f"Invalid granularity. Use one of {GRANULARITY_CHOICES}, or pass start_date/end_date.",
                        }
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )
        except ValueError:
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "Invalid date format. Use YYYY-MM-DD.",
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        current_snapshot = get_picapoints_overview_snapshot(current_start, current_end)
        prior_snapshot = get_picapoints_overview_snapshot(prior_start, prior_end)

        data = {
            "created": compute_trend(
                current_snapshot["created"], prior_snapshot["created"]
            ),
            "created_naira": compute_trend(
                current_snapshot["created_naira"], prior_snapshot["created_naira"]
            ),
            "distributed": compute_trend(
                current_snapshot["distributed"], prior_snapshot["distributed"]
            ),
            "distributed_naira": compute_trend(
                current_snapshot["distributed_naira"],
                prior_snapshot["distributed_naira"],
            ),
            "auto_boost_points": None,
            # Snapshot, not period-scoped - no trend badge (see docstring).
            "avg_points_in_circulation": {
                "value": current_snapshot["avg_points_in_circulation"]
            },
        }

        return Response(
            data=encrypt(
                {
                    "status": "success",
                    "data": {
                        "granularity": resolved_granularity,
                        "date_range": {
                            "start": current_start.date().isoformat(),
                            "end": current_end.date().isoformat(),
                        },
                        **data,
                    },
                }
            ),
            status=status.HTTP_200_OK,
        )


@extend_schema(
    summary="Picapoints Source Breakdown",
    tags=["Admin"],
    description=(
        "PicaPoints Created for the selected period, broken down by "
        "PointTransaction.source (e.g. task_completion, referral, "
        "daily_login, inapp_task, service_purchase, admin_adjustment) - "
        "each with a trend badge vs the immediately preceding period of "
        "equal length and its % share of the period's total points "
        "created. Sources are whatever actually appears in the ledger for "
        "the period, not a fixed list - see get_points_source_breakdown. "
        "Airtime/Data purchases do not appear here: they earn cashback, "
        "not points. Pass `granularity` (daily/weekly/monthly/quarterly/"
        "yearly, default weekly) or an explicit `start_date`/`end_date` "
        "range."
    ),
    parameters=[
        OpenApiParameter(
            "granularity",
            OpenApiTypes.STR,
            OpenApiParameter.QUERY,
            required=False,
            description=f"One of {GRANULARITY_CHOICES}. Ignored if start_date/end_date are passed.",
        ),
        OpenApiParameter(
            "start_date", OpenApiTypes.DATE, OpenApiParameter.QUERY, required=False
        ),
        OpenApiParameter(
            "end_date", OpenApiTypes.DATE, OpenApiParameter.QUERY, required=False
        ),
    ],
    responses={
        200: inline_serializer(
            "PicapointsSourceBreakdownResponse",
            fields={"status": s.CharField(), "data": s.DictField()},
        ),
        400: inline_serializer(
            "PicapointsSourceBreakdownError",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class PicapointsSourceBreakdownView(APIView):
    """Gamification dashboard: where PicaPoints Created are coming from -
    see get_points_source_breakdown. Separate from
    GamificationPicapointsOverviewView, same convention as
    ServicesBreakdownView being separate from IncomeActivityDashboardView."""

    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get(self, request):
        granularity = request.query_params.get("granularity", "weekly")
        raw_start = request.query_params.get("start_date")
        raw_end = request.query_params.get("end_date")

        try:
            if raw_start and raw_end:
                start_date = datetime.strptime(raw_start, "%Y-%m-%d").date()
                end_date = datetime.strptime(raw_end, "%Y-%m-%d").date()
                current_start, current_end, prior_start, prior_end = resolve_period(
                    start_date=start_date, end_date=end_date
                )
                resolved_granularity = "custom"
            elif granularity in GRANULARITY_CHOICES:
                current_start, current_end, prior_start, prior_end = resolve_period(
                    granularity=granularity
                )
                resolved_granularity = granularity
            else:
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "message": f"Invalid granularity. Use one of {GRANULARITY_CHOICES}, or pass start_date/end_date.",
                        }
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )
        except ValueError:
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "Invalid date format. Use YYYY-MM-DD.",
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        current_breakdown = get_points_source_breakdown(current_start, current_end)
        prior_breakdown = get_points_source_breakdown(prior_start, prior_end)

        total = sum(current_breakdown.values())
        source_labels = dict(TRANSACTION_SOURCE_CHOICES)

        sources = []
        for key in sorted(set(current_breakdown) | set(prior_breakdown)):
            current_value = current_breakdown.get(key, 0)
            trend = compute_trend(current_value, prior_breakdown.get(key, 0))
            trend["source"] = key
            trend["source_display"] = source_labels.get(key, key)
            trend["percentage"] = round(current_value / total * 100, 2) if total else 0
            sources.append(trend)
        sources.sort(key=lambda row: row["value"], reverse=True)

        return Response(
            data=encrypt(
                {
                    "status": "success",
                    "data": {
                        "granularity": resolved_granularity,
                        "date_range": {
                            "start": current_start.date().isoformat(),
                            "end": current_end.date().isoformat(),
                        },
                        "total_created": total,
                        "sources": sources,
                    },
                }
            ),
            status=status.HTTP_200_OK,
        )


@extend_schema(
    summary="Task Insight dashboard data",
    tags=["Admin"],
    description=(
        "Returns participant counts for each Task Insight category - Brand "
        "task (BrandTaskSubmission), In App Task (TaskSubmission), and "
        "Streaks (UserStreak) - plus Partner Ecosystem, which is a revenue "
        "figure rather than a participant count: Picadailys's commission "
        "cut when one partner buys another partner's PartnerServices "
        "listing through self-service. All four are period-scoped with a "
        "trend badge. Pass `granularity` (daily/weekly/monthly/quarterly/"
        "yearly, default weekly) or an explicit `start_date`/`end_date` "
        "range."
    ),
    parameters=[
        OpenApiParameter(
            "granularity",
            OpenApiTypes.STR,
            OpenApiParameter.QUERY,
            required=False,
            description=f"One of {GRANULARITY_CHOICES}. Ignored if start_date/end_date are passed.",
        ),
        OpenApiParameter(
            "start_date", OpenApiTypes.DATE, OpenApiParameter.QUERY, required=False
        ),
        OpenApiParameter(
            "end_date", OpenApiTypes.DATE, OpenApiParameter.QUERY, required=False
        ),
    ],
    responses={
        200: inline_serializer(
            "TaskInsightResponse",
            fields={"status": s.CharField(), "data": s.DictField()},
        ),
        400: inline_serializer(
            "TaskInsightError",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class TaskInsightView(APIView):
    """Separate from the other dashboard panels - Task Insight is
    fetched/refreshed independently."""

    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get(self, request):
        granularity = request.query_params.get("granularity", "weekly")
        raw_start = request.query_params.get("start_date")
        raw_end = request.query_params.get("end_date")

        try:
            if raw_start and raw_end:
                start_date = datetime.strptime(raw_start, "%Y-%m-%d").date()
                end_date = datetime.strptime(raw_end, "%Y-%m-%d").date()
                current_start, current_end, prior_start, prior_end = resolve_period(
                    start_date=start_date, end_date=end_date
                )
                resolved_granularity = "custom"
            elif granularity in GRANULARITY_CHOICES:
                current_start, current_end, prior_start, prior_end = resolve_period(
                    granularity=granularity
                )
                resolved_granularity = granularity
            else:
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "message": f"Invalid granularity. Use one of {GRANULARITY_CHOICES}, or pass start_date/end_date.",
                        }
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )
        except ValueError:
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "Invalid date format. Use YYYY-MM-DD.",
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        current_snapshot = get_task_insight_snapshot(current_start, current_end)
        prior_snapshot = get_task_insight_snapshot(prior_start, prior_end)

        data = {
            "brand_task": compute_trend(
                current_snapshot["brand_task"], prior_snapshot["brand_task"]
            ),
            "in_app_task": compute_trend(
                current_snapshot["in_app_task"], prior_snapshot["in_app_task"]
            ),
            "streaks": compute_trend(
                current_snapshot["streaks"], prior_snapshot["streaks"]
            ),
            "partner_ecosystem": compute_trend(
                current_snapshot["partner_ecosystem"],
                prior_snapshot["partner_ecosystem"],
            ),
        }

        return Response(
            data=encrypt(
                {
                    "status": "success",
                    "data": {
                        "granularity": resolved_granularity,
                        "date_range": {
                            "start": current_start.date().isoformat(),
                            "end": current_end.date().isoformat(),
                        },
                        **data,
                    },
                }
            ),
            status=status.HTTP_200_OK,
        )


@extend_schema(
    summary="Demographic breakdown dashboard data",
    tags=["Admin"],
    description=(
        "Returns Revenue by Location/Gender/Age for the selected period. "
        "Revenue is the same combined figure used in ServicesBreakdownView "
        "(vas + self_services + brand_ads + partners), attributed to the "
        "transacting user. Location comes from User.state (required at "
        "registration - good coverage). Gender/Age come from "
        "MemberSurvey.sex/age_bracket, which only exists for users who "
        "completed the survey - anyone missing falls into an 'Unspecified' "
        "bucket rather than being dropped, so each breakdown's total still "
        "reconciles with the true revenue figure. Pass `granularity` "
        "(daily/weekly/monthly/quarterly/yearly, default weekly) or an "
        "explicit `start_date`/`end_date` range."
    ),
    parameters=[
        OpenApiParameter(
            "granularity",
            OpenApiTypes.STR,
            OpenApiParameter.QUERY,
            required=False,
            description=f"One of {GRANULARITY_CHOICES}. Ignored if start_date/end_date are passed.",
        ),
        OpenApiParameter(
            "start_date", OpenApiTypes.DATE, OpenApiParameter.QUERY, required=False
        ),
        OpenApiParameter(
            "end_date", OpenApiTypes.DATE, OpenApiParameter.QUERY, required=False
        ),
    ],
    responses={
        200: inline_serializer(
            "DemographicBreakdownResponse",
            fields={"status": s.CharField(), "data": s.DictField()},
        ),
        400: inline_serializer(
            "DemographicBreakdownError",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class DemographicBreakdownView(APIView):
    """Separate from the other dashboard panels - Demographic Breakdown is
    fetched/refreshed independently."""

    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get(self, request):
        granularity = request.query_params.get("granularity", "weekly")
        raw_start = request.query_params.get("start_date")
        raw_end = request.query_params.get("end_date")

        try:
            if raw_start and raw_end:
                start_date = datetime.strptime(raw_start, "%Y-%m-%d").date()
                end_date = datetime.strptime(raw_end, "%Y-%m-%d").date()
                current_start, current_end, _, _ = resolve_period(
                    start_date=start_date, end_date=end_date
                )
                resolved_granularity = "custom"
            elif granularity in GRANULARITY_CHOICES:
                current_start, current_end, _, _ = resolve_period(
                    granularity=granularity
                )
                resolved_granularity = granularity
            else:
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "message": f"Invalid granularity. Use one of {GRANULARITY_CHOICES}, or pass start_date/end_date.",
                        }
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )
        except ValueError:
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "Invalid date format. Use YYYY-MM-DD.",
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        breakdown = get_demographic_breakdown_snapshot(current_start, current_end)

        return Response(
            data=encrypt(
                {
                    "status": "success",
                    "data": {
                        "granularity": resolved_granularity,
                        "date_range": {
                            "start": current_start.date().isoformat(),
                            "end": current_end.date().isoformat(),
                        },
                        **breakdown,
                    },
                }
            ),
            status=status.HTTP_200_OK,
        )


# ── Alert and Risk drill-downs ──────────────────────────────────────────


def _paginate_rows(rows, request, max_page_size=100):
    """Shared manual pagination for the Alert and Risk drill-down list
    endpoints - same list-slicing approach as AllTransactionsView. Returns
    (paginated_dict, error_response); exactly one of the two is None."""
    try:
        page = max(int(request.query_params.get("page", 1)), 1)
        page_size = min(
            max(int(request.query_params.get("page_size", 20)), 1), max_page_size
        )
    except ValueError:
        return None, Response(
            data=encrypt(
                {"status": "fail", "message": "page and page_size must be integers."}
            ),
            status=status.HTTP_400_BAD_REQUEST,
        )
    offset = (page - 1) * page_size
    return {
        "count": len(rows),
        "page": page,
        "page_size": page_size,
        "results": rows[offset : offset + page_size],
    }, None


def _find_tx_by_transaction_id(transaction_id):
    query = Q(tx_reference=transaction_id)
    if transaction_id.isdigit():
        query |= Q(id=int(transaction_id))
    return TxModel.objects.select_related("user").filter(query).first()


@extend_schema(
    summary="Pending Settlement drill-down list",
    tags=["Admin"],
    description=(
        "Alert and Risk drill-down: every TxModel currently PENDING - a "
        "live backlog snapshot, not period-scoped, same framing as the "
        "pending_settlement count on the Alert and Risk panel. Supports "
        "`page`/`page_size`."
    ),
    parameters=[
        OpenApiParameter(
            "page", OpenApiTypes.INT, OpenApiParameter.QUERY, required=False
        ),
        OpenApiParameter(
            "page_size", OpenApiTypes.INT, OpenApiParameter.QUERY, required=False
        ),
    ],
    responses={
        200: inline_serializer(
            "PendingSettlementListResponse",
            fields={"status": s.CharField(), "data": s.DictField()},
        ),
    },
)
class PendingSettlementListView(APIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get(self, request):
        rows = get_pending_settlement_list()
        paginated, error = _paginate_rows(rows, request)
        if error:
            return error
        return Response(
            data=encrypt({"status": "success", "data": paginated}),
            status=status.HTTP_200_OK,
        )


@extend_schema(
    summary="Transaction Details (Pending Settlement)",
    tags=["Admin"],
    description=(
        "Single transaction lookup by transaction_id (tx_reference, or the "
        "numeric id when tx_reference is null) - backs the Pending "
        'Settlement "Transaction Details" modal.'
    ),
    responses={
        200: inline_serializer(
            "TransactionDetailResponse",
            fields={"status": s.CharField(), "data": s.DictField()},
        ),
        404: inline_serializer(
            "TransactionDetailNotFound",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class TransactionDetailView(APIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get(self, request, transaction_id):
        row = get_transaction_detail_row(transaction_id)
        if not row:
            return Response(
                data=encrypt({"status": "fail", "message": "Transaction not found."}),
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(
            data=encrypt({"status": "success", "data": row}), status=status.HTTP_200_OK
        )


@extend_schema(
    summary="Reconciliation Differences drill-down list",
    tags=["Admin"],
    description=(
        "Alert and Risk drill-down: partner-linked purchases where the "
        "underlying transaction succeeded but the partner hasn't been "
        "marked settled after a grace period (see PartnerPurchase.settled, "
        "RECONCILIATION_GRACE_PERIOD_HOURS). Pass `granularity` "
        "(daily/weekly/monthly/quarterly/yearly, default weekly) or an "
        "explicit `start_date`/`end_date` range, plus `page`/`page_size`."
    ),
    parameters=[
        OpenApiParameter(
            "granularity",
            OpenApiTypes.STR,
            OpenApiParameter.QUERY,
            required=False,
            description=f"One of {GRANULARITY_CHOICES}. Ignored if start_date/end_date are passed.",
        ),
        OpenApiParameter(
            "start_date", OpenApiTypes.DATE, OpenApiParameter.QUERY, required=False
        ),
        OpenApiParameter(
            "end_date", OpenApiTypes.DATE, OpenApiParameter.QUERY, required=False
        ),
        OpenApiParameter(
            "page", OpenApiTypes.INT, OpenApiParameter.QUERY, required=False
        ),
        OpenApiParameter(
            "page_size", OpenApiTypes.INT, OpenApiParameter.QUERY, required=False
        ),
    ],
    responses={
        200: inline_serializer(
            "ReconciliationDifferencesListResponse",
            fields={"status": s.CharField(), "data": s.DictField()},
        ),
        400: inline_serializer(
            "ReconciliationDifferencesListError",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class ReconciliationDifferencesListView(APIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get(self, request):
        granularity = request.query_params.get("granularity", "weekly")
        raw_start = request.query_params.get("start_date")
        raw_end = request.query_params.get("end_date")

        try:
            if raw_start and raw_end:
                start_date = datetime.strptime(raw_start, "%Y-%m-%d").date()
                end_date = datetime.strptime(raw_end, "%Y-%m-%d").date()
                current_start, current_end, _, _ = resolve_period(
                    start_date=start_date, end_date=end_date
                )
                resolved_granularity = "custom"
            elif granularity in GRANULARITY_CHOICES:
                current_start, current_end, _, _ = resolve_period(
                    granularity=granularity
                )
                resolved_granularity = granularity
            else:
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "message": f"Invalid granularity. Use one of {GRANULARITY_CHOICES}, or pass start_date/end_date.",
                        }
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )
        except ValueError:
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "Invalid date format. Use YYYY-MM-DD.",
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        rows = get_reconciliation_differences_list(current_start, current_end)
        paginated, error = _paginate_rows(rows, request)
        if error:
            return error

        return Response(
            data=encrypt(
                {
                    "status": "success",
                    "data": {
                        "granularity": resolved_granularity,
                        "date_range": {
                            "start": current_start.date().isoformat(),
                            "end": current_end.date().isoformat(),
                        },
                        **paginated,
                    },
                }
            ),
            status=status.HTTP_200_OK,
        )


@extend_schema(
    summary="Reconciliation Difference Details (two-sided)",
    tags=["Admin"],
    description=(
        "Two-sided Transaction Details for a Reconciliation Difference: "
        "the user's side (their TxModel row - the wallet debit, already "
        "succeeded) and the partner's side (the PartnerPurchase payout, "
        "still awaiting settlement confirmation)."
    ),
    responses={
        200: inline_serializer(
            "ReconciliationDifferenceDetailResponse",
            fields={"status": s.CharField(), "data": s.DictField()},
        ),
        404: inline_serializer(
            "ReconciliationDifferenceDetailNotFound",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class ReconciliationDifferenceDetailView(APIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get(self, request, transaction_id):
        detail = get_reconciliation_difference_detail(transaction_id)
        if not detail:
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "Reconciliation difference not found.",
                    }
                ),
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(
            data=encrypt({"status": "success", "data": detail}),
            status=status.HTTP_200_OK,
        )


@extend_schema(
    summary="Duplicate Transactions drill-down list",
    tags=["Admin"],
    description=(
        "Alert and Risk drill-down: transactions that look like an "
        "accidental repeat of an immediately preceding one from the same "
        "user (same tx_type + amount within DUPLICATE_TRANSACTION_WINDOW_"
        "MINUTES). Pass `granularity` (daily/weekly/monthly/quarterly/"
        "yearly, default weekly) or an explicit `start_date`/`end_date` "
        "range, plus `page`/`page_size`."
    ),
    parameters=[
        OpenApiParameter(
            "granularity",
            OpenApiTypes.STR,
            OpenApiParameter.QUERY,
            required=False,
            description=f"One of {GRANULARITY_CHOICES}. Ignored if start_date/end_date are passed.",
        ),
        OpenApiParameter(
            "start_date", OpenApiTypes.DATE, OpenApiParameter.QUERY, required=False
        ),
        OpenApiParameter(
            "end_date", OpenApiTypes.DATE, OpenApiParameter.QUERY, required=False
        ),
        OpenApiParameter(
            "page", OpenApiTypes.INT, OpenApiParameter.QUERY, required=False
        ),
        OpenApiParameter(
            "page_size", OpenApiTypes.INT, OpenApiParameter.QUERY, required=False
        ),
    ],
    responses={
        200: inline_serializer(
            "DuplicateTransactionsListResponse",
            fields={"status": s.CharField(), "data": s.DictField()},
        ),
        400: inline_serializer(
            "DuplicateTransactionsListError",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class DuplicateTransactionsListView(APIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get(self, request):
        granularity = request.query_params.get("granularity", "weekly")
        raw_start = request.query_params.get("start_date")
        raw_end = request.query_params.get("end_date")

        try:
            if raw_start and raw_end:
                start_date = datetime.strptime(raw_start, "%Y-%m-%d").date()
                end_date = datetime.strptime(raw_end, "%Y-%m-%d").date()
                current_start, current_end, _, _ = resolve_period(
                    start_date=start_date, end_date=end_date
                )
                resolved_granularity = "custom"
            elif granularity in GRANULARITY_CHOICES:
                current_start, current_end, _, _ = resolve_period(
                    granularity=granularity
                )
                resolved_granularity = granularity
            else:
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "message": f"Invalid granularity. Use one of {GRANULARITY_CHOICES}, or pass start_date/end_date.",
                        }
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )
        except ValueError:
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "Invalid date format. Use YYYY-MM-DD.",
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        rows = get_duplicate_transactions_list(current_start, current_end)
        paginated, error = _paginate_rows(rows, request)
        if error:
            return error

        return Response(
            data=encrypt(
                {
                    "status": "success",
                    "data": {
                        "granularity": resolved_granularity,
                        "date_range": {
                            "start": current_start.date().isoformat(),
                            "end": current_end.date().isoformat(),
                        },
                        **paginated,
                    },
                }
            ),
            status=status.HTTP_200_OK,
        )


@extend_schema(
    summary="Duplicate Transaction Details (two-sided)",
    tags=["Admin"],
    description=(
        "Two-sided Transaction Details for a specific duplicate: the "
        "flagged (later) transaction plus the original it duplicates, "
        "each with its real status."
    ),
    responses={
        200: inline_serializer(
            "DuplicateTransactionDetailResponse",
            fields={"status": s.CharField(), "data": s.DictField()},
        ),
        404: inline_serializer(
            "DuplicateTransactionDetailNotFound",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class DuplicateTransactionDetailView(APIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get(self, request, transaction_id):
        detail = get_duplicate_transaction_detail(transaction_id)
        if not detail:
            return Response(
                data=encrypt(
                    {"status": "fail", "message": "Duplicate transaction not found."}
                ),
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(
            data=encrypt({"status": "success", "data": detail}),
            status=status.HTTP_200_OK,
        )


@extend_schema(
    summary="Fraud Alert drill-down list",
    tags=["Admin"],
    description=(
        "Alert and Risk drill-down: always empty. No fraud ruleset is "
        "defined anywhere in the codebase yet."
    ),
    responses={
        200: inline_serializer(
            "FraudAlertsListResponse",
            fields={"status": s.CharField(), "data": s.DictField()},
        ),
    },
)
class FraudAlertsListView(APIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get(self, request):
        paginated, error = _paginate_rows(get_fraud_alerts_list(), request)
        if error:
            return error
        return Response(
            data=encrypt({"status": "success", "data": paginated}),
            status=status.HTTP_200_OK,
        )


@extend_schema(
    summary="Message Third Party - flag a transaction for resolution",
    tags=["Admin"],
    description=(
        "Creates a support Ticket linked to a specific transaction, for an "
        "ops agent to follow up with the relevant third party (partner/"
        "provider) outside the system - no automated outbound "
        'notification is sent. Backs the "Message Third Party" form on '
        "the Pending Settlement/Reconciliation Differences detail modals."
    ),
    request=TransactionResolutionSerializer,
    responses={
        201: inline_serializer(
            "MessageThirdPartyResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "data": s.DictField(),
            },
        ),
        400: inline_serializer(
            "MessageThirdPartyError",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class MessageThirdPartyView(generics.GenericAPIView):
    serializer_class = TransactionResolutionSerializer
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def post(self, request):
        decrypted_payload = decrypt(request.data)
        payload = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_payload.items()
        }
        serializer = self.get_serializer(data=payload)
        serializer.is_valid(raise_exception=True)

        transaction_id = serializer.validated_data["transaction_id"]
        title = serializer.validated_data["title"]
        issues_description = serializer.validated_data["issues_description"]

        tx = _find_tx_by_transaction_id(transaction_id)

        ticket = Ticket.objects.create(
            user=tx.user if tx and tx.user_id else None,
            customer_name=(
                f"{tx.user.first_name or ''} {tx.user.last_name or ''}".strip()
                if tx and tx.user_id
                else None
            ),
            customer_email=tx.user.email if tx and tx.user_id else None,
            customer_phone_number=tx.user.phone_number if tx and tx.user_id else None,
            title=title,
            category="Transaction Resolution",
            channel="App",
            status="New",
            priority="Medium",
            description=f"Transaction ID: {transaction_id}\n\n{issues_description}",
        )
        # Ticket.save()'s own number-generation never fires (it checks
        # self.pk is None, but BaseModel's UUID pk is already populated by
        # its field default before the first save) - same workaround
        # support.views.CreateTicket already uses.
        ticket.number = generate_ticket_number()
        ticket.save(update_fields=["number"])

        logger.info(
            "SuperAdmin %s raised transaction resolution ticket %s for tx %s.",
            request.user.id,
            ticket.number,
            transaction_id,
        )

        return Response(
            data=encrypt(
                {
                    "status": "success",
                    "message": "Message sent.",
                    "data": {"ticket_number": ticket.number},
                }
            ),
            status=status.HTTP_201_CREATED,
        )


@extend_schema(
    summary="Cancel a pending duplicate transaction",
    tags=["Admin"],
    description=(
        "Marks a PENDING TxModel as CANCELLED - status only, no money "
        "movement (it's still PENDING, so nothing has settled to refund "
        'yet). Backs the "Cancel Pending" action on the Duplicate '
        "Transactions detail modal."
    ),
    request=None,
    responses={
        200: inline_serializer(
            "CancelPendingResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        400: inline_serializer(
            "CancelPendingError",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        404: inline_serializer(
            "CancelPendingNotFound",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class CancelPendingTransactionView(APIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def post(self, request, transaction_id):
        tx = _find_tx_by_transaction_id(transaction_id)
        if not tx:
            return Response(
                data=encrypt({"status": "fail", "message": "Transaction not found."}),
                status=status.HTTP_404_NOT_FOUND,
            )
        if tx.status != "PENDING":
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": f"Only PENDING transactions can be cancelled (this one is {tx.status}).",
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        tx.status = "CANCELLED"
        tx.save(update_fields=["status"])

        logger.info(
            "SuperAdmin %s cancelled pending transaction %s.",
            request.user.id,
            transaction_id,
        )

        return Response(
            data=encrypt({"status": "success", "message": "Transaction cancelled."}),
            status=status.HTTP_200_OK,
        )
