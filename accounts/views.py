from django.utils import timezone

from exceptions import Customexceptions
from cloudinary import uploader as cloud
import logging

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
from rest_framework.parsers import MultiPartParser, JSONParser

from drf_spectacular.utils import extend_schema

# In project imports.
from .serializers import (
    LoginSerializers,
    RegisterSerializer,
    VerifyOTPSerializer,
    ResendOTPSerializer,
    ResetPasswordSerializer,
    ForgotPasswordSerializer,
    PasswordResendOTPSerializer,
    LogoutSerializer,
    SubmitGamificationSerializer,
)
from .models import User, DeviceId, AccountType, UserNotification
from .otp import otp_manager
from .tokens import create_jwt_pair_for_user
from roles.models import GamificationModel, ActivityModel
from sms import Message
from commons import Biometrics
from permissions import IsUserOrMember
from security import encrypt, decrypt


logger = logging.getLogger("accounts")


class Register(generics.GenericAPIView):
    """
    Register handles the POST request of registering a user,
    It takes in firstname, lastname, username, email and password
    and returns a validation email upon success.
    """

    serializer_class = RegisterSerializer
    parser_classes = [MultiPartParser, JSONParser]

    def post(self, request):
        user_data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in request.data.items()
        }

        logger.info("Received registration data: %s", user_data)

        serializer = self.serializer_class(data=user_data)
        if serializer.is_valid(raise_exception=True):
            if user_data["password"] != user_data["password2"]:
                logger.warning("Password mismatch for user: %s", user_data.get("email"))
                return Response(
                    data=encrypt({"status": "fail", "error": "Passwords do not match!"}),
                    status=status.HTTP_400_BAD_REQUEST,
                )

            profile_upload = user_data.get("profile_image")

            user = serializer.save()
            AccountType.objects.create(
                user=user,
                user_type="User",
            )
            user.active_role = "User"
            user.save()

            logger.info("User created: %s", user.email)

            if profile_upload:
                try:
                    image_url = self.upload_image(profile_upload)
                    user.profile_img_url = image_url
                    logger.info("Profile image: %s", image_url)
                    user.save()
                    logger.info("Profile image uploaded for user: %s", user.email)
                except Exception as e:
                    logger.error(
                        "Error uploading profile image for user %s: %s",
                        user.email,
                        str(e),
                    )

            ActivityModel.objects.create(
                user=user,
                title="User Registration.",
                description=f"{user.first_name} {user.last_name} just registered as a User.",
            )

            # Create and send OTP.
            otp = otp_manager.create_otp(user_id=str(user.id))
            logger.info("OTP for user: %s", otp)
            msg = "Picadailys welcomes you aboard! To protect your account, please enter this {}.".format(
                otp
            )
            recipient = serializer.data["phone_number"][1:]

            Message.send_msg(msg=str(msg), to=recipient)

            response = {
                "status": "success",
                "message": "User Created Successfully. Check your phone for an OTP",
                "image": user.profile_img_url,
                "data": serializer.data,
            }
            logger.info("Registration successful for user: %s", user.email)
            encrypted_response = encrypt(response)
            return Response(data=encrypted_response, status=status.HTTP_201_CREATED)
        else:
            logger.error(
                "Registration failed for user: %s, errors: %s",
                user_data.get("email"),
                serializer.errors,
            )
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def upload_image(self, image_data):
        profile_img = cloud.upload(file=image_data)
        self.uploaded_profile_url = profile_img["url"]
        return self.uploaded_profile_url


