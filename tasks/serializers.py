import secrets
import string

from django.utils import timezone
from rest_framework import serializers

from .models import (
    BrandTaskSubmission,
    SocialTask,
    TaskSubmission,
    VerificationResult,
    UserTrustScore,
)
from adverts.models import CreateAd
from gamification.models import StreakChallenge, UserStreak


class SocialTaskSerializer(serializers.ModelSerializer):
    is_expired = serializers.BooleanField(read_only=True)
    is_available = serializers.BooleanField(read_only=True)

    class Meta:
        model = SocialTask
        fields = [
            "id", "title", "description", "platform", "task_type",
            "target_url", "target_account", "target_content_hint",
            "required_hashtag", "required_mention", "required_keywords",
            "reward_points", "reward_naira",
            "max_submissions", "total_submissions",
            "is_active", "expires_at", "is_expired", "is_available",
        ]
        read_only_fields = ["id", "total_submissions", "is_expired", "is_available"]


class VerificationResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = VerificationResult
        fields = [
            "verdict", "confidence_score", "ai_reasoning", "flags",
            "username_matched", "target_matched",
            "hashtag_found", "mention_found",
            "action_confirmed", "verification_code_found",
        ]


class TaskSubmissionSerializer(serializers.ModelSerializer):
    verification = VerificationResultSerializer(read_only=True)
    task_title = serializers.CharField(source="task.title", read_only=True)
    task_platform = serializers.CharField(source="task.platform", read_only=True)
    task_type = serializers.CharField(source="task.task_type", read_only=True)

    class Meta:
        model = TaskSubmission
        fields = [
            "id", "task", "task_title", "task_platform", "task_type",
            "screenshot_url", "post_url", "notes",
            "status", "reward_issued",
            "rejection_reason", "reviewed_at",
            "verification_code",
            "verification",
        ]
        read_only_fields = [
            "id", "status", "reward_issued", "rejection_reason",
            "reviewed_at", "verification_code", "verification",
        ]


class SubmitTaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskSubmission
        fields = ["task", "screenshot_url", "post_url", "notes"]

    def validate(self, attrs):
        user = self.context["request"].user
        task = attrs["task"]

        if not task.is_available:
            raise serializers.ValidationError("This task is not currently available.")

        if TaskSubmission.objects.filter(task=task, user=user).exists():
            raise serializers.ValidationError("You have already submitted this task.")

        if not attrs.get("screenshot_url"):
            raise serializers.ValidationError("A screenshot is required.")

        return attrs

    def create(self, validated_data):
        user = self.context["request"].user
        task = validated_data["task"]
        verification_code = None
        if task.task_type in ("Comment", "Post"):
            alphabet = string.ascii_uppercase + string.digits
            code = "".join(secrets.choice(alphabet) for _ in range(8))
            verification_code = f"PD-{code}"
        return TaskSubmission.objects.create(
            user=user, verification_code=verification_code, **validated_data
        )


class UserTrustScoreSerializer(serializers.ModelSerializer):
    approval_rate = serializers.IntegerField(read_only=True)
    can_auto_approve = serializers.BooleanField(read_only=True)

    class Meta:
        model = UserTrustScore
        fields = [
            "score", "total_submissions", "approved_submissions",
            "rejected_submissions", "flagged_submissions",
            "approval_rate", "can_auto_approve",
        ]


class AdminReviewSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["approve", "reject"])
    reason = serializers.CharField(required=False, allow_blank=True, default="")


# ── Brand campaign task serializers ──────────────────────────────────────────

_SOCIAL_TASK_TYPE_TO_ACTION = {
    "Follow": "follow",
    "Like": "like",
    "Comment": "comment",
    "Post": "post",
}

SCREENSHOT_REQUIRED_TASK_TYPES = {"social_engage"}


