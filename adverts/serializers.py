import logging

# Third party imports.
from rest_framework import serializers

# In projects imports.
from accounts.models import User
from .models import CreateAd, AdBudget, AdLocation


logger = logging.getLogger(__name__)


class OnboardBrandSerializer(serializers.ModelSerializer):
    """Serializers for onboarding a brand"""

    online_presence = serializers.CharField(
        max_length=200, write_only=True, required=False
    )

    class Meta:
        model = User
        fields = [
            "active_role",
            "whoareyou",
            "name",
            "address",
            "brand_email",
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
            "online_presence",
        ]

    def validate(self, attrs):
        return super().validate(attrs)


class CreateBrandAdvertSeriailizers(serializers.ModelSerializer):
    """Serializers for craeating brand adverts"""

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
            "brand_phone_number",
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


class CreateAdSerializers(serializers.ModelSerializer):
    state = serializers.ListField(
        child=serializers.CharField(max_length=150), 
        write_only=True,
        required=False  # Add if these fields can be optional
    )
    city = serializers.ListField(
        child=serializers.CharField(max_length=150), 
        write_only=True,
        required=False  # Add if these fields can be optional
    )
    website = serializers.CharField(max_length=200, required=False, allow_blank=True)
    user = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        write_only=True,
        required=False
    )

    class Meta:
        model = CreateAd
        fields = [
            "id",
            "user",
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

    def create(self, validated_data):
        # Extract non-model fields first
        states = validated_data.pop('state', [])
        cities = validated_data.pop('city', [])

        # Create the main CreateAd instance
        create_ad = CreateAd.objects.create(**validated_data)

        # Create related AdLocation entries
        for state, city in zip(states, cities):
            AdLocation.objects.create(
                brand=create_ad,
                state=state,
                city=city
            )

        return create_ad


class AdBudgetSerializer(serializers.ModelSerializer):
    """Serializers for Advert budget."""

    pin = serializers.CharField(max_length=4, write_only=True, required=True)
    payment_option = serializers.CharField(max_length=50, write_only=True)
    use_biometrics = serializers.BooleanField(write_only=True, required=False)

    class Meta:
        model = AdBudget
        fields = [
            "id",
            "ad_type",
            "ad",
            "star",
            "price_range",
            "pin",
            "payment_option",
            "use_biometrics",
        ]

    def create(self, validated_data):
        validated_data.pop("pin", None)
        validated_data.pop("use_biometrics", None)
        return super().create(validated_data)
