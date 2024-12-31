import logging
from urllib.parse import urlparse

from django.core.validators import URLValidator
from django.core.exceptions import ValidationError as DjangoValidationError

# Third party imports.
from rest_framework import serializers

# In projects imports.
from accounts.models import User
from .models import CreateAd, AdBudget

from security import encrypt


logger = logging.getLogger(__name__)


class CreateBrandAdvertSeriailizers(serializers.ModelSerializer):
    """Serializers for registering brand adverts"""

    class Meta:
        model = User
        fields = [
            "id",
            "whoareyou",
            "facebook",
            "twitter",
            "instagram",
            "telegram",
        ]

    def validate(self, attrs):
        logger.info("Starting validation for CreateBrandAdvertSeriailizers.")
        urls = ["facebook", "twitter", "instagram", "telegram"]
        url_validator = URLValidator()

        for field_name in urls:
            url = attrs.get(field_name, "")

            if url:
                # Check if the URL has a scheme; if not, prepend 'https://'
                parsed_url = urlparse(url)
                if not parsed_url.scheme:
                    url = f"https://{url}"

                try:
                    url_validator(url)
                    logger.debug(f"{field_name} URL validated: {url}")
                except DjangoValidationError:
                    logger.error(f"Invalid URL format for {field_name}: {url}")
                    raise serializers.ValidationError(
                        {field_name: "Invalid URL format"}
                    )

                # Update the field with the corrected URL
                attrs[field_name] = url

        logger.info("Validation completed successfully.")
        return super().validate(attrs)

    def create(self, validated_data):
        logger.info("Creating a new User with brand advert details.")

        try:
            user = User.objects.create(
                whoareyou=validated_data["whoareyou"],
                facebook=validated_data["facebook"],
                twitter=validated_data["twitter"],
                instagram=validated_data["instagram"],
                telegram=validated_data["telegram"],
            )
            logger.info(f"User created successfully: {user.id}")
        except Exception as e:
            logger.error(f"Error creating user: {e}")
            raise serializers.ValidationError(
                "An error occurred while creating the user."
            )

        return user

    def to_representation(self, instance):
        """Override to_representation to encrypt the response"""
        logger.info("Encrypting the serialized response.")
        data = super().to_representation(instance)
        return encrypt(data)  # Encrypt the serialized data


class BrandAdProfileSerializers(serializers.ModelSerializer):
    """Serailizers for our BrandAds profile."""

    class Meta:
        model = User
        fields = [
            "id",
            "active_role",
            "whoareyou",
            "name",
            "address",
            "email",
            "brand_type",
            "phone_number",
            "country",
            "brand_name",
            "description",
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


class UpdateBrandAdProfileSerializers(serializers.ModelSerializer):
    """Serializers for updating brand adverts profile."""

    class Meta:
        model = User
        fields = [
            "id",
            "address",
            "brand_type",
            "country",
            "brand_name",
            "description",
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


class BrandSurveySerializers(serializers.ModelSerializer):
    """Serializers for creating brand adverts survey."""

    state = serializers.CharField(max_length=150, write_only=True)
    city = serializers.CharField(max_length=150, write_only=True)

    class Meta:
        model = CreateAd
        fields = [
            "id",
            "brand_type",
            "product_type",
            "online_presence",
            "online_preferences",
            "metric_to_increase",
            "demography",
            "website",
            "state",
            "city",
            "type",
            "category",
            "address",
            "description",
            "duration",
        ]

        def validate(self, attrs):
            logger.info("Validating website format for BrandSurveySerializers.")
            website = attrs.get("website")

            # Ensure the website URL starts with http:// or https://
            if website and not website.startswith(("http://", "https://")):
                logger.error("Invalid website URL format: %s", website)
                raise serializers.ValidationError(
                    {
                        "website": "Invalid website format. Please include 'http://' or 'https://'."
                    }
                )

            logger.info("Validation successful for BrandSurveySerializers.")
            return attrs


class AdBudgetSerializer(serializers.ModelSerializer):
    """Serializers for Advert budget."""

    pin = serializers.CharField(max_length=4, write_only=True, required=True)

    class Meta:
        model = AdBudget
        fields = ["id", "ad_type", "ad", "star", "price_range", "pin"]
