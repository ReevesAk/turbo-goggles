import logging

# Third party imports.
from rest_framework import serializers

# In project imports.
from accounts.models import User

from banking.models import WalletModel

from adverts.models import CreateAd

from .models import (
    RestrictPartnerAccount,
    RestrictBrandAdAccount,
    ActivityModel,
    SendNewsletters,
    NewsletterRecipient,
)
from accounts.models import USER_CATEGORY_CHOICES, AccountType
from banking.models import WalletUpgrade
from security import encrypt

logger = logging.getLogger(__name__)


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


class ApproveAdSerializers(serializers.ModelSerializer):
    approved = serializers.BooleanField(write_only=True)
    reason = serializers.CharField(max_length=255, write_only=True)

    class Meta:
        model = CreateAd
        fields = ["approved", "reason"]


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
    recentTransactions = serializers.SerializerMethodField()

    bvn = serializers.SerializerMethodField()
    nin = serializers.SerializerMethodField()

    profile_img = serializers.CharField(source="user.profile_img_url", read_only=True)

    class Meta:
        model = WalletModel
        fields = [
            "profile_img",
            "acct_name",
            "transactionTrackingRef",
            "balance",
            "account_number",
            "tier_level",
            "userTypes",
            "email",
            "gender",
            "status",
            "created_at",
            "recentTransactions",
            "bvn",
            "nin",
        ]

    def get_bvn(self, obj):
        return getattr(getattr(obj.user, "kyc", None), "bvn", None)

    def get_nin(self, obj):
        return getattr(getattr(obj.user, "kyc", None), "nin", None)

    def get_userTypes(self, obj):
        return list(obj.user.account_types.values_list("user_type", flat=True))

    def get_recentTransactions(self, obj):
        tx_list = getattr(obj.user, "last_five_tx", [])
        return [
            {
                "description": tx.description,
                "amount": tx.amount,
                "date": tx.date.isoformat(),
                "status": tx.tx_type,
            }
            for tx in tx_list
        ]


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


class ChangeWalletStatusSerializer(serializers.ModelSerializer):
    pin = serializers.CharField(
        max_length=4, min_length=4, required=False, allow_blank=True
    )

    class Meta:
        model = WalletModel
        fields = [
            "account_number",
            "status",
            "pin",
            "created_at",
        ]

    def get_status(self, obj):
        return "STATUS" if obj.status else "SUSPENDED"


class ForgotPinSerializer(serializers.ModelSerializer):
    email = serializers.CharField(max_length=50, write_only=True)

    class Meta:
        model = User
        fields = ["email"]

    def validate(self, attrs):
        email = attrs.get("email")
        logger.info("Forgot admin pin request for email: %s", email)
        return attrs


class ResetPinSerializer(serializers.ModelSerializer):
    pin = serializers.CharField(max_length=68, min_length=5, write_only=True)
    pin2 = serializers.CharField(max_length=68, min_length=5, write_only=True)
    admin_id = serializers.CharField(max_length=68, write_only=True)

    class Meta:
        model = User
        fields = ["admin_id", "pin", "pin2"]

    # def validate(self, attrs):
    #     admin_id = attrs.get("admin_id")
    #     user = User.objects.get(id=admin_id)
    #     logger.info("OTP resend request for phone number: %s", user.phone_number)
    #     return attrs


class EmailOrListField(serializers.Field):
    def to_internal_value(self, data):
        if isinstance(data, str):
            return [data]

        if isinstance(data, list):
            if not all(isinstance(email, str) for email in data):
                raise serializers.ValidationError("All emails must be strings")
            return data

        raise serializers.ValidationError(
            "send_to must be an email string or a list of emails"
        )


class SendNewsletterSerializer(serializers.ModelSerializer):
    send_to = serializers.JSONField(write_only=True)
    pin = serializers.CharField(min_length=5, write_only=True)

    class Meta:
        model = SendNewsletters
        fields = ["volume", "title", "content", "send_to", "pin"]

    def validate_send_to(self, value):
        # Normalize to list
        if isinstance(value, str):
            value = [value]

        if not isinstance(value, list):
            raise serializers.ValidationError(
                "send_to must be an email or a list of emails."
            )

        for email in value:
            serializers.EmailField().run_validation(email)

        return value

    def create(self, validated_data):
        recipients = validated_data.pop("send_to")

        newsletter = SendNewsletters.objects.create(**validated_data)

        NewsletterRecipient.objects.bulk_create(
            [
                NewsletterRecipient(newsletter=newsletter, email=email)
                for email in recipients
            ]
        )

        return newsletter


class AdminDdashboardDataSerializer(serializers.Serializer):
    total_wallet_users = serializers.IntegerField()
    total_partners = serializers.IntegerField()
    total_brand_ads = serializers.IntegerField()
    total_admins = serializers.IntegerField()
    total_active_admins = serializers.IntegerField()
    total_disabled_admins = serializers.IntegerField()
    total_verified_users = serializers.IntegerField()
    total_verified_partners = serializers.IntegerField()
    total_verified_brandAds = serializers.IntegerField()
    total_support_tickets = serializers.IntegerField()
    total_live_tickets = serializers.IntegerField()
    total_closed_tickets = serializers.IntegerField()
    total_logins = serializers.IntegerField()


class WalletKYCSerializer(serializers.ModelSerializer):
    bvn = serializers.CharField(source="user.bvn", read_only=True)
    nin = serializers.CharField(source="user.nin", read_only=True)
    address_verification_status = serializers.CharField(read_only=True)

    class Meta:
        model = WalletModel
        fields = [
            "account_number",
            "acct_name",
            "bvn",
            "nin",
            "address_verification_status",
        ]


class Tier3WalletUpgradeSerializers(serializers.ModelSerializer):
    """Serailizers for upgrading wallet to a tier3."""

    pin = serializers.CharField(min_length=5, write_only=True)
    bvn = serializers.CharField(max_length=12, write_only=True, required=True)
    nin = serializers.CharField(max_length=12, write_only=True, required=True)
    proofOfAddressVerification = serializers.CharField(
        max_length=12, write_only=True, required=True
    )

    class Meta:
        model = WalletUpgrade
        fields = ["id", "pin", "bvn", "nin", "proofOfAddressVerification"]


class MemberSerializer(serializers.ModelSerializer):
    balance = serializers.DecimalField(
        source="walletmodel.balance", max_digits=10, decimal_places=2, read_only=True
    )
    wallet_status = serializers.BooleanField(
        source="walletmodel.status", read_only=True
    )
    name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "name",
            "email",
            "balance",
            "wallet_status",
        ]

    def get_name(self, obj):
        if obj.full_name:
            return obj.full_name
        return f"{obj.first_name or ''} {obj.last_name or ''}".strip()
