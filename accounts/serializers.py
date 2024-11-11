# Third party imports.
from rest_framework import serializers

# In project imports.
from .models import User
from roles.models import GamificationModel


class RegisterSerializer(serializers.ModelSerializer):
    """Serailizers for our User first time registration."""

    password = serializers.CharField(
        max_length=68, min_length=6, write_only=True, style={"input_type": "password"}
    )
    password2 = serializers.CharField(
        max_length=68, min_length=6, write_only=True, style={"input_type": "password"}
    )
    device_id = serializers.CharField(max_length=68, min_length=6, write_only=True)
    profile_image = serializers.ImageField(required=False, allow_null=True)

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
            "profile_image",
        ]
        extra_kwargs = {
            "password": {"write_only": True},
        }

    def validate(self, attrs):
        email = attrs.get("email", "")

        if email:
            email_exists = User.objects.filter(email=email).exists()
            if email_exists:
                raise serializers.ValidationError("Email has already been used")
        else:
            raise serializers.ValidationError("email: email field can not be empty")

        return super().validate(attrs)

    def create(self, validated_data):
        validated_data.pop("profile_image", None)

        user = User.objects.create(
            email=validated_data["email"],
            first_name=validated_data["first_name"],
            last_name=validated_data["last_name"],
            phone_number=validated_data["phone_number"],
        )

        user.set_password(validated_data["password"])
        user.save()

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


class VerifyOTPSerializer(serializers.Serializer):
    otp = serializers.CharField()


class ResendOTPSerializer(serializers.Serializer):
    """Serailizers for resending OTP to our users."""

    phone_number = serializers.CharField()
    id = serializers.IntegerField()

    class Meta:
        model = User
        fields = ["id", "phone_number"]


class ForgotPasswordSerializer(serializers.ModelSerializer):
    phone_number = serializers.CharField(max_length=68, min_length=6, write_only=True)

    class Meta:
        model = User
        fields = ["phone_number"]


class PasswordResendOTPSerializer(serializers.Serializer):
    """Serailizers for resending OTP to our users."""

    phone_number = serializers.CharField()

    class Meta:
        model = User
        fields = ["id", "phone_number"]


class ResetPasswordSerializer(serializers.ModelSerializer):
    password = serializers.CharField(max_length=68, min_length=6, write_only=True)
    password2 = serializers.CharField(max_length=68, min_length=6, write_only=True)
    user_id = serializers.CharField(max_length=68, write_only=True)

    class Meta:
        model = User
        fields = ("user_id", "password", "password2")


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
