import secrets
import string
import uuid

from django.utils import timezone
from rest_framework import serializers

from .models import (
    BrandTaskSubmission,
    SocialTask,
    TaskSubmission,
    VerificationResult,
    UserTrustScore,
)
from adverts.models import CreateAd, StoreVisitQRCode
from gamification.models import StreakChallenge, UserStreak, UserGeneratedContent
from commons import is_slot_target_reached


class SocialTaskSerializer(serializers.ModelSerializer):
    is_expired = serializers.BooleanField(read_only=True)
    is_available = serializers.BooleanField(read_only=True)

    class Meta:
        model = SocialTask
        fields = [
            "id",
            "title",
            "description",
            "platform",
            "task_type",
            "target_url",
            "target_account",
            "target_content_hint",
            "required_hashtag",
            "required_mention",
            "required_keywords",
            "reward_points",
            "reward_naira",
            "max_submissions",
            "total_submissions",
            "is_active",
            "expires_at",
            "is_expired",
            "is_available",
        ]
        read_only_fields = ["id", "total_submissions", "is_expired", "is_available"]


class VerificationResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = VerificationResult
        fields = [
            "verdict",
            "confidence_score",
            "ai_reasoning",
            "flags",
            "username_matched",
            "target_matched",
            "hashtag_found",
            "mention_found",
            "action_confirmed",
            "verification_code_found",
        ]


