import logging
from decouple import config
from django.contrib.auth.hashers import check_password
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ValidationError
from django.db.models import Count
from django.contrib.auth import authenticate
from django.db.models import Q
from django.shortcuts import get_object_or_404

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
    ApplicationsSerializers,
    GetApplicationsSerializers,
    DisableAdminSerializer,
    SwitchRolesSerializers,
    CreateAdminPinSerializer,
    EnableAdminSerializer,
    GetAllActivityLogsSerializer,
)
from user_profile.serializers import GetUserSerializer
from partners.serializers import PartnerProfileSerializer
from adverts.serializers import BrandAdProfileSerializers
from fmcg.serializers import ProductSerializers, AddFmcgPickupAddressSerializers
from banking.serializers import WalletStatusSerializer
from banking.models import AccountCreation
from .models import Applications, ActivityModel
from fmcg.models import Product, PickupAdress
from accounts.models import DeviceId, AccountType
from accounts.tokens import create_jwt_pair_for_user

# Third party imports.
from rest_framework import generics, status, exceptions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.parsers import MultiPartParser, JSONParser
from rest_framework.pagination import PageNumberPagination

from .models import ADMIN_TYPES

from cloudinary import uploader as cloud

from accounts.models import User, UserNotification
from accounts.otp import otp_manager
from commons import Message, CamelCaseJSONRenderer
from permissions import (
    IsSuperAdmin,
    IsNotDisabled,
    IsAdmin,
    IsFmcgAdminOrSuperAdmin,
    IsWalletAdminOrSuperAdmin,
)


class CustomPageNumberPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100


