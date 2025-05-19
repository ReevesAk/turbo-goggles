import logging

# Third party imports.
from rest_framework import serializers

# In projects imports.
from accounts.models import User
from .models import CreateAd, AdBudget


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
        return super().validate(attrs)


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
            # website = attrs.get("website")

            # # Ensure the website URL starts with http:// or https://
            # if website and not website.startswith(("http://", "https://")):
            #     logger.error("Invalid website URL format: %s", website)
            #     raise serializers.ValidationError(
            #         {
            #             "website": "Invalid website format. Please include 'http://' or 'https://'."
            #         }
            #     )

            # logger.info("Validation successful for BrandSurveySerializers.")
            return attrs


class AdBudgetSerializer(serializers.ModelSerializer):
    """Serializers for Advert budget."""

    pin = serializers.CharField(max_length=4, write_only=True, required=True)

    class Meta:
        model = AdBudget
        fields = ["id", "ad_type", "ad", "star", "price_range", "pin"]
