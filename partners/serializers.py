# Third party imports.
from rest_framework import serializers

# In project imports.
from accounts.models import User
from .models import (
    PartnerServices,
    PartnerServicePhotos,
    AvailablePartnerGymTrainers,
    VerifyCAC,
)


class BecomePartnerSerializer(serializers.ModelSerializer):
    """Serailizers for our Partners' first time joining"""

    device_id = serializers.CharField(max_length=68, min_length=6, write_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "device_id",
            "country",
            "state",
            "city",
            "business_name",
            "website",
            "business_category",
        ]
        extra_kwargs = {"password": {"write_only": True}}

    def validate(self, attrs):
        business_name = attrs.get("business_name", "")
        business_category = attrs.get("business_category", "")

        if business_name:
            email_exists = User.objects.filter(email=business_name).exists()
            if email_exists:
                raise serializers.ValidationError("business_name: Business name has already been used")
        else:
            raise serializers.ValidationError("business_name: business_name field can not be empty")

        if business_category:
            pass
        else:
            raise serializers.ValidationError(
                "business_category: business_category field can not be empty"
            )

        return super().validate(attrs)

    def update(self, validated_data):
        user = User.objects.update(
            country=validated_data["country"],
            state=validated_data["state"],
            city=validated_data["city"],
            business_name=validated_data["business_name"],
            website=validated_data["website"],
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
        ]


class PartnerProfileSerializer(serializers.ModelSerializer):
    """Serailizers for our Partners' profile."""

    class Meta:
        model = User
        fields = [
            "id",
            "first_name",
            "last_name",
            "email",
            "country",
            "account_type",
            "state",
            "city",
            "phone_number",
            "business_name",
            "website",
            "business_category",
            "created_at",
            "updated_at",
        ]


class UpdateProfileSerializer(serializers.ModelSerializer):
    """Serailizers for updating our Partners' profile."""

    class Meta:
        model = User
        fields = [
            "id",
            "country",
            "state",
            "city",
            "phone_number",
            "business_name",
            "website",
            "business_category",
            "created_at",
            "updated_at",
        ]


class VerifyCacSerializers(serializers.ModelSerializer):
    """Serailizers for our Partners' business verification."""

    class Meta:
        model = VerifyCAC
        fields = [
            "cac",
            "business_name",
        ]