class TaskSubmissionSerializer(serializers.ModelSerializer):
    verification = VerificationResultSerializer(read_only=True)
    task_title = serializers.CharField(source="task.title", read_only=True)
    task_platform = serializers.CharField(source="task.platform", read_only=True)
    task_type = serializers.CharField(source="task.task_type", read_only=True)

    class Meta:
        model = TaskSubmission
        fields = [
            "id",
            "task",
            "task_title",
            "task_platform",
            "task_type",
            "screenshot_url",
            "post_url",
            "notes",
            "status",
            "reward_issued",
            "rejection_reason",
            "reviewed_at",
            "verification_code",
            "verification",
        ]
        read_only_fields = [
            "id",
            "status",
            "reward_issued",
            "rejection_reason",
            "reviewed_at",
            "verification_code",
            "verification",
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

        if (
            TaskSubmission.objects.filter(task=task, user=user)
            .exclude(status="Rejected")
            .exists()
        ):
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
        submission, _ = TaskSubmission.objects.update_or_create(
            user=user,
            task=task,
            defaults={
                "screenshot_url": validated_data.get("screenshot_url"),
                "post_url": validated_data.get("post_url"),
                "notes": validated_data.get("notes"),
                "verification_code": verification_code,
                "status": "Pending",
                "reward_issued": False,
                "rejection_reason": None,
                "reviewed_by": None,
                "reviewed_at": None,
            },
        )
        return submission


class UserTrustScoreSerializer(serializers.ModelSerializer):
    approval_rate = serializers.IntegerField(read_only=True)
    can_auto_approve = serializers.BooleanField(read_only=True)

    class Meta:
        model = UserTrustScore
        fields = [
            "score",
            "total_submissions",
            "approved_submissions",
            "rejected_submissions",
            "flagged_submissions",
            "approval_rate",
            "can_auto_approve",
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
            "id",
            "source",
            "campaign_name",
            "business_or_brand_name",
            "task",
            "reward_points",
            "expiry_date",
            "time_remaining",
            "is_active",
            "ad_media",
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
    user_status = serializers.SerializerMethodField()

    class Meta:
        model = CreateAd
        fields = [
            "id",
            "source",
            "campaign_name",
            "business_or_brand_name",
            "task",
            "reward_points",
            "expiry_date",
            "time_remaining",
            "is_active",
            "ad_media",
            "user_status",
        ]
        read_only_fields = fields

    def get_source(self, obj) -> str:
        return "brand"

    def get_task(self, obj) -> dict:
        return {
            "type": obj.task_type,
            "display": obj.get_task_type_display() if obj.task_type else None,
            "details": obj.task_details,
        }

    def get_user_status(self, obj) -> str | None:
        user = self.context["request"].user
        submission = (
            BrandTaskSubmission.objects.filter(ad=obj, user=user)
            .order_by("-created_at")
            .first()
        )
        return submission.status if submission else None

    def get_ad_media(self, obj) -> list:
        media = obj.ad_media.all()
        if media:
            return [{"images": m.images, "videos": m.videos} for m in media]
        details = obj.task_details or {}
        if obj.task_type == "watch_video" and details.get("video_url"):
            return [{"videos": details["video_url"], "images": None}]
        return []

    def get_time_remaining(self, obj) -> str | None:
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
    end_date = serializers.DateTimeField()

    class Meta:
        model = StreakChallenge
        fields = [
            "id",
            "name",
            "task",
            "reward_points",
            "end_date",
            "time_remaining",
            "is_active",
        ]

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
                "mission_category": obj.mission_category,
                "vas_category": obj.vas_category,
                "action_type": obj.action_type,
                "required_count": obj.required_count,
                "min_amount_per_action": obj.min_amount_per_action,
                "total_min_amount": obj.total_min_amount,
                "monthly_cap_points": obj.monthly_cap_points,
                "is_recurring": obj.is_recurring,
                "recurrence_period": obj.recurrence_period,
                "kyc_target_tier": obj.kyc_target_tier,
                "progress": self._get_progress(obj),
            },
        }

    def _get_progress(self, obj):
        """Stubbed against the generic UserStreak tracking that already
        exists for every streak type - not yet backed by real per-category
        transaction sums (see plan doc). Same wire shape either way, so
        wiring in real tracking later is a backend swap, not a contract
        change."""
        if obj.streak_type != "financial_task" or not obj.action_type:
            return None
        user = getattr(self.context.get("request"), "user", None)
        user_streak = (
            UserStreak.objects.filter(user=user, challenge=obj).first()
            if user and user.is_authenticated
            else None
        )
        completed = user_streak.completed if user_streak else False
        current_count = user_streak.current_count if user_streak else 0

        if obj.action_type == "amount_based":
            return {
                "completed_count": 1 if completed else 0,
                "total_required": 1,
                "amount_spent": (
                    float(obj.total_min_amount)
                    if completed and obj.total_min_amount is not None
                    else 0
                ),
                "amount_required": (
                    float(obj.total_min_amount)
                    if obj.total_min_amount is not None
                    else None
                ),
                "is_completed": completed,
            }

        total_required = obj.required_count if obj.action_type == "count_based" else 1
        return {
            "completed_count": current_count,
            "total_required": total_required,
            "is_completed": completed,
        }

    def get_time_remaining(self, obj):
        if obj.end_date:
            remaining = obj.end_date - timezone.now()
            if remaining.total_seconds() > 0:
                days = remaining.days
                hours = remaining.seconds // 3600
                minutes = (remaining.seconds % 3600) // 60
                if days > 0:
                    return f"{days}d {hours}h remaining"
                elif hours > 0:
                    return f"{hours}h {minutes}m remaining"
                return f"{minutes}m remaining"
            return "Expired"
        return None


