from django.db import IntegrityError

# Third party imports
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication

# In project imports.
from .serializers import (
    RegisterBrandAdvertSeriailizers,
    BrandAdProfileSerializers,
)
from accounts.models import User
from accounts.otp import otp_manager
from commons import Message
from permissions import IsBrandAd, IsBrandAdAdmin


class RegisterBrandAdverts(generics.GenericAPIView):
    serializer_class = RegisterBrandAdvertSeriailizers

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
                            "message": "Brandadvert with that email or phone number already exist",
                        },
                        status=status.HTTP_409_CONFLICT,
                    )
            else:
                return Response(data=response, status=response.status_code)
        else:
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ListAllBrandAds(generics.ListAPIView):
    serializer_class = BrandAdProfileSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated & (IsBrandAd | IsBrandAdAdmin)]

    def get_queryset(self):
        brand_ads = User.objects.filter(account_type="BrandAd")
        return brand_ads

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.serializer_class(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
