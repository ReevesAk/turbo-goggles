import requests
from django.db import IntegrityError

# Third party imports.
from rest_framework import generics
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication

# In project imports.
from .serializers import (
    RegisterPartnerSerializer,
    PartnerServiceSerializers,
    ServiceAndChargeSerializers,
    PartnerServiceUploadsSerializers,
    PartnerProfileSerializer,
    UpdateProfileSerializer,
    VerifyCacSerializers,
)
from .models import (
    PartnerServiceImageUploads,
)
from commons import Message
from accounts.otp import otp_manager


# Create your views here.
# RegisterPartner handles the POST request of registering a user,
# It takes in firstname, lastname, email and password
#  and returns a validation email upon success.
class RegisterPartner(generics.GenericAPIView):
    serializer_class = RegisterPartnerSerializer

    def post(self, request):
        user = request.data
        serializer = self.serializer_class(data=user)
        if serializer.is_valid(raise_exception=True):
            if user["password"] != user["password2"]:
                return Response(
                data={"error": "Passwords do not match!"},
                status=status.HTTP_400_BAD_REQUEST,
            )

            serializer.save()

            # Create and send OTP.
            otp = otp_manager.create_otp(user_id=str(serializer.data["id"]))
            msg = "Picadailys welcomes you aboard! To protect your account, please enter this {}.".format(
                otp
            )
            recipient = serializer.data["phone_number"]

            response = Message.send_msg(msg=str(msg), to=recipient)
            if response.status_code == 200:
                try:
                    user_data = serializer.data
                    response = {
                        "status": "success",
                        "message": "Partner Created Successfully. Check your phone for an OTP",
                        "data": user_data,
                    }
                    return Response(data=response, status=status.HTTP_201_CREATED)
                except IntegrityError:
                    return Response(
                        {
                            "status": "fail",
                            "message": "Partner with that email already exist",
                        },
                        status=status.HTTP_409_CONFLICT,
                    )
            else:
                return Response(data=response, status=response.status_code)
        else:
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PartnerServiceView(generics.GenericAPIView):
    serializer_class = PartnerServiceSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        user = request.data
        serializer = self.serializer_class(data=user)
        if serializer.is_valid(raise_exception=True):
            serializer.save()
            user_data = serializer.data

        response = {"message": "Services recorded!", "data": user_data}
        return Response(data=response, status=status.HTTP_201_CREATED)


class GetPartnerDetails(generics.RetrieveAPIView):
    """GetPartner decribes returns the profile details of a partner user."""

    serializer_class = PartnerProfileSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

    def retrieve(self, request, *args, **kwargs):
        user = self.request.user  # Get the authenticated user
        serializer = self.get_serializer(user)
        return Response(serializer.data, status=status.HTTP_200_OK)


class UpdatePartnerProfile(generics.UpdateAPIView):
    """Update User Profile"""

    serializer_class = UpdateProfileSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

    def get_object(self):
        return self.request.user

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data, status=status.HTTP_200_OK)


class PartnerServiceListView(generics.RetrieveAPIView):
    serializer_class = PartnerServiceSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

    def retrieve(self, request, *args, **kwargs):
        user = self.request.user  # Get the authenticated user
        serializer = self.get_serializer(user)
        return Response(serializer.data, status=status.HTTP_200_OK)


class ServiceAndChargeView(generics.GenericAPIView):
    serializer_class = ServiceAndChargeSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        user = request.data
        serializer = self.serializer_class(data=user)
        if serializer.is_valid(raise_exception=True):
            serializer.save()
            user_data = serializer.data

        response = {"message": "Service prices added!", "data": user_data}
        return Response(data=response, status=status.HTTP_201_CREATED)


class ServiceAndChargeListView(generics.RetrieveAPIView):
    serializer_class = ServiceAndChargeSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

    def retrieve(self, request, *args, **kwargs):
        user = self.request.user  # Get the authenticated user
        serializer = self.get_serializer(user)
        return Response(serializer.data, status=status.HTTP_200_OK)


class UploadImage(generics.CreateAPIView):
    serializer_class = PartnerServiceUploadsSerializers
    parser_classes = (MultiPartParser,)
    queryset = PartnerServiceImageUploads.objects.all()
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)


class VerifyCAC(generics.GenericAPIView):
    """
    VerifyCAC is a POST request handler for verifying a
    registered partner business It takes in the business name and
    RC number as payload.
    """

    serializer_class = VerifyCacSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        user = request.data
        current_user = request.user

        user["users"] = current_user.id

        resource = "https://searchapp.cac.gov.ng/searchapp/api/public-search/company-business-name-it"
        payload = {
            "searchTerm": user["cac"],
        }

        serializer = self.serializer_class(data=user)
        if serializer.is_valid(raise_exception=True):
            serializer.save(users=current_user)
            try:
                response = requests.post(
                    url=resource,
                    json=payload,
                )

                if response.status_code == 200:
                    resp = response.json()["data"]
                    for name in resp:
                        business_name = user["business_name"].upper()
                        if business_name == name["approvedName"]:
                            response_data = {
                                "status": "Success",
                                "message": "Your business is verified!",
                                "data": response.json(),
                            }
                            return Response(
                                data=response_data, status=status.HTTP_200_OK
                            )
                        else:
                            error_response = {
                                "status": "fail",
                                "message": "The business name provided does not match the RC number!",
                            }
                            return Response(
                                data=error_response, status=status.HTTP_404_NOT_FOUND
                            )
                else:
                    error_response = {
                        "error": "An error occurred!",
                    }
                    return Response(data=error_response, status=response.status_code)
            except requests.exceptions.RequestException as e:
                return Response(
                    {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
