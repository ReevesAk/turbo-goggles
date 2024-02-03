import requests
import logging
from decouple import config
from django.core.exceptions import ValidationError
from django.db.models import Q

# Third party imports.
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication

from drf_spectacular.utils import extend_schema

# In project imports.
from .serializers import (
    StatusSerializer,
    RegisterSuperAdminSerializer,
    RegisterOtherAdminRoleSerializer,
    AdminDeletionSerializer,
    ListAdminSerializer,
)
from accounts.models import User
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


class RegisterSuperAdmin(generics.GenericAPIView):
    """
    RegisterSuperAdmin handles the POST request of registering a superuser,
    It takes in email, phone, account_type, password and password2.
    Sends an otp to phone for validation.
    """

    serializer_class = RegisterSuperAdminSerializer

    def post(self, request):
        account_type = "SuperAdmin"

        if User.objects.filter(account_type=account_type).exists():
            # Super admin exists, block user registration
            return Response(
                data="User registration is not allowed. Super admin already exists.",
                status=status.HTTP_FORBIDDEN,
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
                if response.status_code == 200:
                    try:
                        user_data = serializer.data
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
                    return Response(data=response, status=response.status_code)
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
                "message": "{} Created Successfully.".format(user.data["account_type"]),
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
        new_role = request.data.get("account_type")

        # Update the user's role
        instance.account_type = new_role
        instance.save()
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
                    header=headers,
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


class DeleteAdmin(generics.DestroyAPIView):
    serializer_class = AdminDeletionSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsSuperAdmin)

    def delete(self, request, *args, **kwargs):
        email = self.request.data.get("email")

        try:
            user = User.objects.get(Q(id=email) | Q(email=email))
            user.delete()
            return Response(
                f"Admin with '{email}' deleted successfully.",
                status=status.HTTP_204_NO_CONTENT,
            )
        except User.DoesNotExist:
            return Response(
                f"Admin with '{email}' does not exist.",
                status=status.HTTP_404_NOT_FOUND,
            )
