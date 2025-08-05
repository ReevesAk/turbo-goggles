# Third party imports.
from rest_framework import serializers

# In project imports.
from accounts.models import User
from banking.models import AccountCreation

from .models import (
    Applications,
    RestrictPartnerAccount,
    RestrictBrandAdAccount,
    ActivityModel,
)
from accounts.models import USER_CATEGORY_CHOICES, AccountType
from security import encrypt


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
            raise serializers.ValidationError(
                encrypt({"email": "Email field cannot be empty."})
            )
        if User.objects.filter(email=email).exists():
            raise serializers.ValidationError(
                encrypt({"email": "Email has already been used."})
            )

        # Validate that passwords match
        if password != password2:
            raise serializers.ValidationError(
                encrypt({"password": "Passwords do not match."})
            )

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
    """Serializer for other admin roles' initial registration step."""

    roles = serializers.ListField(
        child=serializers.ChoiceField(choices=USER_CATEGORY_CHOICES), write_only=True
    )

    class Meta:
        model = User
        fields = ["id", "roles", "full_name", "email"]
        extra_kwargs = {"email": {"required": True}}

    def validate(self, attrs):
        return super().validate(attrs)

    def create(self, validated_data):
        user_types = validated_data.pop("roles", [])
        user = super().create(validated_data)

        # Assign multiple AccountType entries based on roles
        AccountType.objects.bulk_create(
            [AccountType(user=user, user_type=user_type) for user_type in user_types]
        )

        return user


class AddAdminContdSerializer(serializers.ModelSerializer):
    """Serializer for other admin roles' first-time registration."""

    password2 = serializers.CharField(max_length=68, min_length=6, write_only=True)

    class Meta:
        model = User
        fields = ["phone_number", "password", "password2"]
        extra_kwargs = {"password": {"write_only": True}}

    def validate(self, attrs):
        password = attrs.get("password")
        password2 = attrs.get("password2")

        if password != password2:
            raise serializers.ValidationError(
                encrypt({"password": "Passwords do not match."})
            )

        return attrs

    def create(self, validated_data):
        validated_data.pop("password2")  # Remove password2 from validated data
        user = User(**validated_data)
        user.set_password(validated_data["password"])  # Hash the password
        user.save()
        return user

    def update(self, instance, validated_data):
        validated_data.pop("password2", None)  # Remove password2 if present
        if "password" in validated_data:
            instance.set_password(validated_data["password"])
        return super().update(instance, validated_data)


class CreateAdminPinSerializer(serializers.ModelSerializer):
    """Serailizers for other admin roles first time pin creation."""

    pin = serializers.CharField(min_length=5, write_only=True)

    class Meta:
        model = User
        fields = ["pin"]
        extra_kwargs = {"pin": {"write_only": True}}

    def validate_pin(self, value):
        if not value.isdigit() or len(value) != 5:
            raise serializers.ValidationError(encrypt("Pin must be a 5-digit number."))
        return value


class AdminLoginSerializers(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["email", "password"]


class AdminDeletionSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(required=True)
    pin = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = User
        fields = ["email", "pin"]


class DisableAdminSerializer(serializers.ModelSerializer):
    pin = serializers.CharField(max_length=5, min_length=6, write_only=True)

    class Meta:
        model = User
        fields = ["email", "pin"]


class EnableAdminSerializer(serializers.ModelSerializer):
    pin = serializers.CharField(max_length=5, min_length=6, write_only=True)

    class Meta:
        model = User
        fields = ["email", "pin"]


class AddRoleToAdminSerializer(serializers.ModelSerializer):
    pin = serializers.CharField(max_length=5, min_length=6, write_only=True)
    role = serializers.CharField(max_length=50, write_only=True)

    class Meta:
        model = User
        fields = ["email", "role", "pin"]


class RemoveRoleFromAdminSerializer(serializers.ModelSerializer):
    pin = serializers.CharField(max_length=5, min_length=6, write_only=True)
    role_to_remove = serializers.CharField(max_length=50, write_only=True)

    class Meta:
        model = User
        fields = ["email", "role_to_remove", "pin"]


class ListAdminSerializer(serializers.ModelSerializer):
    user_type = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "full_name", "email", "status", "user_type", "last_login"]

    def get_user_type(self, obj):
        # Fetch user_type values from AccountType model related to the user
        return list(obj.account_types.values_list("user_type", flat=True))

    def get_status(self, obj):
        return "Disabled" if obj.is_admin_disabled else "Active"


