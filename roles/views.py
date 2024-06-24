import requests
import logging
from decouple import config
from threading import Thread
from django.core.exceptions import ValidationError
from django.db.models import Q

# Third party imports.
from rest_framework import generics, status, exceptions
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.parsers import MultiPartParser, JSONParser
from rest_framework.pagination import PageNumberPagination

from drf_spectacular.utils import extend_schema

from cloudinary import uploader as cloud

from .helpers import sendMail


class CustomPageNumberPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100


# In project imports.
from .serializers import (
    StatusSerializer,
    RegisterSuperAdminSerializer,
    RegisterOtherAdminRoleSerializer,
    AdminDeletionSerializer,
    ListAdminSerializer,
    ApplicationsSerializers,
)
from .models import Applications
from accounts.models import User, UserNotification
from accounts.otp import otp_manager
from commons import Message
from permissions import IsSuperAdmin

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
    It takes in email, phone, active_role, password and password2.
    Sends an otp to phone for validation.
    """

    serializer_class = RegisterSuperAdminSerializer

    def post(self, request):
        active_role = "SuperAdmin"

        if User.objects.filter(active_role=active_role).exists():
            # Super admin exists, block user registration
            return Response(
                data="User registration is not allowed. Super admin already exists.",
                status=status.HTTP_403_FORBIDDEN,
            )
        else:
            user = request.data
            serializer = self.serializer_class(data=user)
            if serializer.is_valid(raise_exception=True):
                if serializer.data["password"] != serializer.data["password2"]:
                    return Response(
                        data={"error": "Passwords do not match!"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                serializer.save()

                # Create and send OTP.
                otp = otp_manager.create_otp(user_id=str(serializer.data["id"]))
                msg = "Welcome SuperUser! This is a one-time signup. To protect your account, please enter this {}.".format(
                    otp
                )
                recipient = serializer.data["phone_number"]

                response = Message.send_otp(msg=str(msg), to=recipient)

                try:
                    user_data = serializer.data

                    UserNotification.objects.create(
                        user=str(serializer.data["id"]),
                        title="Create SuperUser.",
                        message="SuperUser Created Successfully.",
                    )
                    response = {
                        "status": "success",
                        "message": "SuperUser Created Successfully. Check your phone for an OTP",
                        "data": user_data,
                    }
                    return Response(data=response, status=status.HTTP_201_CREATED)
                except Exception as err:
                    return Response(
                        {
                            "status": "fail",
                            "message": err,
                        },
                        status=status.HTTP_409_CONFLICT,
                    )
            else:
                return Response(
                    data=serializer.errors, status=status.HTTP_400_BAD_REQUEST
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

                content = f'name: {name}, email: {email}, role: {role}, cv: {cv_url}, cover letter: {letter_url}, certificates: {application.certificates}'

                sendMail(content=content)

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
