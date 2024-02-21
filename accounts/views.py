from exceptions import Customexceptions

# Third party imports.
from rest_framework import generics
from django.contrib.auth import authenticate
from django.contrib.auth.hashers import make_password
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.tokens import RefreshToken

from drf_spectacular.utils import extend_schema

# In project imports.
from .serializers import (
    LoginSerializers,
    RegisterSerializer,
    VerifyOTPSerializer,
    ResendOTPSerializer,
    ResetPasswordSerializer,
    ForgotPasswordSerializer,
    AcccountStatusSerializer,
    SubmitGamificationSerializer,
)
from .models import User, DeviceId, AccountType
from .otp import otp_manager
from .tokens import create_jwt_pair_for_user
from roles.models import GamificationModel
from sms import Message
from permissions import IsVerifiedUser, IsUserOrMember


class Register(generics.GenericAPIView):
    """
    Register handles the POST request of registering a user,
    It takes in firstname, lastname, username, email and password
    and returns a validation email upon success.
    """

    serializer_class = RegisterSerializer

    def post(self, request):
        user_data = request.data
        authenticated_user = request.user

        serializer = self.serializer_class(data=user_data)
        if serializer.is_valid(raise_exception=True):
            if user_data["password"] != user_data["password2"]:
                return Response(
                    data={"error": "Passwords do not match!"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            user = serializer.save()
            user_type = AccountType.objects.create(user_type="User")
            authenticated_user.account_type.add(user_type)

            # Create and send OTP.
            otp = otp_manager.create_otp(user_id=str(user.id))
            msg = "Picadailys welcomes you aboard! To protect your account, please enter this {}.".format(
                otp
            )
            recipient = serializer.data["phone_number"][1:]

            Message.send_msg(msg=str(msg), to=recipient)

            response = {
                "status": "success",
                "message": "User Created Successfully. Check your phone for an OTP",
                "data": serializer.data,
            }
            return Response(data=response, status=status.HTTP_201_CREATED)
        else:
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PhoneVerifyOTP(generics.GenericAPIView):
    """
    PhoneVerifyOTP handles the POST request of verifying a
    registered user/partner with valid phone number.
    """

    permission_classes = (AllowAny,)
    serializer_class = VerifyOTPSerializer

    def post(self, request):
        user = request.data
        serializer = self.serializer_class(data=user)
        if serializer.is_valid(raise_exception=True):
            received_otp = serializer.data["otp"]

            # Validate otp.
            user_id = otp_manager.validate_user_otp(received_otp)

            if not user_id:
                return Response(
                    data={"error": "Invalid or expired OTP"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            user = User.objects.get(id=user_id)
            # Send welcome message to user.
            msg = "Welcome to Picadailys App...we are thrilled to have you onboard .Get ready to unlock a world of possibilities and seamless experiences. Thank you for choosing us!"
            recipient = user.phone_number

            Message.send_otp(msg=str(msg), to=recipient)
            user.is_verified = True
            user.is_active = True
            user.save()

            verified_resonse = {"status": "success", "message": "Account is verified"}
            return Response(data=verified_resonse, status=status.HTTP_200_OK)


class PasswordPhoneVerifyOTP(generics.GenericAPIView):
    """
    PasswordPhoneVerifyOTP handles the POST request of verifying a
    user/partner with valid phone number for password reset.
    """

    permission_classes = (AllowAny,)
    serializer_class = VerifyOTPSerializer

    def post(self, request):
        user = request.data
        serializer = self.serializer_class(data=user)
        if serializer.is_valid(raise_exception=True):
            received_otp = serializer.data["otp"]

            # Validate otp.
            user_id = otp_manager.validate_user_otp(received_otp)
            print(user_id)

            if not user_id:
                return Response(
                    data={"error": "Invalid or expired OTP"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            user = User.objects.get(id=user_id)
            # Send welcome message to user.
            msg = "User is verified... You can reset now your password!"
            recipient = user.phone_number

            Message.send_msg(msg=str(msg), to=recipient)
            verified_resonse = {"status": "success", "message": "Account is verified"}
            return Response(data=verified_resonse, status=status.HTTP_200_OK)


class ResendOTP(generics.GenericAPIView):
    """
    ResendOTP handles the POST request of resending an
    OTP to a user.
    """

    permission_classes = (AllowAny,)
    serializer_class = ResendOTPSerializer

    def post(self, request):
        user = request.data
        serializer = self.serializer_class(data=user)
        if serializer.is_valid(raise_exception=True):
            phone_number = serializer.data["phone_number"][1:]

            # Generate otp.
            otp = otp_manager.create_otp(user_id=str(serializer.data["id"]))
            msg = (
                "Welcome aboard! To protect your account, please enter this {}.".format(
                    otp
                )
            )

            Message.send_otp(msg=str(msg), to=phone_number)
            response = {
                "status": "success",
                "message": "Otp resent Successfully. Check your phone for validation",
            }
            return Response(data=response, status=status.HTTP_200_OK)
        else:
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PasswordResendOTP(generics.GenericAPIView):
    """
    PasswordResendOTP handles the POST request of resending an
    OTP to a user after password reset.
    """

    permission_classes = (AllowAny,)
    serializer_class = ResendOTPSerializer

    def post(self, request):
        user = request.data
        serializer = self.serializer_class(data=user)
        if serializer.is_valid(raise_exception=True):
            phone_number = serializer.data["phone_number"][1:]

            # Generate otp.
            otp = otp_manager.create_otp(user_id=str(serializer.data["id"]))
            msg = "To reset your password, please enter this One Time Password {}.".format(
                otp
            )

            response = Message.send_otp(msg=str(msg), to=phone_number)
            response = {
                "status": "success",
                "message": "Otp resent Successfully. Check your phone for validation",
            }
            return Response(data=response, status=status.HTTP_200_OK)
        else:
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class Login(APIView):
    """LoginAPIView handles the POST request of logging in
    a verified user with valid login credentials.
    {"phone_number": "8129187363", "password": "13092830"}.
    """

    serializer_class = LoginSerializers
    permission_classes = (IsVerifiedUser,)

    def post(self, request):
        phone_number = request.data.get("phone_number")
        password = request.data.get("password")

        user = authenticate(phone_number=phone_number, password=password)
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


class ForgotPassword(generics.GenericAPIView):
    """
    ForgotPassword handles the POST request of sending a
    forgot password request.
    """

    serializer_class = ForgotPasswordSerializer

    def post(self, request):
        user_data = request.data
        serializer = self.serializer_class(data=user_data)
        if serializer.is_valid(raise_exception=True):
            phone_no = user_data["phone_number"][1:]
            try:
                user = User.objects.get(phone_number=phone_no)
            except user.DoesNotExist:
                return Response(
                    data={"detail": "A user with this phone number does not exist"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            user_id = user.id
            # Create and send OTP.
            otp = otp_manager.create_otp(user_id=str(user_id))
            msg = "Enter this {} to verify your account and reset your password".format(
                otp
            )

            response = Message.send_otp(msg=str(msg), to=phone_no)
            if response.status_code == 200:
                try:
                    response = {
                        "status": "success",
                        "message": "Check your phone for an OTP",
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


class ResetPassword(generics.CreateAPIView):
    serializer_class = ResetPasswordSerializer

    def create(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user_data = serializer.validated_data

        otp = user_data["otp"]
        user_id = otp_manager.validate_user_otp(otp=otp)

        if not user_id:
            return Response(
                data={"error": "Invalid or expired OTP"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response(
                data={"error": "User not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if user_data["password"] != user_data["password2"]:
            return Response(
                data={"error": "Passwords do not match!"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        password = user_data["password"]
        user.password = make_password(password)

        # Retrieve existing tokens and blacklist them.
        user_token = request.data.get("refresh_token")
        if user_token:
            token = RefreshToken(user_token)
            token.blacklist()

        user.save()

        response = {"status": "success!", "message": "Password reset successfully"}
        return Response(data=response, status=status.HTTP_200_OK)


class SubmitGamification(generics.CreateAPIView):
    """
    SubmitGamification is the GET request handler that allows a User/Memeber
    to submit a gamification task result.
    """

    serializer_class = SubmitGamificationSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsUserOrMember)

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid(raise_exception=True):
            task_id = serializer.validated_data["task_id"]

            try:
                task = GamificationModel.objects.get(task_id=task_id)
            except User.DoesNotExist:
                raise Customexceptions.not_found(item_not_found=task_id)

            # Retrieve and save the url of done task.
            task.url = serializer.validated_data["task_url"]
            task.save()

            response_data = {
                "status": "Success",
                "message": "Task submitted successfully, please wait patiently as our agent reviews your work.",
                "data": {
                    "task_id": task.task_id,
                    "title": task.title,
                    "description": task.description,
                },
            }

            return Response(data=response_data, status=status.HTTP_200_OK)


class Logout(APIView):
    serializer_class = AcccountStatusSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        description="Logout view",
        responses={200: {"description": "Logout message"}},
    )
    def post(self, request):
        try:
            refresh_token = request.data["refresh_token"]
            token = RefreshToken(refresh_token)
            token.blacklist()

            return Response(
                data={"status": "success", "logout": "Logout successful!"},
                status=status.HTTP_205_RESET_CONTENT,
            )

        except Exception as e:
            return Response(status=status.HTTP_400_BAD_REQUEST, data={"error": str(e)})