class SocialTaskFeedSerializer(serializers.ModelSerializer):
    """Read-only task card for admin-created SocialTask items on the unified feed."""

    task = serializers.SerializerMethodField()
    time_remaining = serializers.SerializerMethodField()
    ad_media = serializers.SerializerMethodField()
    campaign_name = serializers.SerializerMethodField()
    business_or_brand_name = serializers.SerializerMethodField()
    expiry_date = serializers.DateTimeField(source="expires_at")
    source = serializers.SerializerMethodField()

    class Meta:
        model = SocialTask
        fields = [
            "id", "source", "campaign_name", "business_or_brand_name",
            "task", "reward_points", "expiry_date", "time_remaining",
            "is_active", "ad_media",
        ]

    def get_source(self, obj):
        return "social"

    def get_campaign_name(self, obj):
        return obj.title

    def get_business_or_brand_name(self, obj):
        return obj.ad.business_or_brand_name if obj.ad_id else None

    def get_task(self, obj):
        action = _SOCIAL_TASK_TYPE_TO_ACTION.get(obj.task_type, obj.task_type.lower())
        return {
            "type": "social_engage",
            "display": "Social Engage",
            "details": {
                "platform": obj.platform,
                "post_url": obj.target_url,
                "target_account": obj.target_account,
                "required_actions": [action],
                "required_hashtag": obj.required_hashtag,
                "required_mention": obj.required_mention,
            },
        }

    def get_ad_media(self, obj):
        if obj.ad_id:
            media = obj.ad.ad_media.all()
            if media:
                return [{"images": m.images, "videos": m.videos} for m in media]
        return []

    def get_time_remaining(self, obj):
        if obj.expires_at:
            remaining = obj.expires_at - timezone.now()
            if remaining.total_seconds() > 0:
                days = remaining.days
                hours = remaining.seconds // 3600
                return f"{days}d {hours}h remaining"
            return "Expired"
        return None


class BrandTaskFeedSerializer(serializers.ModelSerializer):
    """Read-only task card for brand campaign (CreateAd) items on the unified feed."""

    task = serializers.SerializerMethodField()
    time_remaining = serializers.SerializerMethodField()
    ad_media = serializers.SerializerMethodField()
    source = serializers.SerializerMethodField()

    class Meta:
        model = CreateAd
        fields = [
            "id", "source", "campaign_name", "business_or_brand_name",
            "task", "reward_points", "expiry_date", "time_remaining",
            "is_active", "ad_media",
        ]
        read_only_fields = fields

    def get_source(self, obj):
        return "brand"

    def get_task(self, obj):
        return {
            "type": obj.task_type,
            "display": obj.get_task_type_display() if obj.task_type else None,
            "details": obj.task_details,
        }

    def get_ad_media(self, obj):
        media = obj.ad_media.all()
        if media:
            return [{"images": m.images, "videos": m.videos} for m in media]
        details = obj.task_details or {}
        if obj.task_type == "watch_video" and details.get("video_url"):
            return [{"videos": details["video_url"], "images": None}]
        return []

    def get_time_remaining(self, obj):
        if obj.expiry_date:
            remaining = obj.expiry_date - timezone.now()
            if remaining.total_seconds() > 0:
                days = remaining.days
                hours = remaining.seconds // 3600
                return f"{days}d {hours}h remaining"
            return "Expired"
        return None


class InAppTaskFeedSerializer(serializers.ModelSerializer):
    """Unified task card for StreakChallenge in-app tasks on the unified feed."""

    task = serializers.SerializerMethodField()
    time_remaining = serializers.SerializerMethodField()

    class Meta:
        model = StreakChallenge
        fields = ["id", "name", "task", "reward_points", "end_date", "time_remaining", "is_active"]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        return {
            "id": data["id"],
            "source": "inapp",
            "campaign_name": data["name"],
            "business_or_brand_name": None,
            "task": data["task"],
            "reward_points": data["reward_points"],
            "expiry_date": data["end_date"],
            "time_remaining": data["time_remaining"],
            "is_active": data["is_active"],
            "ad_media": [],
        }

    def get_task(self, obj):
        return {
            "type": obj.streak_type,
            "display": obj.get_streak_type_display(),
            "details": {
                "description": obj.description,
                "duration_days": obj.duration_days,
                "participant_cap": obj.participant_cap,
                "schedule_type": obj.schedule_type,
            },
        }

    def get_time_remaining(self, obj):
        today = timezone.now().date()
        if obj.end_date:
            remaining_days = (obj.end_date - today).days
            if remaining_days > 0:
                return f"{remaining_days}d remaining"
            return "Expired"
        return None