base_url = config("MAPLERAD_BASE_URL")
secret_key = config("MAPLERAD_SECRET_KEY")
headers = {
    "accept": "application/json",
    "content-Type": "application/json",
    "Authorization": "Bearer " + secret_key,
}

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
    renderer_classes = [CamelCaseJSONRenderer]

    def post(self, request):
        # Check if a SuperAdmin already exists
        # if User.objects.filter(active_role="SuperAdmin").exists():
        #     return Response(
        #         data="Registration is not allowed. Super admin already exists.",
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

                # Set the user's role and create AccountType
                current_user.active_role = "SuperAdmin"
                current_user.save()

                AccountType.objects.create(
                    user=current_user,
                    user_type="SuperAdmin",
                )

                # Create and send OTP
                otp = otp_manager.create_otp(user_id=str(current_user.id))
                print(current_user.id)
                msg = f"Welcome SuperUser! This is a one-time signup. To protect your account, please enter this {otp}."
                recipient = current_user.phone_number

                # Send OTP message
                Message.send_otp(msg=msg, to=recipient)

                # Log the creation of the SuperUser
                UserNotification.objects.create(
                    user=current_user,
                    title="Create SuperUser.",
                    message="SuperUser acount created Successfully.",
                )

                ActivityModel.objects.create(
                    user=current_user,
                    title="Create SuperUser.",
                    description="SuperUser acount created Successfully.",
                )

                response = {
                    "status": "success",
                    "message": "SuperUser Created Successfully. Check your phone for an OTP.",
                    "data": serializer.data,
                }
                return Response(data=response, status=status.HTTP_201_CREATED)

            except Exception as err:
                return Response(
                    {
                        "status": "fail",
                        "message": str(err),
                    },
                    status=status.HTTP_409_CONFLICT,
                )

        return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LoginAdmin(APIView):
    """LoginAPIView handles the POST request of logging in
    a verified user with valid login credentials.
    {"phone_number": "8129187363", "password": "13092830"}.
    """

    serializer_class = AdminLoginSerializers
    renderer_classes = [CamelCaseJSONRenderer]

    def post(self, request):
        _ = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in request.data.items()
        }
        email = request.data.get("email")
        password = request.data.get("password")

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response(
                data={"error": "Invalid credentials"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        user = authenticate(phone_number=user.phone_number, password=password)

        if user:
            # Check if the user already has more than two device IDs.
            existing_device_count = DeviceId.objects.filter(user=user).count()
            if existing_device_count >= 2:
                if existing_device_count == 3:
                    # Delete the oldest device (based on creation timestamp)
                    oldest_device = DeviceId.objects.filter(user=user).earliest(
                        "created_at"
                    )
                    oldest_device.delete()
                return Response(
                    data={
                        "error": "User cannot login on more than two devices, older deviceID deleted."
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # # check if the user has logged in more than one device.
            # for device in existing_device_count:
            #     if not device:
            #     # Create and send OTP.
            #     otp = otp_manager.create_otp(user_id=str(user.id))
            #     msg = "We have noticed that you are using a new device. Please enter this {}. to confirm your identity".format(
            #         otp
            #     )
            #     recipient = user.phone_number

            #     response = Message.send_msg(msg=str(msg), to=recipient)

            #     return Response(
            #         data={"detail": "Otp sent to user's new device Id"},
            #         status=status.HTTP_200_OK,
            #     )
            if not user.is_verified:
                return Response(
                    data={
                        "status": "fail",
                        "message": "Please verify your account to login",
                    },
                    status=status.HTTP_401_UNAUTHORIZED,
                )

            UserNotification.objects.create(
                user=user, title="Login.", message="Login successful."
            )

            ActivityModel.objects.create(
                user=user,
                title="Admin Login.",
                description=f"Admin User, {user.full_name} logged in.",
            )

            # Retrieve user roles from AccountType model
            user_roles = AccountType.objects.filter(user=user).values_list(
                "user_type", flat=True
            )

            # Create JWT tokens
            tokens = create_jwt_pair_for_user(user)
            user_details = {
                "id": user.id,
                "email": user.email,
                "phone_number": user.phone_number,
                "full_name": user.full_name,
                "is_verified": user.is_verified,
                "is_admin_pin_set": user.is_admin_pin_set,
                "roles": list(user_roles),
            }

            response = {
                "status": "success",
                "message": "Login successful",
                "tokens": tokens,
                "user_data": user_details,
            }
            return Response(data=response, status=status.HTTP_200_OK)
        else:
            return Response(
                data={"error": "Invalid credentials"},
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
                return Response(
                    {"error": "An error occurred: {}".format(err)},
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

            ActivityModel.objects.create(
                user=authenticated_user,
                title="Add product",
                description=f"Admin User {authenticated_user.fullname}, added fmcg product {product_entry} to the store.",
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
            return Response(data=resp, status=status.HTTP_201_CREATED)

        else:
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)

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
        user_data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in request.data.items()
        }

        serializer = self.serializer_class(data=user_data)
        if serializer.is_valid(raise_exception=True):
            PickupAdress.objects.create(
                name=user_data["name"], state=user_data["state"]
            )

            name = user_data["name"]
            state = user_data["state"]
            ActivityModel.objects.create(
                user=authenticated_user,
                title="Add FMCG product.",
                description=f"Admin User, {authenticated_user.fullname}, added {name, state} as FMCG pickup address.",
            )
            resp = {
                "status": "success.",
                "message": "Store address added successfully.",
                "data": serializer.data,
            }
            return Response(data=resp, status=status.HTTP_201_CREATED)
        else:
            error_resp = {"status": "fail.", "data": serializer.errors}
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
    renderer_classes = [CamelCaseJSONRenderer]

    def post(self, request):
        payload = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in request.data.items()
        }
        serializer = AddAdminSerializer(data=payload)
        if serializer.is_valid(raise_exception=True):
            user = serializer.save()
            user_data = AddAdminSerializer(user).data

            signup_link = (
                f"https://picadailys-admin.netlify.app/sign-up?user_id={user.id}"
            )
            body = f"Use this link: {signup_link} to complete your registration."

            # Send link to mailbox
            Message.send_email(
                subject="Admin role registration", content=body, email=user.email
            )

            resp = {
                "status": "Success",
                "message": "Created Successfully, a link has been sent to your mail",
                "data": user_data,
            }
            print("Response Data:", resp)
            return Response(
                data=resp,
                status=status.HTTP_201_CREATED,
            )

        else:
            raise ValidationError(
                message=serializer.errors, code=status.HTTP_400_BAD_REQUEST
            )


class AdAdminContd(generics.UpdateAPIView):
    """
    AdAdminContd is a POST request that handles the admin signup completion.
    """

    serializer_class = AddAdminContdSerializer
    permission_classes = [AllowAny]
    renderer_classes = [CamelCaseJSONRenderer]

    def get_object(self):
        user_id = self.kwargs.get("user_id")
        user = User.objects.get(Q(id=user_id))

        try:
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
                    data={
                        "status": "fail",
                        "error": "User exists, but is not an admin.",
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

        except User.DoesNotExist:
            return None

    def update(self, request, *args, **kwargs):
        payload = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in request.data.items()
        }
        instance = self.get_object()
        if instance is None:
            return Response(data="User not found.", status=status.HTTP_404_NOT_FOUND)

        serializer = AddAdminContdSerializer(data=payload)
        if serializer.is_valid(raise_exception=True):
            ActivityModel.objects.create(
                user=instance,
                title="Admin Complete Signup.",
                description=f"Admin user {instance.full_name} completed signup.",
            )
            return Response(
                data={
                    "status": "success",
                    "message": "User registration completed successfully.",
                    "data": serializer.data,
                },
                status=status.HTTP_200_OK,
            )
        else:
            return Response(
                data={"status": "error", "message": serializer.errors},
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
    renderer_classes = [CamelCaseJSONRenderer]

    def perform_create(self, serializer):
        user_data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in self.request.data.items()
        }

        pin = user_data.get("pin")

        # Hash the pin using make_password.
        hashed_pin = make_password(pin)

        # Save the hashed pin in the authenticated user's admin_pin field.
        authenticated_user = self.request.user
        authenticated_user.admin_pin = hashed_pin
        authenticated_user.is_admin_pin_set = True
        authenticated_user.save()

        # Create a user notification
        UserNotification.objects.create(
            user=authenticated_user,
            title="Admin Pin",
            message="Admin pin created successfully.",
        )

    def create(self, request, *args, **kwargs):
        user_data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in request.data.items()
        }

        serializer = self.serializer_class(data=user_data)
        if serializer.is_valid(raise_exception=True):
            self.perform_create(serializer)
            response = {
                "status": "success",
                "message": "Admin pin created successfully!",
            }
            return Response(data=response, status=status.HTTP_201_CREATED)


class AddRoleToAdmin(generics.RetrieveUpdateAPIView):
    serializer_class = AddRoleToAdminSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsSuperAdmin)
    authentication_classes = [JWTAuthentication]
    renderer_classes = [CamelCaseJSONRenderer]

    def get_user(self, email):
        try:
            return User.objects.get(Q(id=email) | Q(email=email))
        except User.DoesNotExist:
            return None

    def post(self, request):
        """Add a role to an admin."""
        user = self.get_user(request.data.get("email"))
        if not user:
            return Response(data="User not found.", status=status.HTTP_404_NOT_FOUND)

        new_role = request.data.get("role")

        # Check if the role already exists
        if AccountType.objects.filter(user=user, user_type=new_role).exists():
            return Response(
                data={
                    "status": "fail.",
                    "message": f"User already has {new_role} as part of their roles.",
                    "role": new_role
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # Add the role
        AccountType.objects.create(user=user, user_type=new_role)

        UserNotification.objects.create(
            user=user,
            title="Updated Admin Role.",
            message=f"'{new_role}' has been added to your Admin's roles.",
        )

        ActivityModel.objects.create(
            user=user,
            title="Admin Role Updated.",
            description=f"Admin, {user.full_name} assigned new role: {new_role}.",
        )
        return Response(
            data={
                "status": "success",
                "message": f"'{new_role}' assigned to the user.",
                "new_role": new_role
            },
            status=status.HTTP_200_OK
        )


class RemoveAdminRole(generics.RetrieveUpdateAPIView):
    serializer_class = RemoveRoleFromAdminSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsSuperAdmin)
    renderer_classes = [CamelCaseJSONRenderer]

    def get_object(self):
        email = self.request.data.get("email")
        try:
            user = User.objects.get(Q(id=email) | Q(email=email))
            return user
        except User.DoesNotExist:
            return None

    def delete(self, request):
        """Remove a role from an admin."""
        user = self.get_user(request.data.get("email"))
        if not user:
            return Response(data="User not found.", status=status.HTTP_404_NOT_FOUND)

        role_to_remove = request.data.get("role")

        # Check if the role exists for the user
        account_type_instance = AccountType.objects.filter(user=user, user_type=role_to_remove).first()
        if not account_type_instance:
            return Response(
                data="Role not found for the user.", status=status.HTTP_400_BAD_REQUEST
            )

        # Remove the role
        account_type_instance.delete()

        UserNotification.objects.create(
            user=user,
            title="Role Removed",
            message=f"The role '{role_to_remove}' has been removed from your account.",
        )

        ActivityModel.objects.create(
            user=user,
            title="Role Removed",
            description=f"'{role_to_remove}' has been removed as part of Admin, {user.full_name} roles.",
        )

        return Response(
            data={
                "status": "success",
                "message": f"Role '{role_to_remove}' removed successfully.",
                "removed_role": role_to_remove
            },
            status=status.HTTP_200_OK
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
    renderer_classes = [CamelCaseJSONRenderer]

    def post(self, request, *args, **kwargs):
        payload = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in request.data.items()
        }
        email = payload.get("email")
        pin = payload.get("pin")

        try:
            user = User.objects.filter(Q(email=email)).first()

            if check_password(password=pin, encoded=request.user.admin_pin):
                user.is_admin_disabled = True
                user.save()

                UserNotification.objects.create(
                    user=user,
                    title="Disable Admin.",
                    message="Your account has been disabled!.",
                )

                ActivityModel.objects.create(
                    user=request.user,
                    title="Disable Admin.",
                    description=f"Admin user, {user.full_name} disabled.",
                )

                resp = {
                    "status": "success",
                    "message": "Admin disabbled successfully",
                    "data": user.is_admin_disabled,
                }
                return Response(data=resp, status=status.HTTP_200_OK)
            else:
                return Response(
                    data={"status": "fail", "error": "Incorrect pin"},
                    status=status.HTTP_401_UNAUTHORIZED,
                )

        except User.DoesNotExist:
            return Response(
                f"Admin with '{email}' does not exist.",
                status=status.HTTP_404_NOT_FOUND,
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
    renderer_classes = [CamelCaseJSONRenderer]

    def post(self, request, *args, **kwargs):
        _ = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in request.data.items()
        }
        email = self.request.data.get("email")
        pin = self.request.data.get("pin")

        try:
            user = User.objects.filter(Q(email=email)).first()

            if check_password(password=pin, encoded=request.user.admin_pin):
                user.is_admin_disabled = False
                user.save()

                UserNotification.objects.create(
                    user=user,
                    title="Re-Enable Admin.",
                    message="Your account has been re-enabled successfully.",
                )

                ActivityModel.objects.create(
                    user=request.user,
                    title="Re-Enable Admin.",
                    description=f"Admin user, {user.first} was re-enabled.",
                )

                resp = {
                    "status": "success",
                    "message": "Admin re-enabled successfully",
                    "data": user.is_admin_disabled,
                }
                return Response(data=resp, status=status.HTTP_200_OK)
            else:
                return Response(
                    data={"status": "fail", "error": "Incorrect pin"},
                    status=status.HTTP_401_UNAUTHORIZED,
                )

        except User.DoesNotExist:
            return Response(
                f"Admin with '{email}' does not exist.",
                status=status.HTTP_404_NOT_FOUND,
            )


class DeleteAdmin(generics.GenericAPIView):
    serializer_class = AdminDeletionSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsSuperAdmin)
    renderer_classes = [CamelCaseJSONRenderer]

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid(raise_exception=True):
            email = serializer.validated_data.get("email")
            pin = serializer.validated_data.get("pin")

            try:
                user = User.objects.get(Q(id=email) | Q(email=email))
                if check_password(password=pin, encoded=request.user.admin_pin):
                    user.delete()

                UserNotification.objects.create(
                    user=request.user,
                    title="Delete Admin.",
                    message=f"Admin with '{email}' deleted successfully.",
                )

                # Register Admin activity.
                ActivityModel.objects.create(
                    user=request.user,
                    title="Delete Admin.",
                    description=f"Admin user, {user.full_name} deleted successfully.",
                )
                # TODO
                # Send email to the admin user.

                return Response(
                    f"Admin with '{email}' deleted successfully.",
                    status=status.HTTP_204_NO_CONTENT,
                )
            except User.DoesNotExist:
                return Response(
                    f"Admin with '{email}' does not exist.",
                    status=status.HTTP_404_NOT_FOUND,
                )
        else:
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class JobApplications(generics.CreateAPIView):
    """
    JobApplications handles the POST request of job applications to Picadailys.
    """

    serializer_class = ApplicationsSerializers
    permission_classes = (AllowAny,)
    parser_classes = (
        MultiPartParser,
        JSONParser,
    )

    def post(self, request):
        serializer = ApplicationsSerializers(data=request.data)
        if serializer.is_valid(raise_exception=True):
            cert_uploads = request.data.getlist("certificates")

            cert_urls = []

            try:
                for upload in cert_uploads:
                    upload_result = cloud.upload(upload)
                    cert_url = upload_result["url"]
                    cert_urls.append(cert_url)

                letter_upload = request.data.get("cover_letter")
                upload_letter = cloud.upload(letter_upload)
                letter_url = upload_letter["url"]

                cv_upload = request.data.get("cv")
                upload_cv = cloud.upload(cv_upload)
                cv_url = upload_cv["url"]

                # Save the application data without the user field
                application = Applications.objects.create(
                    name=request.data.get("name"),
                    email=request.data.get("email"),
                    role=request.data.get("role"),
                    cover_letter=letter_url,
                    portfolio=request.data.get("portfolio"),
                    certificates=",".join(
                        cert_urls
                    ),  # Save as comma-separated string if multiple
                    cv=cv_url,
                )

                # send application to careers@picadailys.com.
                # name = request.data.get("name", "N/A")
                # email = request.data.get("email", "N/A")
                # role = request.data.get("role", "N/A")

                # content = f"""
                #     name: {name},
                #     email: {email},
                #     CV: [View CV]({cv_url}),
                #     cover letter: [View Cover Letter]({letter_url}),
                #     certificates: {application.certificates}
                # """

                # sendMail(content=content, subject=role)

                # Update the certificates field after creating the instance
                application.certificates = ",".join(cert_urls)
                application.save()

                response = {
                    "status": "success",
                    "message": "Job application sent!",
                    "data": {
                        "name": request.data.get("name"),
                        "email": request.data.get("email"),
                        "role": request.data.get("role"),
                        "cover_letter": letter_url,
                        "portfolio": request.data.get("portfolio"),
                        "certificates": cert_urls,
                        "cv": cv_url,
                    },
                }
                return Response(data=response, status=status.HTTP_201_CREATED)

            except Exception as err:
                return Response(
                    {"error": "An error occurred: {}".format(err)},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
        else:
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def upload_image(self, image_data):
        doc_image = cloud.upload(file=image_data)
        self.uploaded_doc_url = doc_image["url"]


class DeleteJobApplication(generics.DestroyAPIView):
    """
    Deletes a single job application entry by ID.
    """

    queryset = Applications.objects.all()
    serializer_class = ApplicationsSerializers
    permission_classes = (AllowAny,)

    def delete(self, request, pk, *args, **kwargs):
        application = get_object_or_404(Applications, pk=pk)

        # Optionally, you could perform some logic before deletion
        try:
            application.delete()
            return Response(
                data={
                    "status": "success",
                    "message": "Job application deleted successfully",
                },
                status=status.HTTP_204_NO_CONTENT,
            )
        except Exception as err:
            return Response(
                {"error": f"An error occurred: {err}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class JobApplicationDetail(generics.ListAPIView):
    """
    Retrieve a single job application based on the email.
    """

    queryset = Applications.objects.all()
    serializer_class = ApplicationsSerializers
    permission_classes = [AllowAny]

    def get_queryset(self):
        email = self.kwargs.get("email")
        email.lower()
        if email is None:
            raise exceptions.NotFound("Email parameter is required.")

        applications = Applications.objects.filter(email=email)
        if not applications.exists():
            raise exceptions.NotFound("No job applications with this email exist.")

        return applications


class JobApplicationList(generics.ListAPIView):
    """
    List all job applications.
    """

    queryset = Applications.objects.all()
    serializer_class = GetApplicationsSerializers
    permission_classes = [AllowAny]


class VerifiedUsersCount(generics.ListAPIView):
    """
    VerifiedUsersCount is the GET request to retrieve the count
    of all verified users.
    """

    serializer_class = GetUserSerializer
    permission_classes = (IsAuthenticated, IsSuperAdmin, IsNotDisabled)
    authentication_classes = [JWTAuthentication]
    pagination_class = PaginationStyle
    renderer_classes = [CamelCaseJSONRenderer]

    def get_queryset(self):
        return User.objects.filter(is_verified=True).order_by("id")

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)

        if page is not None:
            serialized_users = self.get_serializer(page, many=True)
            return Response(
                data={
                    "status": "success",
                    "message": "Verified users retrieved successfully",
                    "verified_users_count": queryset.count(),
                    "verified_users": serialized_users.data,
                },
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
    renderer_classes = [CamelCaseJSONRenderer]

    def get_queryset(self):
        return User.objects.filter(business_verified=True).order_by("created_at")

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)

        if page is not None:
            serialized_users = self.get_serializer(page, many=True)
            return Response(
                data={
                    "status": "success",
                    "message": "Verified Partners retrieved successfully",
                    "verified_business_count": queryset.count(),
                    "verified_businesses": serialized_users.data,
                },
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
    renderer_classes = [CamelCaseJSONRenderer]

    def get_queryset(self):
        return User.objects.filter(has_promoted=True).order_by("created_at")

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)

        if page is not None:
            serialized_users = self.get_serializer(page, many=True)
            return Response(
                data={
                    "status": "success",
                    "message": "Promoted Ads retrieved successfully",
                    "promotedAds_count": queryset.count(),
                    "promotedAds": serialized_users.data,
                },
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
    renderer_classes = [CamelCaseJSONRenderer]

    def get_queryset(self):
        admin_users = (
            User.objects.filter(accounttype__user_type__icontains="Admin")
            .distinct()
            .order_by("accounttype__created_at")
        )
        return admin_users

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        active_admin_count = queryset.filter(is_admin_disabled=False).count()
        disabled_admin_count = queryset.filter(is_admin_disabled=True).count()

        if page is not None:
            serialized_users = self.get_serializer(page, many=True)
            return Response(
                data={
                    "status": "success",
                    "message": "All admin users retrieved successfully",
                    "num_of_admin_users": queryset.count(),
                    "num_of_active_admin_users": active_admin_count,
                    "num_of_disabled_admin_users": disabled_admin_count,
                    "admin_users": serialized_users.data,
                },
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
    permission_classes = (IsAuthenticated, IsWalletAdminOrSuperAdmin)
    pagination_class = PaginationStyle
    renderer_classes = [CamelCaseJSONRenderer]

    def get_queryset(self):
        return (
            User.objects.filter(accounttype__user_type__icontains="Admin")
            .distinct()
            .order_by("accounttype__created_at")
        )

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()

        # Count the number of admins by each role
        role_counts = (
            queryset.values("accounttype__user_type")
            .annotate(role_count=Count("id"))
            .order_by("accounttype__user_type")
        )

        # Transform role counts into a dictionary
        role_counts_dict = {
            role["accounttype__user_type"]: role["role_count"] for role in role_counts
        }

        page = self.paginate_queryset(queryset)
        if page is not None:
            return Response(
                data={
                    "status": "success",
                    "message": "All admin users retrieved successfully",
                    "num_of_admin_users": queryset.count(),
                    "admin_role_counts": role_counts_dict,
                },
                status=status.HTTP_200_OK,
            )


class GetAllWalletStatus(generics.ListAPIView):
    """
    GetAllWalletStatus is the GET request to retrieve the status
    of all wallets, including balance and activation status.
    """

    queryset = AccountCreation.objects.all()
    serializer_class = WalletStatusSerializer
    permission_classes = (IsAuthenticated, IsWalletAdminOrSuperAdmin)

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serialized_wallets = self.get_serializer(queryset, many=True)

        return Response(
            data={
                "status": "success",
                "message": "Wallet statuses retrieved successfully",
                "wallet_statuses": serialized_wallets.data,
            },
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
    renderer_classes = [CamelCaseJSONRenderer]

    def get_queryset(self):
        wallet_admin_users = (
            User.objects.filter(accounttype__user_type__icontains="WalletAdmin")
            .distinct()
            .order_by("accounttype__created_at")
        )
        return wallet_admin_users

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)

        if page is not None:
            serialized_users = self.get_serializer(page, many=True)
            return Response(
                data={
                    "status": "success",
                    "message": "All wallet admin users retrieved successfully",
                    "num_of_wallet_admin_users": queryset.count(),
                    "wallet_admin_users": serialized_users.data,
                },
                status=status.HTTP_200_OK,
            )


class SwitchRoles(generics.RetrieveAPIView):
    """
    SwitchRoles is the PUT request method for updating and switching
    amongst assigned admin roles.
    """

    serializer_class = SwitchRolesSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsAdmin)
    renderer_classes = [CamelCaseJSONRenderer]

    def get_object(self):
        return self.request.user

    def put(self, request):
        _ = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in request.data.items()
        }
        current_user = self.get_object()
        new_role = request.data.get("user_type")

        serializer = AddAdminSerializer(data=request.data)
        if serializer.is_valid(raise_exception=True):
            try:
                account_types = AccountType.objects.filter(user=current_user)

                # Check if the user has the role they want to switch to
                if not account_types.filter(user_type=new_role).exists():
                    data = {
                        "status": "fail",
                        "message": f"Sorry, you have not been assigned the role of {new_role}.",
                        "data": current_user.active_role,
                    }
                    return Response(data=data, status=status.HTTP_400_BAD_REQUEST)

            except AccountType.DoesNotExist:
                raise exceptions.ValidationError(
                    "AccountType for the user does not exist."
                )

            # Handle already switched to the desired role
            if current_user.active_role == new_role:
                data = {
                    "status": "success",
                    "message": f"You are already on the {new_role} screen.",
                    "data": current_user.active_role,
                }
                return Response(data=data, status=status.HTTP_200_OK)

            # Register Admin activity.
            ActivityModel.objects.create(
                user=current_user,
                title="Switch Admin Roles.",
                description=f"Admin user, {current_user.full_name} switched from {current_user.active_role} to {new_role}.",
            )

            # User has the requested account type, switch the role
            current_user.active_role = new_role
            current_user.save()

            data = {
                "status": "success",
                "message": f"Account type switched to {new_role} successfully.",
                "data": current_user.active_role,
            }
            return Response(data=data, status=status.HTTP_200_OK)
        else:
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)


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
        # Define non-admin roles (adjust these based on your application's logic)
        non_admin_roles = {"User", "Member", "Partner", "BrandAd"}

        activities = ActivityModel.objects.filter(user__active_role__in=non_admin_roles).order_by("-created_at")

        paginator = self.pagination_class()
        paginated_activities = paginator.paginate_queryset(activities, request)

        # Prepare response data
        data = []
        for activity in paginated_activities:
            authorised_by = f"{activity.user.first_name} {activity.user.last_name}" if activity.user else "Unknown"
            data.append(
                {
                    "activity_id": activity.id,
                    "authorised_by": authorised_by,
                    "role": activity.user.active_role,
                    "title": activity.title,
                    "description": activity.description,
                    "created_at": activity.created_at,
                }
            )

        response = {
            "status": "success",
            "message": "App activity logs fetched successfully!",
            "page": paginator.page.number,
            "page_size": paginator.page.paginator.per_page,
            "total_count": paginator.page.paginator.count,
            "data": data,
        }
        return Response(response, status=status.HTTP_200_OK)


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
        # Define admin roles to include only admin logs
        admin_roles = {
            "SuperAdmin", "TaskAdmin", "AdAdmin", "MembersAdmin", "UserAdmin", "PartnersAdmin", "ContentAdmin",
            "IntegrationAdmin", "WalletAdmin", "FmcgAdmin"
        }

        # Filter activities based on admin roles
        activities = ActivityModel.objects.filter(user__active_role__in=admin_roles).order_by("-created_at")

        # Apply pagination
        paginator = self.pagination_class()
        paginated_activities = paginator.paginate_queryset(activities, request)

        # Prepare response data
        data = []
        for activity in paginated_activities:
            authorised_by = (
                activity.user.full_name if activity.user and activity.user.full_name
                else activity.user.email if activity.user
                else "Unknown"
            )
            data.append(
                {
                    "activity_id": activity.id,
                    "authorised_by": authorised_by,
                    "role": activity.user.active_role,
                    "title": activity.title,
                    "description": activity.description,
                    "created_at": activity.created_at,
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
        return Response(response, status=status.HTTP_200_OK)


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
        try:
            activity_id = kwargs["activity_id"]
            activity = ActivityModel.objects.get(id=activity_id)

            if activity.user.active_role == "SuperAdmin":
                authorised_by = "SuperAdmin"
            else:
                authorised_by = f"{activity.user.full_name}"

            # Prepare the response data
            response = {
                "status": "success",
                "message": "Activity log retrieved successfully!",
                "title": activity.title,
                "data": {
                    "activity_id": activity_id,
                    "description": activity.description,
                    "authorised_by": authorised_by,
                    "role": activity.user.active_role,
                    "created_at": activity.created_at,
                },
            }
            return Response(data=response, status=status.HTTP_200_OK)

        except ActivityModel.DoesNotExist:
            return Response(
                {"status": "fail", "message": "Activity log not found."},
                status=status.HTTP_404_NOT_FOUND,
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
        try:
            user = User.objects.get(email=admin_email)
            return ActivityModel.objects.filter(user=user).order_by("-created_at")
        except User.DoesNotExist:
            return ActivityModel.objects.none()

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        if not queryset.exists():
            return Response(
                data={"status": "fail", "message": "Activity log not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Prepare response data for all activities
        response_data = []
        for activity in queryset:
            authorised_by = (
                "SuperAdmin" if activity.user.active_role == "SuperAdmin" else activity.user.full_name
            )
            response_data.append({
                "activity_id": activity.id,
                "title": activity.title,
                "description": activity.description,
                "authorised_by": authorised_by,
                "role": activity.user.active_role,
                "created_at": activity.created_at,
            })

        response = {
            "status": "success",
            "message": "Activity logs retrieved successfully!",
            "data": response_data,
        }
        return Response(data=response, status=status.HTTP_200_OK)


class AdminTypesListView(APIView):
    """
    AdminTypesListView is the GET request handler that returns a list of admin types.
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsSuperAdmin)

    def get(self, request):
        admin_types = [admin_type[1] for admin_type in ADMIN_TYPES]
        return Response(
            data={
                "status": "success.",
                "message": "Admin types retrieved successfully.",
                "categories": admin_types,
            },
            status=status.HTTP_200_OK,
        )
