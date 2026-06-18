import secrets
import string

from rest_framework import serializers

from .models import (
    BrandTaskSubmission,
    SocialTask,
    TaskSubmission,
    VerificationResult,
    UserTrustScore,
)
from adverts.models import CreateAd


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

class BrandTaskFeedSerializer(serializers.ModelSerializer):
    """Read-only task card shown to users on the gamification feed."""

    task_type_display = serializers.SerializerMethodField()
    time_remaining = serializers.SerializerMethodField()
    ad_media = serializers.SerializerMethodField()

    class Meta:
        model = CreateAd
        fields = [
            "id",
            "campaign_name",
            "business_or_brand_name",
            "task_type",
            "task_type_display",
            "task_details",
            "reward_points",
            "expiry_date",
            "time_remaining",
            "is_active",
            "ad_media",
        ]
        read_only_fields = fields

    def get_ad_media(self, obj):
        return [
            {"images": m.images, "videos": m.videos}
            for m in obj.ad_media.all()
        ]

    def get_task_type_display(self, obj):
        return obj.get_task_type_display() if obj.task_type else None

    def get_time_remaining(self, obj):
        from django.utils import timezone
        if obj.expiry_date:
            remaining = obj.expiry_date - timezone.now()
            if remaining.total_seconds() > 0:
                days = remaining.days
                hours = remaining.seconds // 3600
                return f"{days}d {hours}h remaining"
            return "Expired"
        return None


class SubmitBrandTaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = BrandTaskSubmission
        fields = ["ad", "screenshot_url", "notes"]

    def validate(self, attrs):
        user = self.context["request"].user
        ad = attrs["ad"]

        if not ad.is_active:
            raise serializers.ValidationError("This campaign is not currently active.")

        if BrandTaskSubmission.objects.filter(ad=ad, user=user).exists():
            raise serializers.ValidationError("You have already submitted this task.")

        # Screenshot required for social_engage and app_download
        if ad.task_type in ("social_engage", "app_download") and not attrs.get("screenshot_url"):
            raise serializers.ValidationError(
                "A screenshot is required as proof for this task type."
            )

        return attrs

    def create(self, validated_data):
        user = self.context["request"].user
        return BrandTaskSubmission.objects.create(user=user, **validated_data)


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
    task_id = serializers.IntegerField()
    is_done = serializers.BooleanField()

    def validate(self, attrs):
        task_id = attrs["task_id"]

        if attrs["is_done"] is not True:
            raise serializers.ValidationError("is_done must be true.")

        try:
            ad = CreateAd.objects.get(pk=task_id)
        except CreateAd.DoesNotExist:
            raise serializers.ValidationError("Task not found.")

        if not ad.is_active:
            raise serializers.ValidationError("This campaign is no longer active.")

        webview_types = ("website_visit", "watch_video")
        if ad.task_type not in webview_types:
            raise serializers.ValidationError("This endpoint is only for website visit and video watch tasks.")

        user = self.context["request"].user
        if BrandTaskSubmission.objects.filter(ad=ad, user=user).exists():
            raise serializers.ValidationError("You have already completed this task.")

        attrs["ad"] = ad
        return attrs
