# Third party imports.
from rest_framework import serializers

# In project imports.
from .models import User


class RegisterSerializer(serializers.ModelSerializer):
    """Serailizers for our User first time registration"""

    class Meta:
        model = User
        fields = [
            "id",
            "first_name",
            "last_name",
            "account_type",
            "country",
            "state",
            "city",
            "phone_number",
            "email",
            "password",
        ]
        extra_kwargs = {"password": {"write_only": True}}

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
        user = User.objects.create(
            email=validated_data["email"],
            first_name=validated_data["first_name"],
            last_name=validated_data["last_name"],
            account_type=validated_data["account_type"],
            country=validated_data["country"],
            state=validated_data["state"],
            city=validated_data["city"],
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
            "account_type",
            "country",
            "state",
            "city",
            "phone_number",
            "email",
            "created_at",
            "updated_at",
            "is_verified",
            "is_member",
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


class VerifyOTPSerializer(serializers.Serializer):
    otp = serializers.CharField()


class ResendOTPSerializer(serializers.Serializer):
    """Serailizers for resending OTP to our users."""

    phone_number = serializers.CharField()
    id = serializers.IntegerField()

    class Meta:
        model = User
        fields = ["id", "phone_number"]


class ResetPasswordSerializer(serializers.ModelSerializer):
    otp = serializers.CharField(max_length=50, min_length=6)
    password = serializers.CharField(max_length=68, min_length=6, write_only=True)
    password2 = serializers.CharField(max_length=68, min_length=6, write_only=True)

    class Meta:
        model = User
        fields = ("otp", "password", "password2")
