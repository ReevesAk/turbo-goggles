import logging

# Third party imports.
from rest_framework import serializers

# In project imports.
from .models import User
from .utils import mask_email, mask_phone

logger = logging.getLogger(__name__)


class RegisterSerializer(serializers.ModelSerializer):
    """Serailizers for our User first time registration."""

    password = serializers.CharField(
        max_length=68, min_length=10, write_only=True, style={"input_type": "password"}
    )
    password2 = serializers.CharField(
        max_length=68, min_length=10, write_only=True, style={"input_type": "password"}
    )
    device_id = serializers.CharField(max_length=68, min_length=10, write_only=True)
    device_name = serializers.CharField(max_length=68, min_length=10, write_only=True)
    device_os = serializers.CharField(max_length=68, min_length=10, write_only=True)
    referral_code = serializers.CharField(
        max_length=50, min_length=3, write_only=True, required=False, allow_blank=True
    )
    consent_given = serializers.BooleanField(write_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "device_id",
            "device_os",
            "device_name",
            "phone_number",
            "password",
            "password2",
            "referral_code",
            "profile_img_url",
            "consent_given",
        ]
        extra_kwargs = {
            "password": {"write_only": True},
        }

    def validate(self, attrs):
        return super().validate(attrs)

    def create(self, validated_data):
        validated_data.pop("profile_img_url", None)
        validated_data.pop("consent_given", None)  # stamped by the view after save

        user = User.objects.create(
            email=validated_data["email"],
            first_name=validated_data["first_name"],
            last_name=validated_data["last_name"],
            phone_number=validated_data["phone_number"],
        )

        user.set_password(validated_data["password"])
        user.save()

        logger.info("New user registered: %s", mask_email(user.email))
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
    device_id = serializers.CharField(max_length=68, min_length=6, write_only=True)
    device_name = serializers.CharField(max_length=68, min_length=6, write_only=True)
    device_os = serializers.CharField(max_length=68, min_length=6, write_only=True)

    class Meta:
        model = User
        fields = [
            "phone_number",
            "password",
            "use_biometrics",
            "device_id",
            "device_name",
            "device_os",
        ]

    def validate(self, attrs):
        phone_number = attrs.get("phone_number")
        logger.info("Login attempt with phone number: %s", mask_phone(phone_number))
        return super().validate(attrs)


class VerifyOTPSerializer(serializers.Serializer):
    otp = serializers.CharField()

    def validate(self, attrs):
        logger.info("OTP verification attempt received")
        return attrs


class NewDeviceOTPVerifyOTPSerializer(serializers.Serializer):
    otp = serializers.CharField(max_length=6, write_only=True, required=True)
    device_Id = serializers.CharField(max_length=100, write_only=True, required=True)
    device_name = serializers.CharField(max_length=50, write_only=True, required=True)
    device_os = serializers.CharField(max_length=50, write_only=True, required=True)

    def validate(self, attrs):
        logger.info("OTP verification attempt received")
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
        logger.info("OTP resend request for phone number: %s", mask_phone(phone_number))
        return attrs


class ForgotPasswordSerializer(serializers.ModelSerializer):
    phone_number = serializers.CharField(max_length=68, min_length=6, write_only=True)

    class Meta:
        model = User
        fields = ["phone_number"]

    def validate(self, attrs):
        return attrs


class PasswordResendOTPSerializer(serializers.Serializer):
    """Serailizers for resending OTP to our users."""

    phone_number = serializers.CharField()

    class Meta:
        model = User
        fields = ["id", "phone_number"]

    def validate(self, attrs):
        return attrs


class ResetPasswordSerializer(serializers.ModelSerializer):
    password = serializers.CharField(max_length=68, min_length=10, write_only=True)
    password2 = serializers.CharField(max_length=68, min_length=10, write_only=True)
    user_id = serializers.CharField(max_length=68, write_only=True)

    class Meta:
        model = User
        fields = ("user_id", "password", "password2")

    def validate(self, attrs):
        return attrs


class LogoutSerializer(serializers.Serializer):
    refresh_token = serializers.CharField(max_length=200)

    class Meta:
        model = User
        fields = [
            "refresh_token",
        ]
