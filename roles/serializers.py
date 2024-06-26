# Third party imports.
from rest_framework import serializers

# In project imports.
from accounts.models import User

from .models import GamificationModel, Applications


class RegisterSuperAdminSerializer(serializers.ModelSerializer):
    """Serailizers for our super admin first time registration"""

    password2 = serializers.CharField(max_length=68, min_length=6, write_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "active_role",
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
            active_role=validated_data["active_role"],
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
            "active_role",
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
            active_role=validated_data["active_role"],
            phone_number=validated_data["phone_number"],
        )

        user.set_password(validated_data["password"])
        user.save()

        return user


class AdminDeletionSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["email"]


class DisableAdminSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["email", "password"]


class UpdateAdminRoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["email", "active_role"]


class ListAdminSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "active_role",
        ]


class StatusSerializer(serializers.Serializer):
    message = serializers.CharField(max_length=200)


class AssignTaskSerializers(serializers.ModelSerializer):
    user_id = serializers.CharField(max_length=68, min_length=6, write_only=True)

    class Meta:
        model = GamificationModel
        fields = ["user_id", "title", "task_id", "description", "assigned_to"]


class UpdateTaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = GamificationModel
        fields = ["user_id", "title", "task_id", "description", "assigned_to"]


class GetAllTaskSerializer(serializers.Serializer):
    message = serializers.CharField(max_length=200)


class GetSingleTaskSerializer(serializers.Serializer):
    message = serializers.CharField(max_length=200)


class GetAllSubittedTasksSerializer(serializers.Serializer):
    class Meta:
        model = GamificationModel
        fields = [
            "task_url",
        ]


class GetSingleSubmittedTaskSerializer(serializers.Serializer):
    message = serializers.CharField(max_length=200)


class ReviewTaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = GamificationModel
        fields = ["user_id", "remarks", "pts"]


class ApplicationsSerializers(serializers.ModelSerializer):
    cover_letter = serializers.FileField(max_length=155)
    certificates = serializers.FileField(max_length=155)
    cv = serializers.FileField(max_length=155)

    class Meta:
        model = Applications
        fields = [
            "name",
            "email",
            "role",
            "cover_letter",
            "portfolio",
            "certificates",
            "cv",
        ]
