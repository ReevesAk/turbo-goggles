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


class RegisterPartnerSerializer(serializers.ModelSerializer):
    """Serailizers for our Partners' first time registration"""

    password2 = serializers.CharField(max_length=68, min_length=6, write_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "device_id",
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
            "password2",
        ]
        extra_kwargs = {"password": {"write_only": True}}

    def validate(self, attrs):
        email = attrs.get("email", "")
        phone_number = attrs.get("phone_number", "")

        if email:
            email_exists = User.objects.filter(email=email).exists()
            if email_exists:
                raise serializers.ValidationError("Email has already been used")
        else:
            raise serializers.ValidationError("email: email field can not be empty")

        if phone_number:
            phone_number_exists = User.objects.filter(
                phone_number=phone_number
            ).exists()
            if phone_number_exists:
                raise serializers.ValidationError("phone_number has already been used")
        else:
            raise serializers.ValidationError(
                "phone_number: phone_number field can not be empty"
            )

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
