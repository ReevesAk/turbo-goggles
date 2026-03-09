import logging

from django.utils import timezone

# Third party imports.
from rest_framework import serializers

# In projects imports.
from accounts.models import User
from .models import CreateAd, AdLocation, AdMedia

logger = logging.getLogger(__name__)


class BrandAdProfileSerializers(serializers.ModelSerializer):
    """Serailizers for our BrandAds profile."""

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
        child=serializers.CharField(max_length=150, required=False, allow_blank=True),
        write_only=True,
        required=False,  # Optional field
    )
    videos = serializers.ListField(
        child=serializers.CharField(max_length=150, required=False, allow_blank=True),
        write_only=True,
        required=False,  # Optional field
    )
    website = serializers.CharField(max_length=200, required=False, allow_blank=True)

    pin = serializers.CharField(max_length=6, write_only=True, required=False)
    payment_option = serializers.CharField(
        max_length=20, write_only=True, required=True
    )
    biometrics = serializers.BooleanField(write_only=True, required=False)

    class Meta:
        model = CreateAd
        fields = [
            "id",
            "pin",
            "payment_option",
            "biometrics",
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
            "type_of_brand",
        ]

    def create(self, validated_data):
        validated_data.pop("pin", None)
        validated_data.pop("payment_option", None)
        validated_data.pop("biometrics", None)

        # Extract non-model fields first
        states = validated_data.pop("state", [])
        cities = validated_data.pop("city", [])
        images = validated_data.pop("images", [])
        videos = validated_data.pop("videos", [])

        # Create the main CreateAd instance
        request = self.context.get("request")
        user = request.user

        create_ad = CreateAd.objects.create(user=user, **validated_data)

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
    remaining_time = serializers.SerializerMethodField()
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
            "type_of_brand",
            "campaign_duration",
            "remaining_time",
            "amount",
            "brand_location",
            "ad_media",
            "is_active",
            "created_at",
            "updated_at",
        ]

    def get_remaining_time(self, obj):
        if obj.expiry_date:
            remaining = obj.expiry_date - timezone.now()

            if remaining.total_seconds() > 0:
                days = remaining.days
                hours = remaining.seconds // 3600

                # Ensure ad is active
                if not obj.is_active:
                    obj.is_active = True
                    obj.save(update_fields=["is_active"])

                return f"{days} days {hours} hours remaining"

            else:
                if obj.is_active:
                    obj.is_active = False
                    obj.save(update_fields=["is_active"])

                return "Expired"