class StatusSerializer(serializers.Serializer):
    message = serializers.CharField(max_length=200)


# class GetAllTaskSerializer(serializers.Serializer):
#     message = serializers.CharField(max_length=200)


# class GetSingleTaskSerializer(serializers.Serializer):
#     message = serializers.CharField(max_length=200)


# class GetAllSubittedTasksSerializer(serializers.Serializer):
#     class Meta:
#         model = GamificationModel
#         fields = [
#             "task_url",
#         ]


# class GetSingleSubmittedTaskSerializer(serializers.Serializer):
#     message = serializers.CharField(max_length=200)


# class ReviewTaskSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = GamificationModel
#         fields = ["user_id", "remarks", "pts"]


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
        return list(obj.account_types.values_list("user_type", flat=True))

    def get_status(self, obj):
        return "Disabled" if obj.is_disabled else "Active"

    def get_full_name(self, obj):
        return f"{obj.firstname} {obj.lastname}".strip()


class RestrictPartnersSerializers(serializers.ModelSerializer):
    pin = serializers.CharField(min_length=5, write_only=True)

    class Meta:
        model = RestrictPartnerAccount
        fields = [
            "id",
            "pin",
            "reason",
            "minimum_debit",
            "maximum_debit",
            "post_per_day",
        ]


class RestrictBrandAdSerializers(serializers.ModelSerializer):
    pin = serializers.CharField(min_length=5, write_only=True)

    class Meta:
        model = RestrictBrandAdAccount
        fields = [
            "id",
            "pin",
            "reason",
            "minimum_debit",
            "maximum_debit",
            "post_per_day",
        ]


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
        return list(obj.account_types.values_list("user_type", flat=True))

    def get_status(self, obj):
        return "Disabled" if obj.is_disabled else "Active"

    def get_full_name(self, obj):
        return f"{obj.firstname} {obj.lastname}".strip()


class ListWalletUsersSerializer(serializers.ModelSerializer):
    balance = serializers.DecimalField(max_digits=12, decimal_places=2)
    userTypes = serializers.SerializerMethodField()

    class Meta:
        model = AccountCreation
        fields = [
            "acct_name",
            "balance",
            "userTypes",
            "status",
        ]

    def get_userTypes(self, obj):
        """
        Get the list of user types for a wallet user from the AccountType model.
        """
        return list(obj.account_types.values_list("user_type", flat=True))


class GetAllActivityLogsSerializer(serializers.Serializer):
    date = serializers.CharField(required=False, read_only=True)

    class Meta:
        model = ActivityModel
        fields = [
            "id",
            "title",
            "description",
            "date",
        ]


class AdminBankAccountCreationSerializers(serializers.ModelSerializer):
    """Serailizers for creating a bank account for users."""

    passport = serializers.FileField(required=True)
    identity = serializers.FileField(required=True)
    utility = serializers.FileField(required=True)
    signature = serializers.FileField(required=True)
    tc = serializers.CharField(max_length=4, write_only=True, required=True)
    gn = serializers.CharField(max_length=4, write_only=True, required=True)
    bvn = serializers.CharField(max_length=20, write_only=True, required=True)
    accountType = serializers.CharField(max_length=4, write_only=True, required=True)
    ms = serializers.CharField(max_length=4, write_only=True, required=True)
    country = serializers.CharField(max_length=100, write_only=True, required=True)
    alt_email = serializers.CharField(max_length=100, write_only=True, required=True)
    alt_phone = serializers.CharField(max_length=100, write_only=True, required=True)
    alt_phone = serializers.CharField(max_length=100, write_only=True, required=True)
    date_of_birth = serializers.CharField(
        max_length=100, write_only=True, required=True
    )

    class Meta:
        model = AccountCreation
        fields = [
            "id",
            "lga",
            "state",
            "tc",
            "bvn",
            "gn",
            "accountType",
            "country",
            "ms",
            "alt_email",
            "alt_phone",
            "religion",
            "nin",
            "sex",
            "address",
            "utility",
            "passport",
            "identity",
            "signature",
            "date_of_birth",
        ]
