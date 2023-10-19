from django.contrib.auth import authenticate

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


class ForgotPasswordSerializer(serializers.ModelSerializer):
    phone_number = serializers.EmailField()
    otp = serializers.CharField(max_length=50, min_length=6)

    class Meta:
        model = User
        fields = ["phone_number", "otp"]

    def validate(self, attrs):
        email = attrs.get("email", "")
        otp = attrs.get("otp", "")

        if email is None:
            return serializers.ValidationError("email: email field can not be empty")

        if otp is None:
            return serializers.ValidationError("otp: otp must be provided")
        return attrs


class ChangePasswordSerializer(serializers.ModelSerializer):
    old_password = serializers.CharField(max_length=68, min_length=6, write_only=True)
    password = serializers.CharField(max_length=68, min_length=6, write_only=True)

    class Meta:
        model = User
        fields = ["old_password", "password"]

    def validate(self, attrs):
        password = attrs.get("password", "")
        password2 = attrs.get("password2", "")

        if password != password2:
            return serializers.ValidationError("password: Passwords do not match")
        return attrs
