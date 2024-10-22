import requests
import logging
from decouple import config
from django.contrib.auth.hashers import check_password
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ValidationError
from django.contrib.auth import authenticate
from django.db.models import Q
from django.shortcuts import get_object_or_404

# In project imports.
from .serializers import (
    StatusSerializer,
    RegisterSuperAdminSerializer,
    AdminLoginSerializers,
    AddAdminContdSerializer,
    AddAdminSerializer,
    UpdateAdminRoleSerializer,
    AdminDeletionSerializer,
    ListAdminSerializer,
    ApplicationsSerializers,
    GetApplicationsSerializers,
    DisableAdminSerializer,
    SwitchRolesSerializers,
    CreateAdminPinSerializer,
    EnableAdminSerializer,
)
from user_profile.serializers import GetUserSerializer
from partners.serializers import PartnerProfileSerializer
from adverts.serializers import BrandAdProfileSerializers
from fmcg.serializers import ProductSerializers, AddFmcgPickupAddressSerializers
from .models import Applications
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

from drf_spectacular.utils import extend_schema

from cloudinary import uploader as cloud

from accounts.models import User, UserNotification
from accounts.otp import otp_manager
from commons import Message, CamelCaseJSONRenderer
from permissions import (
    IsSuperAdmin,
    IsNotDisabled,
    IsAdmin,
    IsFmcgAdmin,
    IsFmcgAdminOrSuperAdmin,
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
                    message="SuperUser Created Successfully.",
                )

                response = {
                    "status": "success",
                    "message": "SuperUser Created Successfully. Check your phone for an OTP",
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
    permission_classes = [IsAuthenticated & (IsFmcgAdmin | IsSuperAdmin)]

    def post(self, request):
        user_data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in request.data.items()
        }

        serializer = self.serializer_class(data=user_data)
        if serializer.is_valid(raise_exception=True):
            PickupAdress.objects.create(
                name=user_data["name"], state=user_data["state"]
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

        try:
            user = User.objects.get(Q(id=user_id))

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


class UpdateAdminRole(generics.RetrieveUpdateAPIView):
    serializer_class = UpdateAdminRoleSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsSuperAdmin)
    authentication_classes = [JWTAuthentication]
    renderer_classes = [CamelCaseJSONRenderer]

    def get_object(self):
        email = self.request.data.get("email")
        try:
            user = User.objects.get(Q(id=email) | Q(email=email))
            return user
        except User.DoesNotExist:
            return None

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance is None:
            return Response(data="User not found.", status=status.HTTP_404_NOT_FOUND)
        new_role = request.data.get("active_role")

        # Update the user's role
        instance.active_role = new_role
        instance.save()

        UserNotification.objects.create(
            user=request.user,
            title="Update Admin Role.",
            message=f"Admin's role updated to '{new_role}.",
        )
        return Response(
            f"Admin's role updated to '{new_role}'.", status=status.HTTP_200_OK
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
        _ = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in request.data.items()
        }
        email = self.request.data.get("email")
        pin = self.request.data.get("pin")

        try:
            user = User.objects.filter(Q(email=email)).first()

            if check_password(password=pin, encoded=request.user.admin_pin):
                user.is_admin_disabled = True
                user.save()

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


class GetAllCustomers(generics.RetrieveAPIView):
    """
    GetAllCustomers handles the GET request of retrieving all availalble
    customers wallet information.
    """

    serializer_class = StatusSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsSuperAdmin, IsNotDisabled)
    authentication_classes = [JWTAuthentication]
    renderer_classes = [CamelCaseJSONRenderer]

    @extend_schema(
        description="Get all customers",
        responses={200: {"description": "Get all customers"}},
    )
    def get(self, request):
        user = self.request.user  # Get the authenticated user.

        if user:
            resource = "customers?page=1&page_size=5"

            try:
                response = requests.get(
                    url=base_url + resource,
                    headers=headers,
                )
                if response.status_code == 200:
                    return Response(data=response.json(), status=status.HTTP_200_OK)

            except requests.exceptions.RequestException as e:
                logging.error(f"Fetching customers API request error: {str(e)}")
                return Response(
                    {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
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
                    user=user,
                    title="Delete Admin.",
                    message=f"Admin with '{email}' deleted successfully.",
                )
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

        if page is not None:
            serialized_users = self.get_serializer(page, many=True)
            return Response(
                data={
                    "status": "success",
                    "message": "All admin users retrieved successfully",
                    "num_of_admin_users": queryset.count(),
                    "admin_users": serialized_users.data,
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