SCREENSHOT_TASK_TYPES = ("social_engage", "app_download")



class BrandTaskSubmissionSerializer(serializers.ModelSerializer):
    campaign_name = serializers.CharField(source="ad.campaign_name", read_only=True)
    brand_name = serializers.CharField(source="ad.business_or_brand_name", read_only=True)
    task_type = serializers.CharField(source="ad.task_type", read_only=True)
    task_type_display = serializers.SerializerMethodField()
    reward_points = serializers.IntegerField(source="ad.reward_points", read_only=True)

    class Meta:
        model = BrandTaskSubmission
        fields = [
            "id",
            "ad",
            "campaign_name",
            "brand_name",
            "task_type",
            "task_type_display",
            "reward_points",
            "screenshot_url",
            "notes",
            "status",
            "reward_issued",
            "rejection_reason",
            "reviewed_at",
            "created_at",
        ]
        read_only_fields = [
            "id", "status", "reward_issued", "rejection_reason",
            "reviewed_at", "created_at",
        ]

    def get_task_type_display(self, obj):
        return obj.ad.get_task_type_display() if obj.ad.task_type else None


class AdminBrandReviewSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["approve", "reject"])
    reason = serializers.CharField(required=False, allow_blank=True, default="")


class CompleteWebviewTaskSerializer(serializers.Serializer):
    task_id = serializers.CharField()
    is_done = serializers.BooleanField()
    source = serializers.ChoiceField(choices=["brand", "inapp"], default="brand")

    BRAND_WEBVIEW_TYPES = ("website_visit", "watch_video", "store_visit", "survey")
    INAPP_WEBVIEW_TYPES = ("website_visit", "watch_video", "store_visit", "survey_completion")

    def validate(self, attrs):
        task_id = attrs["task_id"]
        source = attrs.get("source", "brand")
        user = self.context["request"].user

        if attrs["is_done"] is not True:
            raise serializers.ValidationError("is_done must be true.")

        if source == "brand":
            try:
                ad = CreateAd.objects.get(pk=int(task_id))
            except (CreateAd.DoesNotExist, ValueError, TypeError):
                raise serializers.ValidationError("Task not found.")

            if not ad.is_active:
                raise serializers.ValidationError("This campaign is no longer active.")

            if ad.task_type not in self.BRAND_WEBVIEW_TYPES:
                raise serializers.ValidationError(
                    "This endpoint is only for website visit, video watch, store visit, and survey tasks."
                )

            if BrandTaskSubmission.objects.filter(ad=ad, user=user).exists():
                raise serializers.ValidationError("You have already completed this task.")

            attrs["ad"] = ad

        else:  # inapp
            try:
                challenge = StreakChallenge.objects.get(pk=task_id)
            except StreakChallenge.DoesNotExist:
                raise serializers.ValidationError("Task not found.")

            if not challenge.is_active or challenge.is_cancelled:
                raise serializers.ValidationError("This challenge is no longer active.")

            if challenge.streak_type not in self.INAPP_WEBVIEW_TYPES:
                raise serializers.ValidationError(
                    "This endpoint is only for website visit, video watch, store visit, and survey challenges."
                )

            streak = UserStreak.objects.filter(user=user, challenge=challenge).first()
            if streak and streak.completed:
                raise serializers.ValidationError("You have already completed this challenge.")

            attrs["challenge"] = challenge

        return attrs
