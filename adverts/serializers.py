from django.core.validators import URLValidator
from django.core.exceptions import ValidationError as DjangoValidationError

# Third party imports.
from rest_framework import serializers

# In projects imports.
from accounts.models import User
from .models import CreateAd, AdBudget


class CreateBrandAdvertSeriailizers(serializers.ModelSerializer):
    """Serializers for registering brand adverts"""

    # device_id = serializers.CharField(max_length=68, min_length=6, write_only=True)

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
        # whoareyou = attrs.get("whoareyou", "")

        # if whoareyou:
        #     whoareyou_exists = User.objects.filter(whoareyou=whoareyou).exists()
        #     if whoareyou_exists:
        #         raise serializers.ValidationError(
        #             f"whoareyou: {whoareyou} has already been used"
        #         )
        # else:
        #     raise serializers.ValidationError(
        #         "whoareyou: whoareyou field can not be empty"
        #     )

        urls = ["facebook", "twitter", "instagram", "telegram"]
        url_validator = URLValidator()

        for field_name in urls:
            url = attrs.get(field_name, "")

            if url:
                try:
                    url_validator(url)
                except DjangoValidationError:
                    raise serializers.ValidationError(
                        f"{field_name}: Invalid URL format"
                    )

        return super().validate(attrs)

    def create(self, validated_data):
        user = User.objects.update(
            whoareyou=validated_data["whoareyou"],
            facebook=validated_data["facebook"],
            twitter=validated_data["twitter"],
            instagram=validated_data["instagram"],
            telegram=validated_data["telegram"],
        )

        return user


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
            website = attrs.get("website")

            if website and not website.startswith(("http://", "https://")):
                raise serializers.ValidationError(
                    "Invalid website format. Please include 'http://' or 'https://'."
                )

            return attrs


class AdBudgetSerializer(serializers.ModelSerializer):
    """Serializers for Advert budget."""

    pin = serializers.CharField(max_length=4, write_only=True, required=True)

    class Meta:
        model = AdBudget
        fields = ["id", "ad_type", "ad", "star", "price_range", "pin"]
