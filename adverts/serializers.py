import logging
from itertools import zip_longest
from urllib.parse import urlparse

from django.utils import timezone

from rest_framework import serializers

from .models import CreateAd, AdLocation, AdMedia

logger = logging.getLogger(__name__)


# ── Per-type required fields in task_details ─────────────────────────────────

WATCH_VIDEO_PLATFORMS = ("YouTube", "TikTok", "Instagram", "X", "Vimeo", "Facebook")
WATCH_VIDEO_DURATIONS = ("15s", "30s", "60s", "full")

SOCIAL_ENGAGE_PLATFORMS = ("Facebook", "X", "TikTok", "Instagram", "YouTube")
SOCIAL_ENGAGE_ACTIONS = ("like", "comment", "share", "follow")

_PLATFORM_DOMAINS = {
    "Facebook": ("facebook.com", "fb.com"),
    "X": ("x.com", "twitter.com"),
    "TikTok": ("tiktok.com",),
    "Instagram": ("instagram.com",),
    "YouTube": ("youtube.com", "youtu.be"),
}

WEBSITE_VISIT_MIN_TIMES = (30, 60, 120, 180)


def _validate_watch_video(details: dict):
    errors = {}
    if not details.get("video_url"):
        errors["video_url"] = "A video URL is required for Watch Video tasks."
    if details.get("platform") not in WATCH_VIDEO_PLATFORMS:
        errors["platform"] = (
            f"Platform must be one of: {', '.join(WATCH_VIDEO_PLATFORMS)}."
        )
    if details.get("min_watch_duration") not in WATCH_VIDEO_DURATIONS:
        errors["min_watch_duration"] = (
            f"min_watch_duration must be one of: {', '.join(WATCH_VIDEO_DURATIONS)}."
        )
    return errors


SOCIAL_ENGAGE_TIMINGS = ("15s", "30s", "60s")


def _validate_social_engage(details: dict):
    errors = {}
    if details.get("platform") not in SOCIAL_ENGAGE_PLATFORMS:
        errors["platform"] = (
            f"Platform must be one of: {', '.join(SOCIAL_ENGAGE_PLATFORMS)}."
        )
    post_url = details.get("post_url", "").strip()
    if not post_url:
        errors["post_url"] = (
            "A post or profile URL is required for Social Engage tasks."
        )
    else:
        try:
            parsed = urlparse(post_url)
            netloc = parsed.netloc.lower().removeprefix("www.")
            path = parsed.path.strip("/")
            platform = details.get("platform", "")
            allowed = _PLATFORM_DOMAINS.get(platform, ())
            if allowed and not any(
                netloc == d or netloc.endswith("." + d) for d in allowed
            ):
                errors["post_url"] = (
                    f"The URL must point to a {platform} page or profile."
                )
            elif not path:
                errors["post_url"] = (
                    "Please provide a specific page or profile URL, not just the platform home."
                )
        except Exception:
            errors["post_url"] = "Please provide a valid URL."
    actions = details.get("required_actions", [])
    if not isinstance(actions, list) or len(actions) == 0:
        errors["required_actions"] = "At least one required action must be specified."
    else:
        normalized = [a.lower() for a in actions if isinstance(a, str)]
        invalid = [a for a in normalized if a not in SOCIAL_ENGAGE_ACTIONS]
        if invalid:
            errors["required_actions"] = (
                f"Invalid action(s): {invalid}. Must be from: {list(SOCIAL_ENGAGE_ACTIONS)}."
            )
        else:
            details["required_actions"] = normalized
    timing = details.get("timing")
    if timing and timing not in SOCIAL_ENGAGE_TIMINGS:
        errors["timing"] = f"timing must be one of: {', '.join(SOCIAL_ENGAGE_TIMINGS)}."
    return errors


def _validate_website_visit(details: dict):
    errors = {}
    if not details.get("landing_url"):
        errors["landing_url"] = "A landing URL is required for Website Visit tasks."
    min_time = details.get("min_time_on_page")
    if min_time not in WEBSITE_VISIT_MIN_TIMES:
        errors["min_time_on_page"] = (
            f"min_time_on_page must be one of: {WEBSITE_VISIT_MIN_TIMES} (seconds)."
        )
    return errors


def _validate_store_visit(details: dict):
    errors = {}
    if not details.get("store_name"):
        errors["store_name"] = "Store name is required for Store Visit tasks."
    if not details.get("store_address"):
        errors["store_address"] = "Store address is required for Store Visit tasks."
    return errors


def _validate_survey(details: dict):
    errors = {}
    if not details.get("survey_title"):
        errors["survey_title"] = "A survey title is required."
    questions = details.get("questions", [])
    if not isinstance(questions, list) or len(questions) == 0:
        errors["questions"] = "At least one survey question is required."
    return errors


