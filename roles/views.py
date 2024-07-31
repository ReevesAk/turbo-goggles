import requests
import logging
from decouple import config
from django.contrib.auth.hashers import check_password
from django.core.exceptions import ValidationError
from django.contrib.auth import authenticate
from django.db.models import Q

# In project imports.
from .serializers import (
    StatusSerializer,
    RegisterSuperAdminSerializer,
    AdminLoginSerializers,
    RegisterOtherAdminRoleSerializer,
    AdminDeletionSerializer,
    ListAdminSerializer,
    ApplicationsSerializers,
    DisableAdminSerializer,
)
from .models import Applications
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

from .helpers import sendMail

from accounts.models import User, UserNotification
from accounts.otp import otp_manager
from commons import Message
from permissions import IsSuperAdmin


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
        # if User.objects.filter(active_role="SuperAdmin").exists():
        #     return Response(
        #         data="Registration is not allowed. Super admin already exists.",
        #         status=status.HTTP_403_FORBIDDEN,
        #     )

        serializer = self.serializer_class(data=request.data)
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

        return Response(
            data=serializer.errors, status=status.HTTP_400_BAD_REQUEST
        )


class LoginAdmin(APIView):
    """LoginAPIView handles the POST request of logging in
    a verified user with valid login credentials.
    {"phone_number": "8129187363", "password": "13092830"}.
    """

    serializer_class = AdminLoginSerializers

    def post(self, request):
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

            # Create JWT tokens
            tokens = create_jwt_pair_for_user(user)
            response = {
                "status": "success",
                "message": "Login successful",
                "tokens": tokens,
            }
            return Response(data=response, status=status.HTTP_200_OK)
        else:
            return Response(
                data={"error": "Invalid credentials"},
                status=status.HTTP_401_UNAUTHORIZED,
            )


class CreateOtherAdmin(generics.CreateAPIView):
    """
    Create a new admin.
    Only superadmins can create new admins.
    If the user is successfully created, a JSON object containing the user's data is returned.
    If the user cannot be created, a 400 Bad Request or 403 Forbidden error is returned.
    """

    queryset = User.objects.all()
    serializer_class = RegisterOtherAdminRoleSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsSuperAdmin)

    def perform_create(self, serializer):
        if serializer.is_valid(raise_exception=True):
            user = serializer.save()
            user_data = RegisterSuperAdminSerializer(user).data
            resp = {
                "status": "Success",
                "message": "{} Created Successfully.".format(user.data["active_role"]),
                "data": user_data,
            }
            return Response(
                data=resp,
                status=status.HTTP_201_CREATED,
            )

        else:
            raise ValidationError(
                message=serializer.errors, code=status.HTTP_400_BAD_REQUEST
            )


class UpdateAdminRole(generics.RetrieveUpdateAPIView):
    serializer_class = AdminDeletionSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsSuperAdmin)

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

    def post(self, request, *args, **kwargs):
        email = self.request.data.get("email")
        password = self.request.data.get("password")

        try:
            user = User.objects.filter(Q(email=email)).exists()

            if check_password(password=password, encoded=request.user.password):
                user.is_disabled = True
                user.save()

            resp = {
                "status": "success",
                "message": "Admin disabbles successfully",
                "data": user.is_disabled,
            }
            return Response(data=resp, status=status.HTTP_200_OK)

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
    permission_classes = (IsAuthenticated, IsSuperAdmin)

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


class ListAdmin(generics.ListAPIView):
    queryset = User.objects.all()
    serializer_class = ListAdminSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsSuperAdmin)
    pagination_class = PaginationStyle

    def get_queryset(self):
        return super().get_queryset()


class DeleteAdmin(generics.DestroyAPIView):
    serializer_class = AdminDeletionSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsSuperAdmin)

    def delete(self, request, *args, **kwargs):
        email = self.request.data.get("email")

        try:
            user = User.objects.get(Q(id=email) | Q(email=email))
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
                name = request.data.get("name", "N/A")
                email = request.data.get("email", "N/A")
                role = request.data.get("role", "N/A")

                content = f"""
                    name: {name}, 
                    email: {email},
                    CV: [View CV]({cv_url}),
                    cover letter: [View Cover Letter]({letter_url}),
                    certificates: {application.certificates}
                """

                sendMail(content=content, subject=role)

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
    serializer_class = ApplicationsSerializers
    permission_classes = [AllowAny]
