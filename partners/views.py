from django.conf import settings
from decouple import config
import requests


# Third party imports.
from rest_framework import generics
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import MultiPartParser
from rest_framework.generics import CreateAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication


# In project imports.
from .serializers import (
    RegisterPartnerSerializer,
    PartnerServiceSerializers,
    ServiceAndChargeSerializers,
    PartnerServiceUploadsSerializers,
    PartnerProfileSerializer,
)
from .models import (
    PartnerServices,
    ServiceAndCharge,
    PartnerServiceImageUploads,
)
from accounts.models import User
from accounts.utils import send_email
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
            try:
                serializer.save()
                user_data = serializer.data
                response = {
                    "status": "success",
                    "message": "Partner Created Successfully. Check your phone for an OTP",
                    "data": user_data,
                }
                return Response(data=response, status=status.HTTP_201_CREATED)
            except:
                return Response(
                    {
                        "status": "fail",
                        "message": "Partner with that email already exist",
                    },
                    status=status.HTTP_409_CONFLICT,
                )
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


# GetPartner decribes returns the profile details of a partner user.
# It takes in the user_id provided
class GetPartnerDetails(generics.RetrieveAPIView):
    """Partner Detials"""

    serializer_class = PartnerProfileSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        id = self.request.query_params.get("id")
        queryset = User.objects.filter(id=(id))
        return queryset


class PartnerServiceListView(generics.RetrieveAPIView):
    queryset = PartnerServices.objects.all()
    serializer_class = PartnerServiceSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)


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
    queryset = ServiceAndCharge.objects.all()
    serializer_class = ServiceAndChargeSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)


class UploadImage(CreateAPIView):
    serializer_class = PartnerServiceUploadsSerializers
    parser_classes = (MultiPartParser,)
    queryset = PartnerServiceImageUploads.objects.all()
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)