class UGCFeedSerializer(serializers.ModelSerializer):
    """Read-only task card for UGC (UserGeneratedContent) items on the unified feed.

    No user_status field - UGC has no submission/completion-tracking model,
    so there's nothing to report per-viewer here yet.
    """

    task = serializers.SerializerMethodField()
    time_remaining = serializers.SerializerMethodField()
    task_duration = serializers.SerializerMethodField()
    ad_media = serializers.SerializerMethodField()

    class Meta:
        model = UserGeneratedContent
        fields = [
            "id",
            "task_name",
            "business_or_brand_name",
            "unique_identifiers",
            "task",
            "reward_points",
            "task_duration",
            "expiry_date",
            "time_remaining",
            "is_active",
            "ad_media",
        ]
        read_only_fields = fields

    def to_representation(self, instance):
        data = super().to_representation(instance)
        return {
            "id": data["id"],
            "source": "ugc",
            "campaign_name": data["task_name"],
            "business_or_brand_name": data["business_or_brand_name"],
            "unique_identifiers": data["unique_identifiers"],
            "task": data["task"],
            "reward_points": data["reward_points"],
            "task_duration": data["task_duration"],
            "expiry_date": data["expiry_date"],
            "time_remaining": data["time_remaining"],
            "is_active": data["is_active"],
            "ad_media": data["ad_media"],
        }

    def get_task(self, obj) -> dict:
        return {
            "type": obj.task_type,
            "display": obj.get_task_type_display() if obj.task_type else None,
            "details": {
                "description": obj.description,
                "brand_slogan": obj.brand_slogan if obj.use_brand_slogan else None,
            },
        }

    def get_ad_media(self, obj) -> list:
        return [{"images": obj.thumbnail_url, "videos": obj.sample_url}]

    def get_time_remaining(self, obj) -> str | None:
        if obj.expiry_date:
            remaining = obj.expiry_date - timezone.now()
            if remaining.total_seconds() > 0:
                days = remaining.days
                hours = remaining.seconds // 3600
                return f"{days}d {hours}h remaining"
            return "Expired"
        return None

    def get_task_duration(self, obj):
        if obj.task_duration:
            total_seconds = obj.task_duration.total_seconds()
            hours = int(total_seconds // 3600)
            minutes = int((total_seconds % 3600) // 60)
            if hours > 0 and minutes > 0:
                return f"{hours}h {minutes}m"
            elif hours > 0:
                return f"{hours}h"
            elif minutes > 0:
                return f"{minutes}m"
        return None


SCREENSHOT_TASK_TYPES = ("social_engage", "app_download")


class BrandTaskSubmissionSerializer(serializers.ModelSerializer):
    campaign_name = serializers.CharField(source="ad.campaign_name", read_only=True)
    brand_name = serializers.CharField(
        source="ad.business_or_brand_name", read_only=True
    )
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
            "id",
            "status",
            "reward_issued",
            "rejection_reason",
            "reviewed_at",
            "created_at",
        ]

    def get_task_type_display(self, obj) -> str | None:
        return obj.ad.get_task_type_display() if obj.ad.task_type else None


class AdminBrandReviewSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["approve", "reject"])
    reason = serializers.CharField(required=False, allow_blank=True, default="")


class CompleteWebviewTaskSerializer(serializers.Serializer):
    task_id = serializers.CharField()
    is_done = serializers.BooleanField()
    source = serializers.ChoiceField(choices=["brand", "inapp"], default="brand")

    BRAND_WEBVIEW_TYPES = ("website_visit", "watch_video", "store_visit", "survey")
    INAPP_WEBVIEW_TYPES = (
        "website_visit",
        "watch_video",
        "store_visit",
        "survey_completion",
    )

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

            if (
                BrandTaskSubmission.objects.filter(ad=ad, user=user)
                .exclude(status="Rejected")
                .exists()
            ):
                raise serializers.ValidationError(
                    "You have already completed this task."
                )

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
                raise serializers.ValidationError(
                    "You have already completed this challenge."
                )

            attrs["challenge"] = challenge

        return attrs


