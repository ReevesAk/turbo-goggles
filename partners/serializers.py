# Third party imports.
from rest_framework import serializers
from rest_framework.validators import ValidationError

# In project imports.
from accounts.models import User
from .models import (
    PartnerServices,
    ServiceAndCharge,
    PartnerServiceImageUploads,
)


class RegisterPartnerSerializer(serializers.ModelSerializer):
    """Serailizers for our Partners' first time registration"""

    class Meta:
        model = User
        fields = [
            "id",
            "first_name",
            "last_name",
            "country",
            "account_type",
            "state",
            "city",
            "phone_number",
            "business_name",
            "website",
            "business_category",
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
            business_name=validated_data["business_name"],
            website=validated_data["website"],
            business_category=validated_data["business_category"],
        )

        user.set_password(validated_data["password"])
        user.save()

        return user


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


class PartnerServiceSerializers(serializers.ModelSerializer):
    """Serailizers for our Partners' services."""

    class Meta:
        model = PartnerServices
        fields = ["id", "service_offered", "service_category"]

    def create(self, validated_data):
        partner = PartnerServices.objects.create_user(**validated_data)
        return partner


class ServiceAndChargeSerializers(serializers.ModelSerializer):
    """Serailizers for our Partners' service types and prices."""

    class Meta:
        model = ServiceAndCharge
        fields = ["price", "service"]

    def create(self, validated_data):
        partner_service = ServiceAndCharge.objects.create_user(**validated_data)
        return partner_service


class PartnerServiceUploadsSerializers(serializers.ModelSerializer):
    """Serailizers for our Partners' service uploads."""

    class Meta:
        model = PartnerServiceImageUploads
        fields = ["image_url", "image", "timestamp"]

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation.pop("image")

        return representation
