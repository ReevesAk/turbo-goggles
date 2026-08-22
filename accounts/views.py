from django.utils import timezone
from datetime import timedelta

import logging

from django.core.cache import cache
from django.template.loader import render_to_string

# Third party imports.
from rest_framework import generics
from django.contrib.auth import authenticate
from django.contrib.auth.hashers import make_password, check_password
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

import rest_framework.serializers as s
from drf_spectacular.utils import extend_schema, inline_serializer

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
    NewDeviceOTPVerifyOTPSerializer,
    DeleteAccountSerializer,
)
from .models import User, DeviceId, AccountType, UserNotification, UserDeletion
from .otp import otp_manager
from .tokens import create_jwt_pair_for_user
from roles.models import ActivityModel
from gamification.points import Points
from gamification.referrals import Referrals
from gamification.models import StreakChallenge
from waitlist.models import WaitlistModel
from commons import Biometrics, Messaging
from security import encrypt, decrypt
from .utils import mask_email, mask_phone

logger = logging.getLogger("accounts")


@extend_schema(
    summary="Register a new user",
    tags=["Auth"],
    description="Create a new member account. On success an OTP is sent to the supplied phone number via WhatsApp/SMS for verification.",
    request=RegisterSerializer,
    responses={
        201: inline_serializer(
            name="RegisterResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "image": s.CharField(allow_null=True),
            },
        ),
        400: inline_serializer(
            name="RegisterErrorResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class Register(generics.GenericAPIView):
    """
    Register handles the POST request of registering a user,
    It takes in firstname, lastname, username, email and password
    and returns a validation email upon success.
    """

    serializer_class = RegisterSerializer

    def post(self, request):
        decrypted_payload = decrypt(request.data)
        user_data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_payload.items()
        }

        if not user_data.get("consent_given"):
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "You must accept the privacy policy and terms to register.",
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        email = user_data.get("email")
        if email and User.objects.filter(email=email).exists():
            logger.warning(
                "Registration attempt with already used email: %s", mask_email(email)
            )
            return Response(
                data=encrypt(
                    {"status": "fail", "message": "This email is already registered!"}
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        phone_number = user_data.get("phone_number")
        if phone_number and User.objects.filter(phone_number=phone_number).exists():
            logger.warning(
                "Registration attempt with already used phone number: %s",
                mask_phone(phone_number),
            )
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "This phone number is already registered!",
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        referred_by_code = user_data.get("referred_by_code")
        referrer = None
        referrer_code_type = None
        if referred_by_code:
            referrer = User.objects.filter(
                referral_code=referred_by_code, is_deleted=False
            ).first()
            referrer_code_type = "gamification"
            if referrer is None:
                referrer = User.objects.filter(
                    walk_to_earn_referral_code=referred_by_code, is_deleted=False
                ).first()
                referrer_code_type = "walk_to_earn"
            if referrer is None:
                return Response(
                    data=encrypt(
                        {"status": "fail", "message": "Referral code not found."}
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )

        serializer = self.serializer_class(data=user_data)
        if serializer.is_valid(raise_exception=True):
            if user_data["password"] != user_data["password2"]:
                logger.warning(
                    "Password mismatch for user: %s", mask_email(user_data.get("email"))
                )
                return Response(
                    data=encrypt(
                        {"status": "fail", "message": "Passwords do not match!"}
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )

            profile_upload = user_data.get("profile_img_url")
            logger.info("Profile image: %s", profile_upload)

            user = serializer.save()
            user.consent_given = True
            user.consent_given_at = timezone.now()
            user.save(update_fields=["consent_given", "consent_given_at"])

            user.referral_code = Referrals.generate_code(user)
            user.save(update_fields=["referral_code"])

            if email:
                waitlist_entry = WaitlistModel.objects.filter(
                    email=email, converted_user__isnull=True
                ).first()
                if waitlist_entry:
                    # Accumulated waitlist points are dropped on conversion -
                    # only the link/timestamp carries over.
                    waitlist_entry.converted_user = user
                    waitlist_entry.converted_at = timezone.now()
                    waitlist_entry.save(
                        update_fields=["converted_user", "converted_at"]
                    )
                    logger.info(
                        "Waitlist entry %s converted to user %s",
                        waitlist_entry.id,
                        mask_email(user.email),
                    )

            if referrer is not None:
                if referrer_code_type == "walk_to_earn":
                    Referrals.record_walk_to_earn_referral(
                        referrer=referrer, referred=user, code_used=referred_by_code
                    )
                else:
                    Referrals.record_referral(
                        referrer=referrer, referred=user, code_used=referred_by_code
                    )
                logger.info(
                    "Referral recorded (%s): referrer=%s referred=%s",
                    referrer_code_type,
                    mask_email(referrer.email),
                    mask_email(user.email),
                )

            AccountType.objects.create(
                user=user,
                user_type="Member",
            )
            user.active_role = "Member"
            user.is_member = True
            user.save()

            logger.info("User created: %s", mask_email(user.email))

            if profile_upload:
                try:
                    user.profile_img_url = profile_upload
                    user.save()
                    logger.info(
                        "Profile image uploaded for user: %s", mask_email(user.email)
                    )
                except Exception as e:
                    logger.error(
                        "Error uploading profile image for user %s: %s",
                        mask_email(user.email),
                        str(e),
                    )

            ActivityModel.objects.create(
                user=user,
                title="Member Registration",
                description=f"{user.first_name} {user.last_name} just registered as a Member.",
            )

            # Create and send OTP.
            otp = otp_manager.create_otp(user_id=str(user.id))

            msg = "Your Picadailys verification code is {otp}. Do not share this code with anyone. Expires in 5 minutes.".format(
                otp=otp
            )
            recipient = serializer.data["phone_number"][1:]

            Messaging.send_otp_whatsapp_first(phone_number=recipient, otp=otp, msg=msg)

            # Render the template with values
            text_content = render_to_string(
                template_name="empty_email.html",
                context={
                    "custom_text": f"Dear {user.first_name},<br><br>{msg}.",
                    "support_email": "notifications@picadailys.com",
                    "picadailys_phone": "012271894 0202012271895",
                },
            )

            Messaging.send_email(
                email=user.email,
                html_content=text_content,
                sender_email="notifications@picadailys.com",
                body=msg,
                subject="Picadailys Registration",
            )

            device_id = user_data.get("device_id")
            DeviceId.objects.create(user=user, device_id=device_id)

            response = {
                "status": "success",
                "message": "User Created Successfully. Check your phone for an OTP",
                "image": user.profile_img_url,
                "data": serializer.data,
            }
            logger.info("Registration successful for user: %s", mask_email(user.email))
            return Response(data=encrypt(response), status=status.HTTP_201_CREATED)
        else:
            logger.error(
                "Registration failed for user: %s, errors: %s",
                mask_email(user_data.get("email")),
                serializer.errors,
            )
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "Validation error occurred.",
                        "errors": serializer.errors,
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )


@extend_schema(
    summary="Verify OTP for new device",
    tags=["Auth"],
    description="Confirm a new device by submitting the OTP sent during login. On success the device is registered and JWT tokens are returned.",
    request=NewDeviceOTPVerifyOTPSerializer,
    responses={
        200: inline_serializer(
            name="DeviceVerifyOTPResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "tokens": inline_serializer(
                    name="DeviceVerifyTokens",
                    fields={"access": s.CharField(), "refresh": s.CharField()},
                ),
            },
        ),
        400: inline_serializer(
            name="DeviceVerifyOTPErrorResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class DeviceVerificationOTP(generics.GenericAPIView):
    """
    DeviceVerificationOTP handles the POST request of verifying a
    new user's new device.
    """

    permission_classes = (AllowAny,)
    serializer_class = NewDeviceOTPVerifyOTPSerializer
    throttle_scope = "otp"

    def post(self, request):
        decrypted_payload = decrypt(request.data)
        user_data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_payload.items()
        }
        serializer = self.serializer_class(data=user_data)
        if serializer.is_valid(raise_exception=True):
            data = serializer.validated_data
            received_otp = data["otp"]

            # Validate OTP
            user_id = otp_manager.validate_user_otp(received_otp)
            if not user_id:
                logger.warning("Invalid or expired OTP.")
                return Response(
                    data=encrypt(
                        {"status": "fail", "message": "Invalid or expired OTP"}
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )

            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                logger.error("User with id %s does not exist.", user_id)
                return Response(
                    data=encrypt({"status": "fail", "message": "User not found"}),
                    status=status.HTTP_404_NOT_FOUND,
                )

            device_id = data["device_Id"]
            device_name = data["device_name"]
            device_os = data["device_os"]

            # Delete old device
            DeviceId.objects.filter(user=user).delete()

            device_id = device_id.strip().lower()

            # Save new device
            DeviceId.objects.create(
                user=user,
                device_id=device_id,
                device_name=device_name,
                device_os=device_os,
            )

            # Send welcome message to user
            msg = "Your new device has been verified! You are now logged in."

            if user.alert_type_choice in ("SMS", "Both"):
                recipient = user.phone_number[1:]

                Messaging.send_sms(phone_number=recipient, msg=msg)
            if user.alert_type_choice in ("Email", "Both"):
                # Render the template with values
                text_content = render_to_string(
                    template_name="empty_email.html",
                    context={
                        "custom_text": f"Dear {user.first_name},<br><br>{msg}.",
                        "support_email": "support@picadailys.com",
                        "picadailys_phone": "02012271894 02012271895",
                    },
                )

                Messaging.send_email(
                    email=user.email,
                    html_content=text_content,
                    subject="Welcome To Picadailys",
                    body=msg,
                    sender_email="notifications@picadailys.com",
                )

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

            # Create JWT tokens
            tokens = create_jwt_pair_for_user(user)
            logger.info("JWT tokens generated for user %s", user.phone_number)
            verified_response = {
                "status": "success",
                "message": "Account is verified",
                "tokens": tokens,
            }
            encrypted_response = encrypt(verified_response)
            return Response(data=encrypted_response, status=status.HTTP_200_OK)
        else:
            logger.error(
                "Serializer validation failed with errors: %s", serializer.errors
            )
            return Response(
                data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST
            )


@extend_schema(
    summary="Verify phone OTP after registration",
    tags=["Auth"],
    description="Validate the OTP sent to the user's phone after registration to activate the account and receive JWT tokens.",
    request=VerifyOTPSerializer,
    responses={
        200: inline_serializer(
            name="PhoneVerifyOTPResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "tokens": inline_serializer(
                    name="PhoneVerifyTokens",
                    fields={"access": s.CharField(), "refresh": s.CharField()},
                ),
            },
        ),
        400: inline_serializer(
            name="PhoneVerifyOTPErrorResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class PhoneVerifyOTP(generics.GenericAPIView):
    """
    PhoneVerifyOTP handles the POST request of verifying a
    registered user/partner with valid phone number.
    """

    permission_classes = (AllowAny,)
    serializer_class = VerifyOTPSerializer
    throttle_scope = "otp"

    def post(self, request):
        decrypted_payload = decrypt(request.data)
        user_data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_payload.items()
        }
        serializer = self.serializer_class(data=user_data)
        if serializer.is_valid(raise_exception=True):
            received_otp = serializer.data["otp"]

            # Validate OTP
            user_id = otp_manager.validate_user_otp(received_otp)
            if not user_id:
                logger.warning("Invalid or expired OTP.")
                return Response(
                    data=encrypt(
                        {"status": "fail", "message": "Invalid or expired OTP"}
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )

            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                logger.error("User with id %s does not exist.", user_id)
                return Response(
                    data=encrypt({"status": "fail", "message": "User not found"}),
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Send welcome message to user
            msg = "Welcome to Picadailys App...we are thrilled to have you onboard. Get ready to unlock a world of possibilities and seamless experiences. Thank you for choosing us!"

            if user.alert_type_choice in ("SMS", "Both"):
                recipient = user.phone_number[1:]

                Messaging.send_sms(phone_number=recipient, msg=msg)
                logger.info("Welcome message sent to user %s at %s", user.id, recipient)

            if user.alert_type_choice in ("Email", "Both"):
                # Render the template with values
                text_content = render_to_string(
                    template_name="empty_email.html",
                    context={
                        "custom_text": f"Dear {user.first_name},<br><br>{msg}.",
                        "support_email": "support@picadailys.com",
                        "picadailys_phone": "02012271894  02012271895",
                    },
                )

                Messaging.send_email(
                    email=user.email,
                    html_content=text_content,
                    subject="Welcome To Picadailys",
                    body=msg,
                    sender_email="notifications@picadailys.com",
                )

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

            # Create JWT tokens
            tokens = create_jwt_pair_for_user(user)
            verified_response = {
                "status": "success",
                "message": "Account is verified",
                "tokens": tokens,
            }
            encrypted_response = encrypt(verified_response)
            return Response(data=encrypted_response, status=status.HTTP_200_OK)
        else:
            logger.error("Serializer validation failed.")
            return Response(
                data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST
            )


@extend_schema(
    summary="Verify OTP for password reset",
    tags=["Auth"],
    description="Validate the OTP sent to the user's phone as part of the forgot-password flow. Returns the user_id needed to call the reset-password endpoint.",
    request=VerifyOTPSerializer,
    responses={
        200: inline_serializer(
            name="PasswordPhoneVerifyOTPResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "user_id": s.CharField(),
            },
        ),
        400: inline_serializer(
            name="PasswordPhoneVerifyOTPErrorResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
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

        serializer = self.serializer_class(data=user_data)
        if serializer.is_valid(raise_exception=True):
            received_otp = serializer.data["otp"]

            # Validate OTP
            user_id = otp_manager.validate_user_otp(received_otp)
            if not user_id:
                logger.warning("Invalid or expired OTP during password reset.")
                return Response(
                    data=encrypt(
                        {"status": "fail", "message": "Invalid or expired OTP"}
                    ),
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
                    data=encrypt({"status": "fail", "message": "User not found"}),
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Send confirmation message to the user
            msg = "User is verified... You can reset your password now!"

            if user.alert_type_choice in ("SMS", "Both"):
                recipient = user.phone_number
                Messaging.send_sms(phone_number=recipient, msg=msg)
                logger.info(
                    "Password reset verification message sent to user %s at %s",
                    user.id,
                    recipient,
                )
            if user.alert_type_choice in ("Email", "Both"):
                text_content = render_to_string(
                    template_name="empty_email.html",
                    context={
                        "custom_text": f"Dear {user.first_name},<br><br>{msg}.",
                        "support_email": "support@picadailys.com",
                        "picadailys_phone": "02012271894  02012271895",
                    },
                )

                Messaging.send_email(
                    email=user.email,
                    html_content=text_content,
                    subject="Password Reset Verification",
                    body=msg,
                    sender_email="notifications@picadailys.com",
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
            return Response(
                data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST
            )


@extend_schema(
    summary="Resend OTP to user",
    tags=["Auth"],
    description="Resend the verification OTP to the user's registered phone number during the registration flow.",
    request=ResendOTPSerializer,
    responses={
        200: inline_serializer(
            name="ResendOTPResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        400: inline_serializer(
            name="ResendOTPErrorResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
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
        logger.debug("Resend OTP request received.")
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

            # Send OTP message
            msg = "Your Picadailys verification code is {otp}. Do not share this code with anyone. Expires in 5 minutes.".format(
                otp=otp
            )
            Messaging.send_otp_whatsapp_first(
                phone_number=phone_number, otp=otp, msg=msg
            )

            # Prepare response
            response = {
                "status": "success",
                "message": "OTP resent successfully. Check your phone for validation.",
            }
            encrypted_response = encrypt(response)
            return Response(data=encrypted_response, status=status.HTTP_200_OK)

        else:
            # Log validation errors
            logger.error("Resend OTP validation failed.")
            return Response(
                data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST
            )


@extend_schema(
    summary="Resend OTP for password reset",
    tags=["Auth"],
    description="Resend a password-reset OTP to the phone number associated with the account.",
    request=PasswordResendOTPSerializer,
    responses={
        200: inline_serializer(
            name="PasswordResendOTPResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        404: inline_serializer(
            name="PasswordResendOTPNotFoundResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class PasswordResendOTP(generics.GenericAPIView):
    """
    PasswordResendOTP handles the POST request of resending an
    OTP to a user after password reset.
    """

    permission_classes = (AllowAny,)
    serializer_class = PasswordResendOTPSerializer

    def post(self, request):
        decrypted_payload = decrypt(request.data)

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
                logger.info("Generated OTP for user ID: %s", user.id)

                msg = "To reset your password, use this code {}.".format(otp)

                # Send OTP — WhatsApp as fallback since initial was SMS
                if user.alert_type_choice in ("SMS", "Both"):
                    Messaging.send_otp_whatsapp_fallback(
                        phone_number=phone_number, otp=otp, msg=msg
                    )
                if user.alert_type_choice in ("Email", "Both"):
                    text_content = render_to_string(
                        template_name="empty_email.html",
                        context={
                            "custom_text": f"Dear {user.first_name},<br><br>{msg}.",
                            "support_email": "support@picadailys.com",
                            "picadailys_phone": "02012271894  02012271895",
                        },
                    )

                    Messaging.send_email(
                        email=user.email,
                        html_content=text_content,
                        subject="Password Resend OTP",
                        body=msg,
                        sender_email="notifications@picadailys.com",
                    )

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
            logger.error("OTP resend validation failed.")
            return Response(
                data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST
            )


@extend_schema(
    summary="Login with password or biometrics",
    tags=["Auth"],
    description="Authenticate a verified user using phone number + password or biometrics. Returns JWT access and refresh tokens on success; triggers an OTP challenge if a new device is detected.",
    request=LoginSerializers,
    responses={
        200: inline_serializer(
            name="LoginResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "active_role": s.CharField(),
                "user_id": s.CharField(),
                "is_verified": s.BooleanField(),
                "tokens": inline_serializer(
                    name="LoginTokens",
                    fields={"access": s.CharField(), "refresh": s.CharField()},
                ),
            },
        ),
        400: inline_serializer(
            name="LoginNewDeviceResponse",
            fields={"status": s.CharField(), "error": s.CharField()},
        ),
        401: inline_serializer(
            name="LoginUnauthorizedResponse",
            fields={"error": s.CharField()},
        ),
        403: inline_serializer(
            name="LoginLockedResponse",
            fields={"error": s.CharField()},
        ),
    },
)
class Login(APIView):
    """
    LoginAPIView handles the POST request for logging in
    a verified user with valid biometrics or password credentials.
    """

    serializer_class = LoginSerializers
    throttle_scope = "login"

    def post(self, request):
        decrypted_payload = decrypt(request.data)
        data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_payload.items()
        }
        login = data.get("phone_number")
        password = data.get("password")
        biometrics = data.get("use_biometrics")
        device_id = data.get("device_id")

        logger.info("Login attempt for phone number: %s", login)

        # Get user object for password attempt tracking
        user_obj = User.objects.filter(phone_number=login).first()
        if (
            user_obj
            and user_obj.password_locked_until
            and user_obj.password_locked_until > timezone.now()
        ):
            return Response(
                data=encrypt(
                    {
                        "error": "Account locked due to too many failed login attempts. Try again later."
                    }
                ),
                status=status.HTTP_403_FORBIDDEN,
            )

        # Check if biometrics is requested
        if biometrics:
            user = Biometrics.authenticate(login)
            logger.info("Biometric authentication attempted for user: %s", login)
        else:
            user = authenticate(phone_number=login, password=password)
            logger.info("Password authentication attempted for user: %s", login)

        logger.info("INCOMING DEVICE ID: %s", device_id)
        stored = list(
            DeviceId.objects.filter(user=user).values_list("device_id", flat=True)
        )
        logger.info("STORED DEVICE ID: %s", stored)

        # If authentication fails, increment attempts and maybe lock
        if not user:
            logger.warning("Invalid credentials for user: %s", login)
            if user_obj:
                user_obj.password_attempts = (user_obj.password_attempts or 0) + 1
                if user_obj.password_attempts >= 4:
                    user_obj.password_locked_until = timezone.now() + timedelta(
                        minutes=30
                    )
                    user_obj.save(
                        update_fields=["password_attempts", "password_locked_until"]
                    )
                    return Response(
                        data=encrypt(
                            {
                                "error": "Too many failed login attempts. Account locked for 30 minutes."
                            }
                        ),
                        status=status.HTTP_403_FORBIDDEN,
                    )
                else:
                    user_obj.save(update_fields=["password_attempts"])
            return Response(
                data=encrypt({"error": "Invalid credentials"}),
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # Reset attempts on successful login
        if user_obj:
            user_obj.password_attempts = 0
            user_obj.password_locked_until = None
            user_obj.save(update_fields=["password_attempts", "password_locked_until"])

        # Ensure user is verified if using password login
        if not biometrics and not user.is_verified:
            logger.warning("User %s is not verified, cannot login", login)

            # Send verification OTP to the user's email, as in ResendOTP
            otp = otp_manager.create_otp(user_id=str(user.id))
            msg = "Your Picadailys verification code is {otp}. Do not share this code with anyone. Expires in 5 minutes.".format(
                otp=otp
            )

            if user.alert_type_choice in ("Email", "Both"):
                text_content = render_to_string(
                    template_name="empty_email.html",
                    context={
                        "custom_text": f"Dear {user.first_name},<br><br>{msg}.",
                        "support_email": "notifications@picadailys.com",
                        "picadailys_phone": "02012271894 02012271895",
                    },
                )

                Messaging.send_email(
                    email=user.email,
                    html_content=text_content,
                    sender_email="notifications@picadailys.com",
                    body=msg,
                    subject="Picadailys Verification",
                )

            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "Please verify your account to login",
                        "data": {
                            "user_id": str(user.id),
                            "is_verified": user.is_verified,
                            "phone_number": user.phone_number,
                        },
                    }
                ),
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # Normalize device ID for consistent comparison
        # device_id = str(device_id).strip().lower()

        # Check device limit for password login only
        # is_known_device = self.check_device_limit(
        #     user, device_id, device_name, device_os
        # )

        # if not is_known_device:
        #     logger.warning("New device detected for user: %s", login)

        #     # Create and send OTP.
        #     otp = otp_manager.create_otp(user_id=str(user.id))

        #     msg = "Your Picadailys verification code is {otp}. Do not share this code with anyone. Expires in 5 minutes.".format(
        #         otp=otp
        #     )
        #     recipient = user.phone_number[1:]

        #     if user.alert_type_choice in ("SMS", "Both"):
        #         Messaging.send_sms(phone_number=recipient, msg=msg)
        #     if user.alert_type_choice in ("Email", "Both"):
        #         # Render the template with values
        #         text_content = render_to_string(
        #             template_name="empty_email.html",
        #             context={
        #                 "custom_text": f"Dear {user.first_name},<br><br>{msg}.",
        #                 "support_email": "notifications@picadailys.com",
        #                 "picadailys_phone": "02012271894 02012271895",
        #             },
        #         )

        #         Messaging.send_email(
        #             email=user.email,
        #             html_content=text_content,
        #             sender_email="notifications@picadailys.com",
        #             body=msg,
        #             subject="Picadailys Registration",
        #         )
        #     return Response(
        #         data=encrypt(
        #             {
        #                 "status": "failed",
        #                 "error": "New device detected. OTP sent for verification.",
        #                 "device_data": {
        #                     "device_id": device_id,
        #                     "device_name": device_name,
        #                     "device_os": device_os,
        #                 },
        #             }
        #         ),
        #         status=status.HTTP_400_BAD_REQUEST,
        #     )

        # Successful login
        return self._handle_login_success(user)

    @staticmethod
    def check_device_limit(user, device_id, device_name, device_os):
        device_id = str(device_id).strip().lower()
        device_name = str(device_name).strip().lower()
        device_os = str(device_os).strip().lower()

        devices = DeviceId.objects.filter(user=user)
        if not devices.exists():
            return True

        for device in devices:
            if (
                (device.device_id or "").strip().lower() == device_id
                and (device.device_name or "").strip().lower() == device_name
                and (device.device_os or "").strip().lower() == device_os
            ):
                return True

        return False

    def _handle_login_success(self, user):
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
        if user.has_done_survey:
            active_campaign = StreakChallenge.objects.filter(
                streak_type="daily_login",
                is_active=True,
                is_paused=False,
                start_date__lte=timezone.now(),
                end_date__gte=timezone.now(),
            ).first()
            # user.last_login still holds the *previous* login here — it's only
            # overwritten below — so this tells us whether they were already
            # credited today.
            already_logged_in_today = (
                user.last_login is not None
                and user.last_login.date() == timezone.now().date()
            )
            if active_campaign and not already_logged_in_today:
                points = Points.determine(activity_type="daily_login", level=user.level)
                Points.award(
                    user, amount=points, reason="Daily login", source="daily_login"
                )

        user.last_login = timezone.now()
        user.save(update_fields=["last_login"])

        # Create JWT tokens
        tokens = create_jwt_pair_for_user(user)

        response = {
            "status": "success",
            "message": "Login successful",
            "active_role": user.active_role,
            "user_id": str(user.id),
            "is_verified": user.is_verified,
            "tokens": tokens,
        }
        encrypted_response = encrypt(response)
        return Response(data=encrypted_response, status=status.HTTP_200_OK)


@extend_schema(
    summary="Send OTP for forgotten password",
    tags=["Auth"],
    description="Initiate a password reset by sending a one-time code to the phone number associated with the account.",
    request=ForgotPasswordSerializer,
    responses={
        201: inline_serializer(
            name="ForgotPasswordResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        404: inline_serializer(
            name="ForgotPasswordNotFoundResponse",
            fields={"status": s.CharField(), "detail": s.CharField()},
        ),
    },
)
class ForgotPassword(generics.GenericAPIView):
    """
    ForgotPassword handles the POST request of sending a
    forgot password request.
    """

    throttle_scope = "password_change"
    serializer_class = ForgotPasswordSerializer

    def post(self, request):
        decrypted_payload = decrypt(request.data)
        user_data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_payload.items()
        }
        serializer = self.serializer_class(data=user_data)
        if not serializer.is_valid(raise_exception=True):
            return Response(
                data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST
            )

        phone_no = user_data["phone_number"][1:]
        try:
            user = User.objects.get(phone_number=user_data["phone_number"])
            logger.info(f"User found for phone number: {user.phone_number}")
        except User.DoesNotExist:
            logger.warning(
                f"No user found with phone number: {user_data['phone_number']}"
            )
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "detail": "A user with this phone number does not exist",
                    }
                ),
                status=status.HTTP_404_NOT_FOUND,
            )

        user_id = user.id
        otp = otp_manager.create_otp(user_id=str(user_id))
        msg = f"Enter this {otp} to verify your account and reset your password"

        if user.alert_type_choice in ("SMS", "Both"):
            Messaging.send_sms(phone_number=phone_no, msg=msg)
        if user.alert_type_choice in ("Email", "Both", None):
            text_content = render_to_string(
                template_name="empty_email.html",
                context={
                    "custom_text": f"Dear {user.first_name},<br><br>{msg}.",
                    "support_email": "support@picadailys.com",
                    "picadailys_phone": "02012271894  02012271895",
                },
            )

            Messaging.send_email(
                email=user.email,
                html_content=text_content,
                subject="Forgot Password",
                body=msg,
                sender_email="notifications@picadailys.com",
            )

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


@extend_schema(
    summary="Reset account password",
    tags=["Auth"],
    description="Set a new password using the user_id returned from the OTP verification step. The current refresh token is blacklisted on success.",
    request=ResetPasswordSerializer,
    responses={
        200: inline_serializer(
            name="ResetPasswordResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        400: inline_serializer(
            name="ResetPasswordErrorResponse",
            fields={"error": s.CharField()},
        ),
        404: inline_serializer(
            name="ResetPasswordNotFoundResponse",
            fields={"error": s.CharField()},
        ),
    },
)
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
            return Response(
                data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST
            )

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

        response = {"status": "success", "message": "Password reset successfully"}
        encrypted_response = encrypt(response)
        return Response(data=encrypted_response, status=status.HTTP_200_OK)


@extend_schema(
    summary="Logout and blacklist refresh token",
    tags=["Auth"],
    description="Invalidate the user's refresh token, ending the session. Requires a valid JWT access token in the Authorization header.",
    request=LogoutSerializer,
    responses={
        205: inline_serializer(
            name="LogoutResponse",
            fields={"status": s.CharField(), "logout": s.CharField()},
        ),
        400: inline_serializer(
            name="LogoutErrorResponse",
            fields={"error": s.CharField()},
        ),
    },
)
class Logout(APIView):
    serializer_class = LogoutSerializer
    permission_classes = (IsAuthenticated,)

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
                    data=encrypt({"error": "Refresh token is required."}),
                    status=status.HTTP_400_BAD_REQUEST,
                )
            token = RefreshToken(refresh_token)
            token.blacklist()

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
            logger.error(f"Error during logout: {str(e)}", exc_info=True)
            return Response(
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                data=encrypt(
                    {"status": "fail", "message": "Logout failed. Please try again."}
                ),
            )


@extend_schema(
    summary="Platform-wide user counts",
    tags=["Auth"],
    description=(
        "Public, unauthenticated endpoint returning platform-wide user counts "
        "for display in the mobile app. Cached for 6 hours, so figures may lag "
        "reality by up to that long."
    ),
    responses={
        200: inline_serializer(
            name="UserCountsResponse",
            fields={
                "status": s.CharField(),
                "data": inline_serializer(
                    name="UserCountsData",
                    fields={
                        "total": s.IntegerField(),
                        "members": s.IntegerField(),
                        "brands": s.IntegerField(),
                        "partners": s.IntegerField(),
                        "members_completed_survey": s.IntegerField(),
                    },
                ),
            },
        ),
    },
)
class PlatformUserCountsView(generics.GenericAPIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        cache_key = "platform_user_counts"
        data = cache.get(cache_key)

        if data is None:
            data = {
                "total": User.objects.count(),
                "members": User.objects.filter(is_member=True).count(),
                "members_completed_survey": User.objects.filter(
                    is_member=True, has_done_survey=True
                ).count(),
                "brands": User.objects.filter(account_types__user_type="BrandAd")
                .distinct()
                .count(),
                "partners": User.objects.filter(account_types__user_type="Partner")
                .distinct()
                .count(),
            }
            cache.set(cache_key, data, timeout=60 * 60 * 6)

        return Response(
            data=encrypt({"status": "success", "data": data}),
            status=status.HTTP_200_OK,
        )


@extend_schema(
    summary="Delete account",
    tags=["Auth"],
    description=(
        "Soft-deletes the authenticated user's account after verifying their "
        "password. The account and all related records (wallet, transaction "
        "history, points, etc.) are retained for compliance - the user is "
        "just excluded from active-user views and can no longer log in. "
        "An optional `reason` is logged for churn analysis."
    ),
    request=DeleteAccountSerializer,
    responses={
        200: inline_serializer(
            name="DeleteAccountResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        401: inline_serializer(
            name="DeleteAccountUnauthorized",
            fields={"status": s.CharField(), "error": s.CharField()},
        ),
        400: inline_serializer(
            name="DeleteAccountBadRequest",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class DeleteAccount(generics.GenericAPIView):
    serializer_class = DeleteAccountSerializer
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        decrypted_payload = decrypt(request.data)
        serializer = self.serializer_class(data=decrypted_payload)
        serializer.is_valid(raise_exception=True)

        user = request.user

        if not check_password(serializer.validated_data["password"], user.password):
            logger.warning("Delete account: incorrect password for user %s", user.id)
            return Response(
                data=encrypt({"status": "fail", "error": "Incorrect password."}),
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if user.is_deleted:
            return Response(
                data=encrypt({"status": "fail", "message": "Account already deleted."}),
                status=status.HTTP_400_BAD_REQUEST,
            )

        now = timezone.now()
        user.is_deleted = True
        user.deleted_at = now
        user.is_active = False
        user.save(update_fields=["is_deleted", "deleted_at", "is_active"])

        UserDeletion.objects.create(
            user=user, reason=serializer.validated_data.get("reason", "")
        )

        logger.info("User %s deleted their account.", user.id)

        return Response(
            data=encrypt(
                {"status": "success", "message": "Account deleted successfully."}
            ),
            status=status.HTTP_200_OK,
        )
