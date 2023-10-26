# Third party imports.
from rest_framework import serializers

# In project imports.
from accounts.models import User


class RegisterSuperAdminSerializer(serializers.ModelSerializer):
    """Serailizers for our super admin first time registration"""

    password2 = serializers.CharField(max_length=68, min_length=6, write_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "account_type",
            "phone_number",
            "email",
            "password",
            "password2",
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
            account_type=validated_data["account_type"],
            phone_number=validated_data["phone_number"],
        )

        user.set_password(validated_data["password"])
        user.save()

        return user


class RegisterOtherAdminRoleSerializer(serializers.ModelSerializer):
    """Serailizers for other admin roles first time registration."""

    class Meta:
        model = User
        fields = [
            "id",
            "account_type",
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
            account_type=validated_data["account_type"],
            phone_number=validated_data["phone_number"],
        )

        user.set_password(validated_data["password"])
        user.save()

        return user


class AdminDeletionSerializer(serializers.Serializer):
    class Meta:
        model = User
        fields = ["email"]


class UpdateAdminRoleSerializer(serializers.Serializer):
    class Meta:
        model = User
        fields = ["email", "account_type"]


class ListAdminSerializer(serializers.Serializer):
    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "account_type",
        ]