class PhoneVerifyOTP(generics.GenericAPIView):
    """
    PhoneVerifyOTP handles the POST request of verifying a
    registered user/partner with valid phone number.
    """

    permission_classes = (AllowAny,)
    serializer_class = VerifyOTPSerializer

    def post(self, request):
        decrypted_payload = decrypt(request.data)
        user_data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_payload.items()
        }
        logger.debug("Received user data for OTP verification: %s", user_data)

        serializer = self.serializer_class(data=user_data)
        if serializer.is_valid(raise_exception=True):
            received_otp = serializer.data["otp"]
            logger.info("OTP received: %s", received_otp)

            # Validate OTP
            user_id = otp_manager.validate_user_otp(received_otp)
            if not user_id:
                logger.warning("Invalid or expired OTP: %s", received_otp)
                return Response(
                    data={"error": "Invalid or expired OTP"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                logger.error("User with id %s does not exist.", user_id)
                return Response(
                    data={"error": "User not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Send welcome message to user
            msg = "Welcome to Picadailys App...we are thrilled to have you onboard. Get ready to unlock a world of possibilities and seamless experiences. Thank you for choosing us!"
            recipient = user.phone_number

            Message.send_otp(msg=str(msg), to=recipient)
            logger.info("Welcome message sent to user %s at %s", user.id, recipient)

            # Update user verification status
            user.is_verified = True
            user.is_active = True
            user.save()
            logger.info("User %s has been verified and activated.", user.id)

            # Log activity
            ActivityModel.objects.create(
                user=user,
                title="Verify Account",
                description=f"{user.first_name} {user.last_name} verified OTP after registration.",
            )
            logger.info("Activity logged for user %s verification.", user.id)

            verified_response = {"status": "success", "message": "Account is verified"}
            encrypted_response = encrypt(verified_response)
            return Response(data=encrypted_response, status=status.HTTP_200_OK)
        else:
            logger.error(
                "Serializer validation failed with errors: %s", serializer.errors
            )
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PasswordPhoneVerifyOTP(generics.GenericAPIView):
    """
    PasswordPhoneVerifyOTP handles the POST request of verifying a
    user/partner with valid phone number for password reset.
    """

    permission_classes = (AllowAny,)
    serializer_class = VerifyOTPSerializer

    def post(self, request):
        decrypted_payload = decrypt(request.data)
        user_data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_payload.items()
        }
        logger.debug("Received data for password reset OTP verification: %s", user_data)

        serializer = self.serializer_class(data=user_data)
        if serializer.is_valid(raise_exception=True):
            received_otp = serializer.data["otp"]
            logger.info("OTP received for password reset: %s", received_otp)

            # Validate OTP
            user_id = otp_manager.validate_user_otp(received_otp)
            if not user_id:
                logger.warning(
                    "Invalid or expired OTP during password reset: %s", received_otp
                )
                return Response(
                    data={"error": "Invalid or expired OTP"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                logger.error(
                    "User with id %s not found for password reset verification.",
                    user_id,
                )
                return Response(
                    data={"error": "User not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Send confirmation message to the user
            msg = "User is verified... You can reset your password now!"
            recipient = user.phone_number
            Message.send_msg(msg=str(msg), to=recipient)
            logger.info(
                "Password reset verification message sent to user %s at %s",
                user.id,
                recipient,
            )

            # Log activity for verification
            ActivityModel.objects.create(
                user=user,
                title="Verify Account",
                description=f"{user.first_name} {user.last_name} verified OTP for password reset.",
            )
            logger.info(
                "Password reset OTP verification activity logged for user %s.", user.id
            )

            verified_response = {
                "status": "success",
                "message": "Account is verified",
                "user_id": user_id,
            }
            encrypted_response = encrypt(verified_response)
            return Response(data=encrypted_response, status=status.HTTP_200_OK)
        else:
            logger.error(
                "Serializer validation failed with errors: %s", serializer.errors
            )
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ResendOTP(generics.GenericAPIView):
    """
    ResendOTP handles the POST request of resending an
    OTP to a user.
    """

    permission_classes = (AllowAny,)
    serializer_class = ResendOTPSerializer

    def post(self, request):
        # Log initial data received
        decrypted_payload = decrypt(request.data)

        # Clean up input data
        user_data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_payload.items()
        }
        logger.debug("Resend OTP request data: %s", decrypted_payload)
        serializer = self.serializer_class(data=user_data)

        # Validate serializer data
        if serializer.is_valid(raise_exception=True):
            # Process phone number and user ID
            phone_number = serializer.data["phone_number"][1:]  # Remove first character
            user_id = serializer.data["id"]
            logger.info(
                "Resending OTP for user ID %s to phone number %s", user_id, phone_number
            )

            # Generate OTP
            otp = otp_manager.create_otp(user_id=str(user_id))
            logger.info("Generated OTP %s for user ID %s", otp, user_id)

            # Send OTP message
            msg = "Welcome aboard! To protect your account, please enter this OTP: {}.".format(
                otp
            )
            Message.send_otp(msg=str(msg), to=phone_number)
            logger.info("OTP message sent to phone number %s", phone_number)

            # Prepare response
            response = {
                "status": "success",
                "message": "OTP resent successfully. Check your phone for validation.",
            }
            encrypted_response = encrypt(response)
            return Response(data=encrypted_response, status=status.HTTP_200_OK)

        else:
            # Log validation errors
            logger.error("Resend OTP validation failed: %s", serializer.errors)
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PasswordResendOTP(generics.GenericAPIView):
    """
    PasswordResendOTP handles the POST request of resending an
    OTP to a user after password reset.
    """

    permission_classes = (AllowAny,)
    serializer_class = PasswordResendOTPSerializer

    def post(self, request):
        decrypted_payload = decrypt(request.data)
        logger.debug("Received OTP resend request data: %s", decrypted_payload)

        user_data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_payload.items()
        }
        serializer = self.serializer_class(data=user_data)

        if serializer.is_valid(raise_exception=True):
            phone_number = serializer.data["phone_number"][1:]
            logger.info("Processing OTP resend for phone number: %s", phone_number)

            try:
                user = User.objects.get(phone_number=serializer.data["phone_number"])
                logger.info("User found with phone number: %s", phone_number)

                # Generate OTP using the user's ID
                otp = otp_manager.create_otp(user_id=str(user.id))
                logger.info("Generated OTP: %s for user ID: %s", otp, user.id)

                msg = "To reset your password, please enter this One Time Password {}.".format(
                    otp
                )

                # Send OTP
                Message.send_otp(msg=str(msg), to=phone_number)
                logger.info("Sent OTP to phone number: %s", phone_number)

                response = {
                    "status": "success",
                    "message": "OTP resent successfully. Check your phone for validation.",
                }
                return Response(data=encrypt(response), status=status.HTTP_200_OK)

            except User.DoesNotExist:
                logger.warning(
                    "User with phone number %s does not exist.", phone_number
                )
                resp = {
                    "status": "fail",
                    "message": "User with the provided phone number does not exist.",
                }
                encrypted_response = encrypt(resp)
                return Response(
                    data=encrypted_response,
                    status=status.HTTP_404_NOT_FOUND,
                )

        else:
            logger.error("OTP resend validation failed: %s", serializer.errors)
            return Response(
                data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST
            )


class Login(APIView):
    """
    LoginAPIView handles the POST request for logging in
    a verified user with valid biometrics or password credentials.
    """

    serializer_class = LoginSerializers

    def post(self, request):
        print(request.data)
        decrypted_payload = decrypt(request.data)
        logger.debug("Received login request data: %s", decrypted_payload)
        data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_payload.items()
        }
        login = data.get("phone_number")
        password = data.get("password")
        biometrics = data.get("use_biometrics")

        logger.info("Login attempt for phone number: %s", login)

        # Check if biometrics is requested
        if biometrics:
            user = Biometrics.authenticate(login)
            logger.info("Biometric authentication attempted for user: %s", login)
        else:
            user = authenticate(phone_number=login, password=password)
            logger.info("Password authentication attempted for user: %s", login)

        # If authentication fails, return an error
        if not user:
            logger.warning("Invalid credentials for user: %s", login)
            return Response(
                data=encrypt({"error": "Invalid credentials"}),
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # Ensure user is verified if using password login
        if not biometrics and not user.is_verified:
            logger.warning("User %s is not verified, cannot login", login)
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "Please verify your account to login",
                    }
                ),
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # Check device limit for password login only
        if not biometrics and not self.check_device_limit(user):
            logger.warning(
                "User %s has reached device limit. Deleting oldest device.", login
            )
            return Response(
                data=encrypt(
                    {
                        "error": "User cannot log in on more than two devices; oldest device deleted."
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Successful login
        return self.handle_login_success(user)

    def check_device_limit(self, user):
        existing_device_count = DeviceId.objects.filter(user=user).count()
        if existing_device_count >= 2:
            if existing_device_count >= 3:
                oldest_device = DeviceId.objects.filter(user=user).earliest(
                    "created_at"
                )
                logger.info(
                    "Deleting oldest device %s for user %s",
                    oldest_device.id,
                    user.phone_number,
                )
                oldest_device.delete()
            return False
        return True

    def handle_login_success(self, user):
        logger.info("User %s successfully logged in.", user.phone_number)

        # Log successful login event
        UserNotification.objects.create(
            user=user, title="Login", message="Login successful."
        )
        ActivityModel.objects.create(
            user=user,
            title="Login.",
            description=f"{user.first_name} {user.last_name} successfully logged into their account.",
        )
        user.last_login = timezone.now()
        user.save(update_fields=["last_login"])

        # Create JWT tokens
        tokens = create_jwt_pair_for_user(user)
        logger.info("JWT tokens generated for user %s", user.phone_number)

        response = {
            "status": "success",
            "message": "Login successful",
            "active_role": user.active_role,
            "tokens": tokens,
        }
        encrypted_response = encrypt(response)
        return Response(data=encrypted_response, status=status.HTTP_200_OK)


class ForgotPassword(generics.GenericAPIView):
    """
    ForgotPassword handles the POST request of sending a
    forgot password request.
    """

    serializer_class = ForgotPasswordSerializer

    def post(self, request):
        decrypted_payload = decrypt(request.data)
        user_data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_payload.items()
        }
        serializer = self.serializer_class(data=user_data)
        if not serializer.is_valid(raise_exception=True):
            return Response(data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST)

        phone_no = user_data["phone_number"][1:]
        try:
            user = User.objects.get(phone_number=user_data["phone_number"])
            logger.info(f"User found for phone number: {user.phone_number}")
        except User.DoesNotExist:
            logger.warning(
                f"No user found with phone number: {user_data['phone_number']}"
            )
            return Response(
                data=encrypt({
                    "status": "fail",
                    "detail": "A user with this phone number does not exist",
                }),
                status=status.HTTP_404_NOT_FOUND,
            )

        user_id = user.id
        otp = otp_manager.create_otp(user_id=str(user_id))
        msg = f"Enter this {otp} to verify your account and reset your password"

        Message.send_otp(msg=str(msg), to=phone_no)
        logger.info(f"OTP sent to phone number: {phone_no}")

        UserNotification.objects.create(
            user=user,
            title="Forgot Password Request.",
            message="Check your phone for an OTP.",
        )

        ActivityModel.objects.create(
            user=user,
            title="Forgot Password Request.",
            description=f"{user.first_name} {user.last_name} submitted a forgot password request.",
        )

        response = {
            "status": "success",
            "message": "Check your phone for an OTP",
        }
        encrypted_response = encrypt(response)
        return Response(data=encrypted_response, status=status.HTTP_201_CREATED)


class ResetPassword(generics.CreateAPIView):
    serializer_class = ResetPasswordSerializer

    def create(self, request):
        decrypted_payload = decrypt(request.data)
        payload = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_payload.items()
        }
        serializer = self.get_serializer(data=payload)
        if not serializer.is_valid(raise_exception=True):
            return Response(data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST)

        user_data = serializer.validated_data
        user_id = payload.get("user_id")

        try:
            user = User.objects.get(id=user_id)
            logger.info(f"User found for ID: {user.id}")
        except User.DoesNotExist:
            logger.error(f"User not found with ID: {user_id}")
            return Response(
                data=encrypt({"error": "User not found"}),
                status=status.HTTP_404_NOT_FOUND,
            )

        if user_data["password"] != user_data["password2"]:
            logger.warning("Passwords do not match for user ID: %s", user_id)
            return Response(
                data=encrypt({"error": "Passwords do not match!"}),
                status=status.HTTP_400_BAD_REQUEST,
            )

        password = user_data["password"]
        user.password = make_password(password)

        user_token = payload.get("refresh_token")
        if user_token:
            token = RefreshToken(user_token)
            token.blacklist()
            logger.info(f"Refresh token blacklisted for user: {user_id}")

        user.save()

        UserNotification.objects.create(
            user=user,
            title="Password Reset.",
            message="Your password reset is successful.",
        )

        ActivityModel.objects.create(
            user=user,
            title="Password Reset.",
            description=f"{user.first_name} {user.last_name} reset their password.",
        )

        response = {"status": "success!", "message": "Password reset successfully"}
        encrypted_response = encrypt(response)
        return Response(data=encrypted_response, status=status.HTTP_200_OK)


class SubmitGamification(generics.CreateAPIView):
    """
    SubmitGamification handles the POST request that allows a User/Member
    to submit a gamification task result.
    """

    serializer_class = SubmitGamificationSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsUserOrMember)

    def post(self, request):
        decrypted_payload = decrypt(request.data)
        payload = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_payload.items()
        }

        current_user = request.user
        serializer = self.get_serializer(data=payload)
        if not serializer.is_valid(raise_exception=True):
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        task_id = serializer.validated_data["task_id"]

        try:
            task = GamificationModel.objects.get(task_id=task_id)
            logger.info(f"Gamification task found: {task_id}")
        except User.DoesNotExist:
            logger.error(f"Gamification task not found for ID: {task_id}")
            raise Customexceptions.not_found(item_not_found=task_id)

        task.url = serializer.validated_data["task_url"]
        task.save()

        UserNotification.objects.create(
            user=request.user,
            title="Submit Gamification.",
            message="You have successfully submitted your gamification task.",
        )

        ActivityModel.objects.create(
            user=current_user,
            title="Submit Gamification.",
            description=f"{current_user.first_name} {current_user.last_name} submitted a gamification task.",
        )

        response_data = {
            "status": "Success",
            "message": "Task submitted successfully, please wait for review.",
            "data": {
                "task_id": task.task_id,
                "title": task.title,
                "description": task.description,
            },
        }
        encrypt_response = encrypt(response_data)

        logger.info(f"Gamification task {task_id} submission completed successfully")
        return Response(data=encrypt_response, status=status.HTTP_200_OK)


class Logout(APIView):
    serializer_class = LogoutSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        description="Logout view",
        responses={200: {"description": "Logout message"}},
    )
    def post(self, request):
        decrypted_payload = decrypt(request.data)
        payload = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_payload.items()
        }
        try:
            refresh_token = payload["refresh_token"]
            if refresh_token is None:
                logger.warning("Refresh token is missing for logout request.")
                return Response(
                    {"error": "Refresh token is required."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            token = RefreshToken(refresh_token)
            token.blacklist()
            logger.info("Refresh token blacklisted for user: %s", request.user.id)

            current_user = request.user
            UserNotification.objects.create(
                user=current_user,
                title="Logout.",
                message="You have successfully logged out.",
            )

            ActivityModel.objects.create(
                user=current_user,
                title="Logout.",
                description=f"{current_user.first_name} {current_user.last_name} logged out.",
            )

            response = {"status": "success", "logout": "Logout successful!"}
            encrypted_response = encrypt(response)
            return Response(
                data=encrypted_response,
                status=status.HTTP_205_RESET_CONTENT,
            )

        except Exception as e:
            logger.error(f"Error during logout: {str(e)}")
            return Response(status=status.HTTP_400_BAD_REQUEST, data={"error": str(e)})
