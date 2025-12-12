import logging
from django.contrib.auth.hashers import check_password
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ValidationError
from django.db.models import Count
from django.contrib.auth import authenticate
from django.db.models import Q
from django.utils import timezone
from django.core.cache import cache

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
    ResetPinSerializer,
)
from user_profile.serializers import GetUserSerializer
from partners.serializers import PartnerProfileSerializer
from adverts.serializers import BrandAdProfileSerializers
from fmcg.serializers import ProductSerializers, AddFmcgPickupAddressSerializers
from banking.serializers import WalletStatusSerializer
from banking.models import WalletModel
from .models import ActivityModel
from fmcg.models import Product, PickupAdress
from accounts.models import DeviceId, AccountType
from accounts.tokens import create_jwt_pair_for_user
from accounts.serializers import VerifyOTPSerializer

# Third party imports.
from rest_framework import generics, status, exceptions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.parsers import MultiPartParser, JSONParser
from rest_framework.pagination import PageNumberPagination
from rest_framework_simplejwt.tokens import RefreshToken

from .models import ADMIN_TYPES

from cloudinary import uploader as cloud

from accounts.models import User, UserNotification
from accounts.otp import otp_manager
from security import encrypt, decrypt
from permissions import (
    IsSuperAdmin,
    IsNotDisabled,
    IsAdmin,
    IsFmcgAdminOrSuperAdmin,
    IsWalletAdminOrSuperAdmin,
)
from sms import Message
from commons import Messaging


class CustomPageNumberPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100


logger = logging.getLogger(__name__)


class PaginationStyle(PageNumberPagination):
    page_size = 10


class RegisterSuperAdmin(generics.GenericAPIView):
    """
    RegisterSuperAdmin handles the POST request of registering a superuser,
    It takes in email, phone, active_role, password, and password2.
    Sends an OTP to the phone for validation.
    """

    serializer_class = RegisterSuperAdminSerializer

    def post(self, request):
        # Check if a SuperAdmin already exists
        if User.objects.filter(active_role="SuperAdmin").exists():
            return Response(
                data="Registration is not allowed. Super admin already exists.",
                status=status.HTTP_403_FORBIDDEN,
            )

        decrypted_payload = decrypt(request.data)
        payload = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_payload.items()
        }
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
                logger.info(f"OTP generated for user: {current_user.id}, OTP: {otp}")
                msg = f"Welcome SuperUser! This is a one-time signup. To protect your account, please enter this {otp}."
                recipient = current_user.phone_number

                # Send OTP message
                Message.send_otp(msg=msg, to=recipient)
                logger.info(f"OTP sent to phone number: {recipient}")

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
                logger.error(f"Error occurred while creating SuperUser: {str(err)}")
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "message": str(err),
                        }
                    ),
                    status=status.HTTP_409_CONFLICT,
                )

        logger.warning("Invalid data received for SuperAdmin registration.")
        return Response(
            data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST
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

        try:
            # Retrieve the user by email to get the phone number
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            logger.warning(f"Login attempt failed: User with email {email} not found.")
            return Response(
                data=encrypt({"error": "Invalid credentials"}),
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
                    data=encrypt(
                        {
                            "error": "User cannot login on more than two devices, oldest device ID deleted."
                        }
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )

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
            logger.warning(
                f"Login attempt failed for user with email {email}. Invalid credentials."
            )
            return Response(
                data=encrypt({"error": "Invalid credentials"}),
                status=status.HTTP_401_UNAUTHORIZED,
            )


class AddProduct(generics.GenericAPIView):
    """
    AddProduct is the POST request that handles the creation
    of fmcg products instance.
    """

    serializer_class = ProductSerializers
    authentication_classes = [JWTAuthentication]
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


class AddAddress(generics.GenericAPIView):
    """
    AddAddress is the POST request that handles the updating of
    of fmcg products store addresses.
    """

    serializer_class = AddFmcgPickupAddressSerializers
    authentication_classes = [JWTAuthentication]
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


class AddAdmin(generics.CreateAPIView):
    """
    Create a new admin.
    Only superadmins can create new admins.
    If the user is successfully created, a JSON object containing the user's data is returned.
    If the user cannot be created, a 400 Bad Request or 403 Forbidden error is returned.
    """

    queryset = User.objects.all()
    serializer_class = AddAdminSerializer
    authentication_classes = [JWTAuthentication]
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
            logger.debug(f"Processed payload: {payload}")

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
                user_data = AddAdminSerializer(user).data
                logger.info(f"Admin user created successfully: {user.email}")

                # Generate signup link
                signup_link = f"https://admin.picadailys.com/sign-up?user_id={user.id}"

                name = user.full_name.split()[0]
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
                        "picadailys_phone": "+123 456 7890",
                    },
                )

                Messaging.send_email(
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
        logger.debug("Payload for update: %s", payload)

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
                data=encrypt({"status": "error", "message": serializer.errors}),
                status=status.HTTP_400_BAD_REQUEST,
            )