def _validate_app_download(details: dict):
    errors = {}
    if not details.get("app_name"):
        errors["app_name"] = "App name is required for App Download tasks."
    if not details.get("play_store_url"):
        errors["play_store_url"] = (
            "A Play Store URL is required for App Download tasks."
        )
    return errors


TASK_DETAIL_VALIDATORS = {
    "watch_video": _validate_watch_video,
    "social_engage": _validate_social_engage,
    "website_visit": _validate_website_visit,
    "store_visit": _validate_store_visit,
    "survey": _validate_survey,
    "app_download": _validate_app_download,
}


# ── Serializers ───────────────────────────────────────────────────────────────


class BrandAdProfileSerializers(serializers.ModelSerializer):
    class Meta:
        model = CreateAd
        fields = "__all__"


class UpdateBrandAdProfileSerializers(serializers.ModelSerializer):
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
        required=False,
    )
    videos = serializers.ListField(
        child=serializers.CharField(max_length=150, required=False, allow_blank=True),
        write_only=True,
        required=False,
    )
    website = serializers.CharField(max_length=200, required=False, allow_blank=True)
    brand_socials = serializers.ListField(
        child=serializers.URLField(
            max_length=300,
            error_messages={
                "invalid": "Social links must be valid URLs starting with http:// or https://"
            },
        ),
        required=False,
        max_length=4,
    )
    task_details = serializers.DictField(
        child=serializers.JSONField(),
        required=False,
        default=dict,
    )
    countries = serializers.ListField(
        child=serializers.CharField(max_length=100),
        required=False,
        default=list,
    )

    campaign_name = serializers.CharField(max_length=150)

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
            "brand_socials",
            "campaign_duration",
            "amount",
            "state",
            "city",
            "images",
            "videos",
            "type_of_brand",
            # Task type fields
            "task_type",
            "task_name",
            "task_description",
            "task_details",
            "slot_cap",
            # Targeting
            "location_type",
            "targeting_type",
            "countries",
            "auto_boost",
        ]

    def validate(self, attrs):
        task_type = attrs.get("task_type")
        task_details = attrs.get("task_details", {})

        if task_type:
            validator = TASK_DETAIL_VALIDATORS.get(task_type)
            if validator:
                field_errors = validator(task_details)
                if field_errors:
                    raise serializers.ValidationError({"task_details": field_errors})

        return attrs

    def create(self, validated_data):
        validated_data.pop("pin", None)
        validated_data.pop("payment_option", None)
        validated_data.pop("biometrics", None)

        states = validated_data.pop("state", [])
        cities = validated_data.pop("city", [])
        images = validated_data.pop("images", [])
        videos = validated_data.pop("videos", [])

        # Resolve reward_points from PointConfig — brand cannot set this
        task_type = validated_data.get("task_type")
        if task_type:
            from gamification.models import PointConfig

            TASK_TYPE_TO_KEY = {
                "watch_video": "watch_video",
                "social_engage": "social_engagement",
                "website_visit": "website_visit",
                "store_visit": "store_visit",
                "survey": "survey_completion",
                "app_download": "app_download",
                "brand_task": "brand_task",
            }
            key = TASK_TYPE_TO_KEY.get(task_type)
            if key:
                config = PointConfig.objects.filter(key=key).first()
                if config:
                    validated_data["reward_points"] = config.value

        request = self.context.get("request")
        user = request.user

        create_ad = CreateAd.objects.create(user=user, **validated_data)

        for state, city in zip(states, cities):
            AdLocation.objects.create(brand=create_ad, state=state, city=city)

        for image, video in zip_longest(images, videos):
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
    slots_remaining = serializers.SerializerMethodField()
    task_type_display = serializers.SerializerMethodField()

    def get_ad_media(self, obj):
        media = obj.ad_media.all()
        return [{"images": m.images, "videos": m.videos} for m in media]

    def get_slots_remaining(self, obj):
        if obj.slot_cap:
            return max(0, obj.slot_cap - obj.slots_filled)
        return None

    def get_task_type_display(self, obj):
        return obj.get_task_type_display() if obj.task_type else None

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
            "brand_socials",
            "ad_media",
            "is_active",
            "created_at",
            "updated_at",
            # Task type fields
            "task_type",
            "task_type_display",
            "task_name",
            "task_description",
            "task_details",
            "reward_points",
            "slot_cap",
            "slots_filled",
            "slots_remaining",
            "ads_credit",
            "auto_boost_points",
            # Targeting
            "location_type",
            "targeting_type",
            "countries",
            "auto_boost",
        ]

    def get_remaining_time(self, obj):
        if obj.expiry_date:
            remaining = obj.expiry_date - timezone.now()

            if remaining.total_seconds() > 0:
                days = remaining.days
                hours = remaining.seconds // 3600

                if not obj.is_active:
                    obj.is_active = True
                    obj.save(update_fields=["is_active"])

                return f"{days} days {hours} hours remaining"

            else:
                if obj.is_active:
                    obj.is_active = False
                    obj.save(update_fields=["is_active"])

                return "Expired"
