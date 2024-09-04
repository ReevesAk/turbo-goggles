# Third party imports.
from rest_framework import serializers

# In project imports.
from accounts.models import User

from .models import (
    GamificationModel,
    Applications,
    RestrictPartnerAccount,
    RestrictBrandAdAccount,
)
from accounts.models import USER_CATEGORY_CHOICES, AccountType


class RegisterSuperAdminSerializer(serializers.ModelSerializer):
    """Serializer for super admin first-time registration"""

    password2 = serializers.CharField(max_length=68, min_length=6, write_only=True)
    device_id = serializers.CharField(max_length=68, min_length=6, write_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "device_id",
            "phone_number",
            "email",
            "password",
            "password2",
        ]
        extra_kwargs = {"password": {"write_only": True}}

    def validate(self, attrs):
        email = attrs.get("email", "")
        password = attrs.get("password", "")
        password2 = attrs.get("password2", "")

        # Validate that email is provided and not already in use
        if not email:
            raise serializers.ValidationError({"email": "Email field cannot be empty."})
        if User.objects.filter(email=email).exists():
            raise serializers.ValidationError({"email": "Email has already been used."})

        # Validate that passwords match
        if password != password2:
            raise serializers.ValidationError({"password": "Passwords do not match."})

        return attrs

    def create(self, validated_data):
        # Remove password2 from validated_data as it's not a field in the User model
        validated_data.pop("password2")

        # Create the user with the provided email and phone number
        user = User.objects.create(
            email=validated_data["email"],
            phone_number=validated_data["phone_number"],
        )

        # Set and save the password securely
        user.set_password(validated_data["password"])
        user.save()

        return user


class AddAdminSerializer(serializers.ModelSerializer):
    """Serailizers for other admin roles first time registration."""

    roles = serializers.ListField(
        child=serializers.ChoiceField(choices=USER_CATEGORY_CHOICES), write_only=True
    )

    class Meta:
        model = User
        fields = [
            "id",
            "roles",
            "full_name",
            "email",
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
        user_types = validated_data.pop("roles", [])
        user = super().create(validated_data)

        # Create multiple AccountType entries
        for user_type in user_types:
            AccountType.objects.create(user=user, user_type=user_type)

        return user


class AddAdminContdSerializer(serializers.ModelSerializer):
    """Serailizers for other admin roles first time registration."""

    password2 = serializers.CharField(max_length=68, min_length=6, write_only=True)

    class Meta:
        model = User
        fields = ["phone_number", "password", "password2"]
        extra_kwargs = {"password": {"write_only": True}}

    def validate(self, attrs):
        password = attrs.get("password", "")
        password2 = attrs.get("password2", "")

        if password != password2:
            raise serializers.ValidationError({"password": "Passwords do not match."})

        return attrs

    def update(self, instance, validated_data):
        phone_number = validated_data.get("phone_number", instance.phone_number)
        password = validated_data.get("password", None)

        instance.phone_number = phone_number

        if password:
            instance.set_password(password)

        instance.save()
        return instance


class AdminLoginSerializers(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["email", "password"]


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
    user_type = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "full_name",
            "email",
            "status",
            "user_type",
        ]

    def get_user_type(self, obj):
        # Fetch user_type values from AccountType model related to the user
        return list(obj.accounttype_set.values_list("user_type", flat=True))

    def get_status(self, obj):
        return "Disabled" if obj.is_disabled else "Active"


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


class GetApplicationsSerializers(serializers.ModelSerializer):
    class Meta:
        model = Applications
        fields = [
            "id",
            "name",
            "email",
            "role",
            "cover_letter",
            "portfolio",
            "certificates",
            "cv",
        ]


class SwitchRolesSerializers(serializers.ModelSerializer):
    user_type = serializers.CharField(max_length=68, min_length=6, write_only=True)

    class Meta:
        model = User
        fields = ["user_type"]


class ListPartnerUsersSerializer(serializers.ModelSerializer):
    user_type = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    acc_balance = serializers.CharField(
        required=False, default=2000000.00, read_only=True
    )
    full_name = serializers.CharField(required=False, read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "full_name",
            "email",
            "acc_balance",
            "status",
            "user_type",
            "business_category",
            "business_name",
        ]

    def get_user_type(self, obj):
        # Fetch user_type values from AccountType model related to the user
        return list(obj.accounttype_set.values_list("user_type", flat=True))

    def get_status(self, obj):
        return "Disabled" if obj.is_disabled else "Active"

    def get_full_name(self, obj):
        return f"{obj.firstname} {obj.lastname}".strip()


class RestrictPartnersSerializers(serializers.ModelSerializer):
    class Meta:
        model = RestrictPartnerAccount
        fields = ["id", "reason", "minimum_debit", "maximum_debit", "post_per_day"]


class RestrictBrandAdSerializers(serializers.ModelSerializer):
    class Meta:
        model = RestrictBrandAdAccount
        fields = ["id", "reason", "minimum_debit", "maximum_debit", "post_per_day"]


class ListBrandAdSerializer(serializers.ModelSerializer):
    user_type = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    full_name = serializers.CharField(required=False, read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "full_name",
            "email",
            "user_type",
            "address",
            "status",
            "brand_type",
            "services",
            "state",
            "city",
            "website",
            "facebook",
            "twitter",
            "instagram",
            "telegram",
            "created_at",
            "updated_at",
        ]

    def get_user_type(self, obj):
        # Fetch user_type values from AccountType model related to the user
        return list(obj.accounttype_set.values_list("user_type", flat=True))

    def get_status(self, obj):
        return "Disabled" if obj.is_disabled else "Active"

    def get_full_name(self, obj):
        return f"{obj.firstname} {obj.lastname}".strip()
