import logging

# Third party imports.
from rest_framework import serializers

# In project imports.
from .models import User
from roles.models import GamificationModel

from security import encrypt

logger = logging.getLogger(__name__)


class RegisterSerializer(serializers.ModelSerializer):
    """Serailizers for our User first time registration."""

    password = serializers.CharField(
        max_length=68, min_length=6, write_only=True, style={"input_type": "password"}
    )
    password2 = serializers.CharField(
        max_length=68, min_length=6, write_only=True, style={"input_type": "password"}
    )
    device_id = serializers.CharField(max_length=68, min_length=6, write_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "device_id",
            "phone_number",
            "password",
            "password2",
            "profile_img_url",
        ]
        extra_kwargs = {
            "password": {"write_only": True},
        }

    def validate(self, attrs):
        email = attrs.get("email", "")
        phone_number = attrs.get("phone_number", "")

        if email:
            email_exists = User.objects.filter(email=email).exists()
            if email_exists:
                logger.warning("Registration attempt with already used email: %s", email)
                raise serializers.ValidationError(encrypt("Email has already been used"))

        if phone_number:
            phone_exists = User.objects.filter(phone_number=phone_number).exists()
            if phone_exists:
                logger.warning("Registration attempt with already used phone number: %s", phone_number)
                raise serializers.ValidationError(encrypt("Phone number has already been used"))

        return super().validate(attrs)

    def create(self, validated_data):
        validated_data.pop("profile_img_url", None)

        user = User.objects.create(
            email=validated_data["email"],
            first_name=validated_data["first_name"],
            last_name=validated_data["last_name"],
            phone_number=validated_data["phone_number"],
        )

        user.set_password(validated_data["password"])
        user.save()

        logger.info("New user registered with email: %s", user.email)
        return user


class GetUserSerializer(serializers.ModelSerializer):
    """Serailizers for retrieving User profile."""

    class Meta:
        model = User
        fields = [
            "id",
            "first_name",
            "last_name",
            "active_role",
            "country",
            "state",
            "city",
            "phone_number",
            "email",
            "created_at",
            "updated_at",
            "is_verified",
        ]


class UpdateUserSerializer(serializers.ModelSerializer):
    """Serailizers for updating our users' profile."""

    class Meta:
        model = User
        fields = [
            "id",
            "country",
            "state",
            "city",
            "created_at",
            "updated_at",
        ]


class LoginSerializers(serializers.ModelSerializer):
    use_biometrics = serializers.BooleanField(required=False)

    class Meta:
        model = User
        fields = ["phone_number", "password", "use_biometrics"]

    def validate(self, attrs):
        phone_number = attrs.get("phone_number")
        logger.info("Login attempt with phone number: %s", phone_number)
        return super().validate(attrs)


class VerifyOTPSerializer(serializers.Serializer):
    otp = serializers.CharField()

    def validate(self, attrs):
        otp = attrs.get("otp")
        logger.info("OTP verification attempt for OTP: %s", otp)
        return attrs


class ResendOTPSerializer(serializers.Serializer):
    """Serailizers for resending OTP to our users."""

    phone_number = serializers.CharField()
    id = serializers.IntegerField()

    class Meta:
        model = User
        fields = ["id", "phone_number"]

    def validate(self, attrs):
        phone_number = attrs.get("phone_number")
        logger.info("OTP resend request for phone number: %s", phone_number)
        return attrs


class ForgotPasswordSerializer(serializers.ModelSerializer):
    phone_number = serializers.CharField(max_length=68, min_length=6, write_only=True)

    class Meta:
        model = User
        fields = ["phone_number"]

    def validate(self, attrs):
        phone_number = attrs.get("phone_number")
        logger.info("Forgot password request for phone number: %s", phone_number)
        return attrs


class PasswordResendOTPSerializer(serializers.Serializer):
    """Serailizers for resending OTP to our users."""

    phone_number = serializers.CharField()

    class Meta:
        model = User
        fields = ["id", "phone_number"]

    def validate(self, attrs):
        phone_number = attrs.get("phone_number")
        logger.info("Password reset request for phone number: %s", phone_number)
        return attrs


class ResetPasswordSerializer(serializers.ModelSerializer):
    password = serializers.CharField(max_length=68, min_length=6, write_only=True)
    password2 = serializers.CharField(max_length=68, min_length=6, write_only=True)
    user_id = serializers.CharField(max_length=68, write_only=True)

    class Meta:
        model = User
        fields = ("user_id", "password", "password2")

    def validate(self, attrs):
        user_id = attrs.get("user_id")
        user = User.objects.get(id=user_id)
        logger.info("OTP resend request for phone number: %s", user.phone_number)
        return attrs


class LogoutSerializer(serializers.Serializer):
    refresh_token = serializers.CharField(max_length=200)

    class Meta:
        model = User
        fields = [
            "refresh_token",
        ]


class SubmitGamificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = GamificationModel
        fields = ["task_id", "task_url"]

    def validate(self, attrs):
        task_id = attrs.get("task_id")
        logger.info("Submit task request for phone number: %s", task_id)
        return attrs