class SetAdminPin(generics.CreateAPIView):
    """
    SetWalletPin handles the POST request of creating a pin for a
    customer wallet.
    """

    serializer_class = CreateAdminPinSerializer
    authentication_classes = [JWTAuthentication]
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
                data=encrypt({"status": "error", "message": "Pin is required."}),
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Hash the pin using make_password.
        hashed_pin = make_password(pin)
        logger.debug(
            "Hashed pin for user %s %s: %s", user.first_name, user.last_name, hashed_pin
        )

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
                data=encrypt({"status": "error", "message": serializer.errors}),
                status=status.HTTP_400_BAD_REQUEST,
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
                "picadailys_phone": "+123 456 7890",
            },
        )

        Messaging.send_email(
            email=email, html_content=text_content, subject="Admin Pin Reset"
        )
        logger.info(f"OTP sent: {otp}")
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
        logger.debug("Received data for pin reset OTP verification: %s", user_data)

        serializer = self.serializer_class(data=user_data)

        # Validate incoming data with serializer class.
        if not serializer.is_valid(raise_exception=True):
            logger.error(
                "Serializer validation failed with errors: %s", serializer.errors
            )
            return Response(
                data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST
            )

        received_otp = serializer.data["otp"]
        logger.info("OTP received for pin reset: %s", received_otp)

        # Validate OTP
        user_id = otp_manager.validate_user_otp(received_otp)
        if not user_id:
            logger.warning("Invalid or expired OTP during pin reset: %s", received_otp)
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
                "picadailys_phone": "+123 456 7890",
            },
        )

        Messaging.send_email(
            email=user.email, html_content=text_content, subject="Admin Verify OTP"
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


class ResetPin(generics.CreateAPIView):
    serializer_class = ResetPinSerializer

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
            logger.info(f"Refresh token blacklisted for user: {admin_id}")

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


class AddRoleToAdmin(generics.GenericAPIView):
    serializer_class = AddRoleToAdminSerializer
    authentication_classes = [JWTAuthentication]
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

        if check_password(password=pin, encoded=request.user.admin_pin):
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


class RemoveAdminRole(generics.GenericAPIView):
    serializer_class = RemoveRoleFromAdminSerializer
    authentication_classes = [JWTAuthentication]
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

        if check_password(password=pin, encoded=request.user.admin_pin):
            if not account_type_instance:
                logger.warning(
                    "Role '%s' not found for user: %s", role_to_remove, email
                )
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


class DisableAdminrole(generics.RetrieveUpdateAPIView):
    """
    DisableAdminrole handles the POST request of disabling
    an admin user.
    """

    queryset = User.objects.all()
    serializer_class = DisableAdminSerializer
    permission_classes = [IsAuthenticated, IsSuperAdmin]
    authentication_classes = [JWTAuthentication]

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

            if check_password(password=pin, encoded=request.user.admin_pin):
                user.is_admin_disabled = True
                user.save()
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

        except Exception as e:
            logger.error("An error occurred while disabling admin: %s", str(e))
            return Response(
                data=encrypt({"status": "fail", "error": "An error occurred."}),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class EnableAdminrole(generics.RetrieveUpdateAPIView):
    """
    EnableAdminrole handles the POST request of re-enabling
    a disabled admin user.
    """

    queryset = User.objects.all()
    serializer_class = EnableAdminSerializer
    permission_classes = [IsAuthenticated, IsSuperAdmin]
    authentication_classes = [JWTAuthentication]

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

            if check_password(password=pin, encoded=request.user.admin_pin):
                user.is_admin_disabled = False
                user.save()
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
                logger.info(
                    "Activity logged for re-enabling admin '%s'.", user.full_name
                )

                resp = {
                    "status": "success",
                    "message": "Admin re-enabled successfully",
                    "data": user.is_admin_disabled,
                }
                return Response(data=encrypt(resp), status=status.HTTP_200_OK)
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

        except Exception as e:
            logger.error("An error occurred while re-enabling admin: %s", str(e))
            return Response(
                data=encrypt({"status": "fail", "error": "An error occurred."}),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class DeleteAdmin(generics.GenericAPIView):
    serializer_class = AdminDeletionSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsSuperAdmin)

    def post(self, request, *args, **kwargs):
        decrypted_payload = decrypt(request.data)
        serializer = self.serializer_class(data=decrypted_payload)
        if serializer.is_valid(raise_exception=True):
            email = serializer.validated_data.get("email")
            pin = serializer.validated_data.get("pin")
            logger.info("Received request to delete admin for email: %s", email)

            try:
                user = User.objects.get(Q(id=email) | Q(email=email))
                logger.info("Admin user found: %s", user.full_name)

                if check_password(password=pin, encoded=request.user.admin_pin):
                    user.delete()
                    logger.info("Admin user '%s' deleted successfully.", user.full_name)

                    UserNotification.objects.create(
                        user=request.user,
                        title="Delete Admin.",
                        message=f"Admin with '{email}' deleted successfully.",
                    )
                    logger.info(
                        "User  notification created for admin deletion: %s", email
                    )

                    # Register Admin activity.
                    ActivityModel.objects.create(
                        user=request.user,
                        title="Delete Admin.",
                        description=f"Admin user, {user.full_name} deleted successfully.",
                    )
                    logger.info(
                        "Activity logged for deleting admin: %s", user.full_name
                    )

                    text_content = render_to_string(
                        template_name="empty_email.html",
                        context={
                            "custom_text": f"Dear {request.user.first_name},<br><br>Your admin account has been deleted.",
                            "support_email": "support@picadailys.com",
                            "picadailys_phone": "+123 456 7890",
                        },
                    )

                    Message.send_email(
                        email=request.user.email,
                        html_content=text_content,
                        subject="Admin Deletion",
                    )

                    return Response(
                        data=encrypt(f"Admin with '{email}' deleted successfully."),
                        status=status.HTTP_204_NO_CONTENT,
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


class VerifiedUsersCount(generics.ListAPIView):
    """
    VerifiedUsersCount is the GET request to retrieve the count
    of all verified users.
    """

    serializer_class = GetUserSerializer
    permission_classes = (IsAuthenticated, IsSuperAdmin, IsNotDisabled)
    authentication_classes = [JWTAuthentication]
    pagination_class = PaginationStyle

    def get_queryset(self):
        return User.objects.filter(is_verified=True).order_by("id")

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


class VerifiedPartnersCount(generics.ListAPIView):
    """
    VerifiedPartnersCount is the GET request to retrieve the count
    of all verified Partners.
    """

    serializer_class = PartnerProfileSerializer
    permission_classes = (IsAuthenticated, IsSuperAdmin, IsNotDisabled)
    authentication_classes = [JWTAuthentication]
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


class VerifiedBrandAdsCount(generics.ListAPIView):
    """
    VerifiedBrandAdsCount is the GET request to retrieve the count
    of all verified promoted brandads.
    """

    serializer_class = BrandAdProfileSerializers
    permission_classes = (IsAuthenticated, IsSuperAdmin, IsNotDisabled)
    authentication_classes = [JWTAuthentication]
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


class GetAllAdminUsers(generics.ListAPIView):
    """
    GetAllAdminUsers is the GET request to retrieve the count
    of all admin users.
    """

    queryset = User.objects.all()
    serializer_class = ListAdminSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsSuperAdmin)
    pagination_class = PaginationStyle

    def get_queryset(self):
        logger.info("Retrieving admin users.")
        admin_users = (
            User.objects.filter(account_types__user_type__icontains="Admin")
            .distinct()
            .order_by("account_types__created_at")
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

            # Save to cache (short TTL)
            cache.set(cache_key, response_data, timeout=900)  # 15 minutes

            return Response(
                data=encrypt(response_data),
                status=status.HTTP_200_OK,
            )


class GetAllAdminUsersTypes(generics.ListAPIView):
    """
    GetAllAdminUsersTypes is the GET request to retrieve the count
    of all admin users, grouped by each admin role.
    """

    queryset = User.objects.all()
    serializer_class = ListAdminSerializer
    authentication_classes = [JWTAuthentication]
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


class GetAllWalletAdminUsers(generics.ListAPIView):
    """
    GetAllWalletAdminUsers is the GET request to retrieve the count
    of all wallet admin users.
    """

    queryset = User.objects.all()
    serializer_class = ListAdminSerializer
    authentication_classes = [JWTAuthentication]
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


class SwitchRoles(generics.RetrieveAPIView):
    """
    SwitchRoles is the PUT request method for updating and switching
    amongst assigned admin roles.
    """

    serializer_class = SwitchRolesSerializers
    authentication_classes = [JWTAuthentication]
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
        logger.debug(f"Processed payload: {payload}")

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


class GetProfileImage(generics.RetrieveAPIView):
    authentication_classes = [JWTAuthentication]
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


class GetAllAppActivites(generics.ListAPIView):
    """
    GetAllAdminActivities is the GET request handler that allows the SuperAdmin to
    receive all app activity logs.
    """

    authentication_classes = [JWTAuthentication]
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


class GetAllAdminActivites(generics.ListAPIView):
    """
    GetAllAdminActivities is the GET request handler that allows the SuperAdmin to
    receive all activity logs, including the name of the admin user who
    created the activity.
    """

    authentication_classes = [JWTAuthentication]
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
                else activity.user.email
                if activity.user
                else "Unknown"
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


class GetSingleAdminActivity(generics.RetrieveAPIView):
    """
    GetSingleAdminActivity is the GET request handler that allows a SuperAdmin to
    check a specific admin activity log.
    """

    queryset = ActivityModel.objects.all()
    serializer_class = GetAllActivityLogsSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
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


class GetAllSingleAdminUserActivity(generics.ListAPIView):
    """
    GetAllSingleAdminUserActivity is the GET request handler that allows a SuperAdmin to
    check a specific admin activity log for a single Admin user.
    """

    queryset = ActivityModel.objects.all()
    serializer_class = GetAllActivityLogsSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
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


class AdminTypesListView(APIView):
    """
    AdminTypesListView is the GET request handler that returns a list of admin types.
    """

    authentication_classes = [JWTAuthentication]
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


class ActivityTitleListView(APIView):
    """
    Retrieve all unique activity titles.
    """

    permission_classes = [IsAuthenticated, IsSuperAdmin]
    authentication_classes = [JWTAuthentication]

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