class ScanStoreVisitQRSerializer(serializers.Serializer):
    """Accepts either a QR token (UUID from scan) or the visit code the store owner shows the user."""

    token = serializers.CharField(required=False, max_length=64)
    code = serializers.CharField(required=False, max_length=20, allow_blank=True)

    def to_internal_value(self, data):
        data = dict(data)
        if not data.get("token"):
            data.pop("token", None)
        if not data.get("code"):
            data.pop("code", None)
        return super().to_internal_value(data)

    def validate(self, attrs):
        token = attrs.get("token")
        code = attrs.get("code")

        if not token and not code:
            raise serializers.ValidationError(
                "Provide either a QR token or a visit code."
            )

        # Clients send both scanned QR tokens (UUIDs) and manually-typed visit
        # codes (e.g. "PIC-A3X9K2") under the same "token" field, so detect
        # which one we got rather than trusting the field name.
        if token:
            try:
                uuid.UUID(token)
            except ValueError:
                code, token = token, None

        try:
            if token:
                qr = StoreVisitQRCode.objects.select_related("ad").get(token=token)
            else:
                qr = StoreVisitQRCode.objects.select_related("ad").get(
                    visit_code=code.strip().upper()
                )
        except StoreVisitQRCode.DoesNotExist:
            raise serializers.ValidationError("Invalid QR code or visit code.")

        ad = qr.ad
        user = self.context["request"].user

        if not ad.is_active:
            raise serializers.ValidationError("This campaign is no longer active.")

        if ad.expiry_date and ad.expiry_date < timezone.now():
            raise serializers.ValidationError("This campaign has expired.")

        if is_slot_target_reached(ad.slot_cap, ad.slots_filled):
            raise serializers.ValidationError("This campaign's slots are full.")

        if (
            BrandTaskSubmission.objects.filter(ad=ad, user=user)
            .exclude(status="Rejected")
            .exists()
        ):
            raise serializers.ValidationError(
                "You have already completed this store visit."
            )

        attrs["_qr"] = qr
        return attrs

    @property
    def qr(self):
        return self.validated_data["_qr"]


# ── Store visit arrival flow serializers ─────────────────────────────────────


class StoreVisitArriveSerializer(serializers.Serializer):
    """Identify the campaign by ad ID or visit code."""

    task_id = serializers.IntegerField(required=False)
    code = serializers.CharField(required=False, max_length=20, allow_blank=True)

    def to_internal_value(self, data):
        data = dict(data)
        if not data.get("task_id"):
            data.pop("task_id", None)
        if not data.get("code"):
            data.pop("code", None)
        return super().to_internal_value(data)

    def validate(self, attrs):
        from .models import StoreVisitArrival

        task_id = attrs.get("task_id")
        code = attrs.get("code")

        if not task_id and not code:
            raise serializers.ValidationError("Provide either task_id or a visit code.")

        if task_id:
            try:
                ad = CreateAd.objects.get(pk=task_id)
            except CreateAd.DoesNotExist:
                raise serializers.ValidationError("Task not found.")
            if ad.task_type != "store_visit":
                raise serializers.ValidationError(
                    "This task is not a store-visit campaign."
                )
        else:
            try:
                qr = StoreVisitQRCode.objects.select_related("ad").get(
                    visit_code=code.strip().upper()
                )
            except StoreVisitQRCode.DoesNotExist:
                raise serializers.ValidationError("Invalid visit code.")
            ad = qr.ad

        user = self.context["request"].user

        if not ad.is_active:
            raise serializers.ValidationError("This campaign is no longer active.")

        if ad.expiry_date and ad.expiry_date < timezone.now():
            raise serializers.ValidationError("This campaign has expired.")

        if is_slot_target_reached(ad.slot_cap, ad.slots_filled):
            raise serializers.ValidationError("This campaign's slots are full.")

        if (
            BrandTaskSubmission.objects.filter(ad=ad, user=user)
            .exclude(status="Rejected")
            .exists()
        ):
            raise serializers.ValidationError(
                "You have already completed this store visit."
            )

        existing = StoreVisitArrival.objects.filter(ad=ad, user=user).first()
        if existing and existing.status == "completed":
            raise serializers.ValidationError(
                "You have already completed this store visit."
            )

        attrs["_ad"] = ad
        attrs["_existing_arrival"] = existing
        return attrs

    @property
    def ad(self):
        return self.validated_data["_ad"]

    @property
    def existing_arrival(self):
        return self.validated_data["_existing_arrival"]


class StoreVisitArrivalIdSerializer(serializers.Serializer):
    """Base serializer for endpoints that operate on an existing arrival."""

    arrival_id = serializers.UUIDField()

    def validate_arrival_id(self, value):
        from .models import StoreVisitArrival

        user = self.context["request"].user
        try:
            arrival = StoreVisitArrival.objects.select_related("ad").get(
                id=value, user=user
            )
        except StoreVisitArrival.DoesNotExist:
            raise serializers.ValidationError("Arrival record not found.")
        self._arrival = arrival
        return value

    @property
    def arrival(self):
        return self._arrival
