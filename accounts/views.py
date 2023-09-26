from decouple import config

# Third party imports.
from rest_framework import generics
from django.contrib.auth import authenticate
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

# In project imports.
from .serializers import (
    RegisterSerializer,
    VerifyOTPSerailizer,
    ChangePasswordSerializer,
    ForgotPasswordSerializer,
)
from .models import User
from .otp import otp_manager
from .tokens import create_jwt_pair_for_user


# Register handles the POST request of registering a user,
# It takes in firstnmae, lastname, username, email and password
#  and resturns a validation email upon success.
class Register(generics.GenericAPIView):
    serializer_class = RegisterSerializer

    def post(self, request):
        user = request.data
        serializer = self.serializer_class(data=user)
        if serializer.is_valid(raise_exception=True):
            try:
                serializer.save()
                user_data = serializer.data
                response = {
                    "status": "success",
                    "message": "User Created Successfully. Check your phone for an OTP",
                    "data": user_data,
                }
                return Response(data=response, status=status.HTTP_201_CREATED)
            except:
                return Response(
                    {
                        "status": "fail",
                        "message": "User with that email already exist",
                    },
                    status=status.HTTP_409_CONFLICT,
                )
        else:
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# EmailVerify handles the GET request of verifying a register user with valid email.
class EmailVerifyOTP(generics.GenericAPIView):
    permission_classes = (AllowAny,)
    serializer_class = VerifyOTPSerailizer

    def post(self, request):
        data = request.data
        serializer = self.serializer_class(data=data)
        user_data = serializer.data

        if serializer.is_valid():
            received_otp = serializer.data["otp"]

            user = User.objects.get(email=user_data["email"])

            # Validate otp.
            user_id = otp_manager.validate_user_otp(str(received_otp))
            if not user_id:
                return Response(
                    data={"error": "Invalid or expired otp"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            user = User.objects.get(id=user_id)
            user.is_verified = True
            user.save()

            return Response(
                {"Success": "Account is verified"}, status=status.HTTP_201_CREATED
            )


# LoginAPIView handles the POST request of logging in
# a verified user with valid login credentials.
class Login(APIView):
    permission_classes = (AllowAny,)

    def post(self, request):
        email = request.data.get("email")
        password = request.data.get("password")

        if email and password:
            user = authenticate(email=email, password=password)

        if user:
            tokens = create_jwt_pair_for_user(user)

            response = {"message": "Login Successfull", "tokens": tokens}
            return Response(data=response, status=status.HTTP_200_OK)

        else:
            return Response(data={"message": "Invalid email or password"})


class ForgotPassword(generics.GenericAPIView):
    serializer_class = ForgotPasswordSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        user = request.data
        serializer = self.serializer_class(data=user)
        if serializer.is_valid(raise_exception=True):
            serializer.save()
            user_data = serializer.data

            return Response(data=user_data, status=status.HTTP_200_OK)
        else:
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ResetPassword(generics.GenericAPIView):
    serializer_class = ChangePasswordSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        user = request.data
        serializer = self.serializer_class(data=user)
        if serializer.is_valid(raise_exception=True):
            serializer.save()
            user_data = serializer.data

            return Response(data=user_data, status=status.HTTP_201_CREATED)
