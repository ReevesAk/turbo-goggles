# Third party imports.
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field

# In project imports.
from accounts.models import User
from .models import (
    PartnerServices,
    PartnerServicePhotos,
    AvailablePartnerGymTrainers,
)
from banking.models import WalletModel

from security import encrypt


class BecomePartnerSerializer(serializers.ModelSerializer):
    """Serializers for our Partners' first time joining"""

    class Meta:
        model = User
        fields = [
            "id",
            "country",
            "state",
            "city",
            "business_name",
            "website",
            "business_category",
        ]
        extra_kwargs = {
            "password": {"write_only": True},
            "website": {"required": False, "allow_blank": True},
        }

    def validate(self, attrs):
        business_name = attrs.get("business_name", "")
        business_category = attrs.get("business_category", "")

        if business_name:
            email_exists = User.objects.filter(email=business_name).exists()
            if email_exists:
                raise serializers.ValidationError(
                    encrypt("business_name: Business name has already been used")
                )
        else:
            raise serializers.ValidationError(
                encrypt("business_name: business_name field can not be empty")
            )

        if not business_category:
            raise serializers.ValidationError(
                encrypt("business_category: business_category field can not be empty")
            )

        return super().validate(attrs)

    def update(self, validated_data):
        user = User.objects.update(
            country=validated_data["country"],
            state=validated_data["state"],
            city=validated_data["city"],
            business_name=validated_data["business_name"],
            website=validated_data.get("website"),
            business_category=validated_data["business_category"],
        )
        return user


class PartnerServicePhotosSerializer(serializers.ModelSerializer):
    class Meta:
        model = PartnerServicePhotos
        fields = ("photo",)


class PartnerServiceGymPhotosSerializer(serializers.ModelSerializer):
    class Meta:
        model = AvailablePartnerGymTrainers
        fields = ["trainer_name", "trainer_price", "trainer_photo"]


class PartnerServiceSerializer(serializers.ModelSerializer):
    """Serailizers for our Partners' service entry."""

    trainer_name = serializers.CharField(required=False, read_only=True)
    trainer_price = serializers.FloatField(required=False, read_only=True)
    commission_rate = serializers.DecimalField(
        max_digits=5, decimal_places=2, read_only=True
    )
    commission_set = serializers.BooleanField(read_only=True)
    final_price = serializers.FloatField(read_only=True)

    class Meta:
        model = PartnerServices
        fields = [
            "id",
            "business",
            "service",
            "service_star",
            "price",
            "description",
            "trainer_name",
            "trainer_price",
            "from_station",
            "destination",
            "commission_rate",
            "commission_set",
            "final_price",
        ]


class UpdatePartnerServiceSerializer(serializers.ModelSerializer):
    """Serailizers for updating our Partners' service."""

    trainer_name = serializers.CharField(required=False, read_only=True)
    trainer_price = serializers.FloatField(required=False, read_only=True)

    class Meta:
        model = PartnerServices
        fields = [
            "id",
            "service_star",
            "price",
            "description",
            "trainer_name",
            "trainer_price",
            "from_station",
            "destination",
        ]


class PartnerProfileSerializer(serializers.ModelSerializer):
    """Serailizers for our Partners' profile."""

    acc_balance = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "first_name",
            "last_name",
            "profile_img_url",
            "email",
            "country",
            "acc_balance",
            "active_role",
            "has_wallet",
            "state",
            "city",
            "phone_number",
            "business_name",
            "website",
            "business_category",
            "created_at",
            "updated_at",
            "business_verified",
            "has_created_pin",
            "welcome_bonus",
            "has_card",
        ]

    @extend_schema_field(serializers.CharField())
    def get_acc_balance(self, obj):
        wallet = getattr(obj, "walletmodel", None)
        return str(wallet.balance) if wallet else "0.00"


class UpdateProfileSerializer(serializers.ModelSerializer):
    """Serailizers for updating our Partners' profile."""

    class Meta:
        model = User
        fields = [
            "id",
            "state",
            "city",
            "website",
            "business_category",
            "created_at",
            "updated_at",
        ]


class SetCommissionSerializer(serializers.ModelSerializer):
    """Serializer for a PartnersAdmin negotiating and locking in a service's commission."""

    class Meta:
        model = PartnerServices
        fields = ["commission_rate"]
        extra_kwargs = {"commission_rate": {"required": True}}


class VerifyPartnerSerializers(serializers.ModelSerializer):
    """Serializers for our Partners' business verification."""

    bank_code = serializers.CharField(required=False, read_only=True)
    business_name = serializers.CharField(required=False, read_only=True)
    account_number = serializers.CharField(required=False, read_only=True)

    class Meta:
        model = WalletModel
        fields = [
            "business_name",
            "bank_code",
            "account_number",
        ]
