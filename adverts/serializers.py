import logging

# Third party imports.
from rest_framework import serializers

# In projects imports.
from accounts.models import User
from .models import CreateAd, AdBudget, AdLocation, AdMedia

logger = logging.getLogger(__name__)


class BrandAdProfileSerializers(serializers.ModelSerializer):
    """Serailizers for our BrandAds profile."""

    is_approved = serializers.BooleanField(read_only=True)

    class Meta:
        model = CreateAd
        fields = "__all__"


class UpdateBrandAdProfileSerializers(serializers.ModelSerializer):
    """Serializers for updating brand adverts profile."""

    class Meta:
        model = CreateAd
        fields = "__all__"


class CreateAdSerializers(serializers.ModelSerializer):
    state = serializers.ListField(
        child=serializers.CharField(max_length=150),
        write_only=True,
        required=False,
    )
    city = serializers.ListField(
        child=serializers.CharField(max_length=150),
        write_only=True,
        required=False,
    )
    images = serializers.ListField(
        child=serializers.CharField(max_length=150),
        write_only=True,
        required=False,  # Optional field
    )
    videos = serializers.ListField(
        child=serializers.CharField(max_length=150),
        write_only=True,
        required=False,  # Optional field
    )
    website = serializers.CharField(max_length=200, required=False, allow_blank=True)
    user = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), write_only=True, required=False
    )

    class Meta:
        model = CreateAd
        fields = [
            "id",
            "user",
            "business_or_brand_name",
            "type_of_business",
            "industry",
            "brand_objective",
            "campaign_name",
            "gender",
            "demography",
            "engagement_type",
            "daily_allocation",
            "website",
            "campaign_duration",
            "amount",
            "state",
            "city",
            "images",
            "videos",
            "type",
            "is_approved",
            "is_rejected",
        ]

    def create(self, validated_data):
        # Extract non-model fields first
        states = validated_data.pop("state", [])
        cities = validated_data.pop("city", [])
        images = validated_data.pop("images", [])
        videos = validated_data.pop("videos", [])

        # Create the main CreateAd instance
        create_ad = CreateAd.objects.create(**validated_data)

        # Create related AdLocation entries
        for state, city in zip(states, cities):
            AdLocation.objects.create(brand=create_ad, state=state, city=city)

        # Create related AdMedia entries
        for image, video in zip(images, videos):
            AdMedia.objects.create(brand=create_ad, images=image, videos=video)

        return create_ad


class AdLocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = AdLocation
        fields = ["state", "city"]


class AdSerializers(serializers.ModelSerializer):
    brand_location = AdLocationSerializer(many=True, read_only=True)
    ad_media = serializers.SerializerMethodField()

    def get_ad_media(self, obj):
        media = obj.ad_media.all()
        return [{"images": m.images, "videos": m.videos} for m in media]

    class Meta:
        model = CreateAd
        fields = [
            "id",
            "user",
            "business_or_brand_name",
            "type_of_business",
            "industry",
            "brand_objective",
            "campaign_name",
            "gender",
            "demography",
            "engagement_type",
            "daily_allocation",
            "website",
            "type",
            "campaign_duration",
            "amount",
            "brand_location",
            "ad_media",
            "is_approved",
            "is_rejected",
        ]


class AdBudgetSerializer(serializers.ModelSerializer):
    class Meta:
        model = AdBudget
        fields = [
            "id",
            "user",
            "payment_option",
            "is_active_ad",
            "is_completed",
            "is_ongoing",
            "has_made_request",
            "category",
            "ad",
            "star",
            "price_range",
        ]
