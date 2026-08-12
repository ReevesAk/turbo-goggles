import logging
from decimal import Decimal, InvalidOperation
from django.core.validators import URLValidator
from django.core.exceptions import ValidationError

# Third party imports.
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field

# In project imports.
from accounts.models import User
from .models import (
    PointConfig,
    StepCampaignModel,
    StepSessionModel,
    StreakChallenge,
    StreakHistory,
    UserStreak,
    RewardRule,
    RewardTier,
    ReferralTask,
    UserGeneratedContent,
    UGCTaskSubmission,
    UGCTaskProgress,
    UGCLeaderboard,
    SCHEDULE_TYPE_CHOICES,
)

logger = logging.getLogger(__name__)


class SSOLoginSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)

    class Meta:
        model = User
        fields = [
            "email",
        ]


class RedeemPointsToWalletSerializer(serializers.Serializer):
    pin = serializers.CharField(max_length=4, write_only=True, required=False)
    use_biometrics = serializers.BooleanField(required=False, default=False)

    def validate(self, data):
        if not data.get("use_biometrics") and not data.get("pin"):
            raise serializers.ValidationError(
                "Either pin or use_biometrics is required."
            )
        return data


class SocialEngagementSerializer(serializers.Serializer):
    platform = serializers.ChoiceField(
        choices=["facebook", "instagram", "twitter", "tiktok"],
        required=True,
        help_text="Social platform to log activity for.",
    )
    image_url = serializers.URLField(
        required=True,
        help_text="Cloudinary URL of the uploaded post image.",
    )


class StepCampaignSerializer(serializers.ModelSerializer):
    total_steps = serializers.IntegerField(read_only=True)
    is_campaign_active = serializers.BooleanField(read_only=True)
    status = serializers.CharField(read_only=True)
    time_remaining = serializers.DurationField(read_only=True)
    completed = serializers.BooleanField(read_only=True)

    class Meta:
        model = StepCampaignModel
        fields = [
            "id",
            "campaign_id",
            "name",
            "duration",
            "step_target",
            "reward_points",
            "created_by",
            "created_at",
            "description",
            "completed",
            "time_limit",
            "total_steps",
            "is_campaign_active",
            "status",
            "time_remaining",
            "target_gender",
            "target_age_bracket",
        ]
        read_only_fields = ["created_by", "created_at"]


def _user_campaign_status(campaign, request):
    """
    "completed" if the requesting user has finished their own step target
    on this campaign, else the campaign's own active/expired state.
    """
    if request and request.user.is_authenticated:
        session = StepSessionModel.objects.filter(
            user=request.user, campaign=campaign
        ).first()
        if session and session.completed:
            return "completed"
    return campaign.status


class StepCampaignListSerializer(serializers.ModelSerializer):
    status = serializers.SerializerMethodField()

    class Meta:
        model = StepCampaignModel
        fields = [
            "id",
            "campaign_id",
            "name",
            "description",
            "duration",
            "step_target",
            "reward_points",
            "created_at",
            "status",
        ]

    def get_status(self, obj):
        return _user_campaign_status(obj, self.context.get("request"))


class StepCampaignDetailSerializer(serializers.ModelSerializer):
    participants = serializers.SerializerMethodField()
    duration = serializers.SerializerMethodField()
    created_at = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()

    class Meta:
        model = StepCampaignModel
        fields = [
            "id",
            "name",
            "description",
            "duration",
            "step_target",
            "reward_points",
            "created_at",
            "status",
            "participants",
        ]

    def get_status(self, obj):
        return _user_campaign_status(obj, self.context.get("request"))

    def get_duration(self, obj):
        if obj.duration:
            return str(obj.duration)  # Convert timedelta to string
        return None

    def get_created_at(self, obj):
        if obj.created_at:
            return obj.created_at.isoformat()  # Convert datetime to ISO string
        return None

    def get_participants(self, obj):
        # Get sessions with user info
        sessions = StepSessionModel.objects.filter(campaign=obj).select_related("user")

        participants = []
        for session in sessions:
            participants.append(
                {
                    "user_id": session.user.id,
                    "full_name": session.user.full_name,
                    "step_count": session.step_count,
                    "completed": session.completed,
                    "started_at": str(session.started_at),
                }
            )

        return participants


class CampaignWithParticipantsSerializer(serializers.ModelSerializer):
    participant_count = serializers.SerializerMethodField()
    status = serializers.CharField(read_only=True)

    class Meta:
        model = StepCampaignModel
        fields = [
            "campaign_id",
            "name",
            "description",
            "step_target",
            "reward_points",
            "duration",
            "created_at",
            "status",
            "participant_count",
        ]

    @extend_schema_field(serializers.IntegerField())
    def get_participant_count(self, obj):
        return len({session.user_id for session in obj.sessions.all()})


# Main output serializer - enhanced version of your original
class StepCountSessionSerializer(serializers.ModelSerializer):
    """Enhanced serializer for step session responses"""

    campaign_name = serializers.CharField(source="campaign.name", read_only=True)
    step_target = serializers.IntegerField(
        source="campaign.step_target", read_only=True
    )
    reward_points = serializers.IntegerField(
        source="campaign.reward_points", read_only=True
    )
    campaign_end_time = serializers.DateTimeField(
        source="campaign.campaign_end_time", read_only=True
    )
    time_limit = serializers.DurationField(source="campaign.time_limit", read_only=True)

    class Meta:
        model = StepSessionModel
        fields = [
            "session_id",
            "campaign",
            "campaign_name",
            "session_date",
            "step_count",
            "completed",
            "step_target",
            "reward_points",
            "started_at",
            "last_updated",
            "campaign_end_time",
            "time_limit",
        ]
        read_only_fields = ["session_id", "completed", "started_at", "last_updated"]


class PointConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = PointConfig
        fields = ["id", "key", "label", "value", "updated_at"]
        read_only_fields = ["id", "key", "label", "updated_at"]


class PointConfigUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = PointConfig
        fields = ["value"]


class StreakChallengeSerializer(serializers.ModelSerializer):
    is_ongoing = serializers.BooleanField(read_only=True)
    participant_count = serializers.SerializerMethodField()
    participant_names = serializers.SerializerMethodField()
    completed_tasks = serializers.SerializerMethodField()
    total_points_earned = serializers.SerializerMethodField()
    start_date = serializers.DateTimeField()
    end_date = serializers.DateTimeField()

    class Meta:
        model = StreakChallenge
        fields = [
            "id",
            "name",
            "description",
            "streak_type",
            "duration_days",
            "start_date",
            "end_date",
            "reward_points",
            "reminder_time",
            "is_active",
            "is_paused",
            "is_ongoing",
            "participant_count",
            "participant_names",
            "completed_tasks",
            "total_points_earned",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    @extend_schema_field(serializers.IntegerField())
    def get_participant_count(self, obj):
        return obj.user_streaks.count()

    @extend_schema_field(serializers.ListField(child=serializers.DictField()))
    def get_participant_names(self, obj):
        return [
            {
                "id": str(us.user.id),
                "name": us.user.full_name
                or f"{us.user.first_name or ''} {us.user.last_name or ''}".strip(),
                "joined_at": us.joined_at,
                "current_count": us.current_count,
                "completed": us.completed,
                "reward_issued": us.reward_issued,
            }
            for us in obj.user_streaks.select_related("user").all()
        ]

    @extend_schema_field(serializers.IntegerField())
    def get_completed_tasks(self, obj):
        return obj.user_streaks.filter(completed=True).count()

    @extend_schema_field(serializers.IntegerField())
    def get_total_points_earned(self, obj):
        completed = obj.user_streaks.filter(completed=True).count()
        return completed * obj.reward_points


class StreakChallengeCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = StreakChallenge
        fields = [
            "name",
            "description",
            "streak_type",
            "duration_days",
            "start_date",
            "end_date",
            "reward_points",
            "reminder_time",
        ]

    def validate(self, data):
        if data.get("start_date") and data.get("end_date"):
            if data["end_date"] <= data["start_date"]:
                raise serializers.ValidationError("end_date must be after start_date.")
            total_days = max(1, (data["end_date"] - data["start_date"]).days)
            if data.get("duration_days", 0) > total_days:
                raise serializers.ValidationError(
                    "duration_days cannot exceed the duration of the challenge."
                )
        return data


class StreakChallengeUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = StreakChallenge
        fields = [
            "name",
            "description",
            "end_date",
            "reward_points",
            "reminder_time",
            "is_active",
            "is_paused",
        ]


class UserStreakSerializer(serializers.ModelSerializer):
    challenge_name = serializers.CharField(source="challenge.name", read_only=True)
    challenge_type = serializers.CharField(
        source="challenge.streak_type", read_only=True
    )
    duration_days = serializers.IntegerField(
        source="challenge.duration_days", read_only=True
    )
    reward_points = serializers.IntegerField(
        source="challenge.reward_points", read_only=True
    )
    days_remaining = serializers.SerializerMethodField()

    class Meta:
        model = UserStreak
        fields = [
            "id",
            "challenge",
            "challenge_name",
            "challenge_type",
            "duration_days",
            "reward_points",
            "current_count",
            "longest_count",
            "last_activity_date",
            "completed",
            "completed_at",
            "reward_issued",
            "days_remaining",
            "joined_at",
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.IntegerField())
    def get_days_remaining(self, obj):
        return max(obj.challenge.duration_days - obj.current_count, 0)


class StreakHistorySerializer(serializers.ModelSerializer):
    challenge_name = serializers.CharField(source="challenge.name", read_only=True)

    class Meta:
        model = StreakHistory
        fields = [
            "id",
            "challenge",
            "challenge_name",
            "streak_count_reached",
            "broken_at",
            "completed",
            "reward_issued",
            "recorded_at",
        ]
        read_only_fields = fields


class StreakLeaderboardEntrySerializer(serializers.Serializer):
    rank = serializers.IntegerField()
    user_id = serializers.UUIDField()
    full_name = serializers.CharField()
    current_count = serializers.IntegerField()
    longest_count = serializers.IntegerField()
    completed = serializers.BooleanField()


class InAppTaskCreateSerializer(serializers.ModelSerializer):
    """Used by admin to create an in-app task (backed by StreakChallenge)."""

    schedule_type = serializers.ChoiceField(
        choices=SCHEDULE_TYPE_CHOICES, required=False, allow_null=True
    )

    class Meta:
        model = StreakChallenge
        fields = [
            "name",
            "description",
            "streak_type",
            "duration_days",
            "duration_minutes",
            "start_date",
            "end_date",
            "reward_points",
            "reminder_time",
            "participant_cap",
            "schedule_type",
            "scheduled_start_time",
            "target_min_tier",
            "target_state",
            "mission_category",
            "vas_category",
            "action_type",
            "required_count",
            "min_amount_per_action",
            "total_min_amount",
            "monthly_cap_points",
            "is_recurring",
            "recurrence_period",
            "kyc_target_tier",
        ]

    FINANCIAL_TASK_FIELDS = (
        "mission_category",
        "vas_category",
        "action_type",
        "required_count",
        "min_amount_per_action",
        "total_min_amount",
        "monthly_cap_points",
        "is_recurring",
        "recurrence_period",
        "kyc_target_tier",
    )

    def validate(self, data):
        start = data.get("start_date")
        end = data.get("end_date")
        if start and end:
            if end <= start:
                raise serializers.ValidationError("end_date must be after start_date.")
            window_minutes = int((end - start).total_seconds() // 60)
            task_minutes = data.get("duration_days", 0) * 1440 + data.get(
                "duration_minutes", 0
            )
            if task_minutes > window_minutes:
                raise serializers.ValidationError(
                    "Total duration (days + minutes) cannot exceed the challenge window."
                )
        if data.get("schedule_type") and not data.get("scheduled_start_time"):
            raise serializers.ValidationError(
                "scheduled_start_time is required when schedule_type is set."
            )
        self._validate_financial_task_fields(data)
        return data

    def _validate_financial_task_fields(self, data):
        if data.get("streak_type") != "financial_task":
            if any(data.get(field) for field in self.FINANCIAL_TASK_FIELDS):
                raise serializers.ValidationError(
                    "mission_category/vas_category/action_type and related fields "
                    "only apply to streak_type='financial_task'."
                )
            return

        if not data.get("mission_category"):
            raise serializers.ValidationError(
                "mission_category is required for streak_type='financial_task'."
            )
        if not data.get("action_type"):
            raise serializers.ValidationError(
                "action_type is required for streak_type='financial_task'."
            )
        if data["action_type"] == "count_based" and not data.get("required_count"):
            raise serializers.ValidationError(
                "required_count is required when action_type='count_based'."
            )
        if data["action_type"] == "amount_based" and not data.get("total_min_amount"):
            raise serializers.ValidationError(
                "total_min_amount is required when action_type='amount_based'."
            )
        if data["mission_category"] in ("vas", "bills_payment") and not data.get(
            "vas_category"
        ):
            raise serializers.ValidationError(
                "vas_category is required when mission_category is 'vas' or 'bills_payment'."
            )
        if data["mission_category"] == "kyc_upgrade" and not data.get(
            "kyc_target_tier"
        ):
            raise serializers.ValidationError(
                "kyc_target_tier is required when mission_category='kyc_upgrade'."
            )
        if data.get("is_recurring") and not data.get("recurrence_period"):
            raise serializers.ValidationError(
                "recurrence_period is required when is_recurring is true."
            )


class InAppTaskSerializer(serializers.ModelSerializer):
    """Full read serializer for an in-app task — maps fields for the frontend."""

    task_status = serializers.CharField(read_only=True)
    is_scheduled = serializers.BooleanField(read_only=True)
    duration_display = serializers.CharField(read_only=True)
    participant_count = serializers.SerializerMethodField()
    participant_names = serializers.SerializerMethodField()
    completed_tasks = serializers.SerializerMethodField()
    total_points_earned = serializers.SerializerMethodField()
    days_remaining = serializers.SerializerMethodField()

    class Meta:
        model = StreakChallenge
        fields = [
            "id",
            "name",
            "description",
            "streak_type",
            "duration_days",
            "duration_minutes",
            "duration_display",
            "start_date",
            "end_date",
            "reward_points",
            "reminder_time",
            "participant_cap",
            "participant_count",
            "participant_names",
            "completed_tasks",
            "total_points_earned",
            "days_remaining",
            "schedule_type",
            "scheduled_start_time",
            "target_min_tier",
            "target_state",
            "mission_category",
            "vas_category",
            "action_type",
            "required_count",
            "min_amount_per_action",
            "total_min_amount",
            "monthly_cap_points",
            "is_recurring",
            "recurrence_period",
            "kyc_target_tier",
            "is_active",
            "is_paused",
            "is_cancelled",
            "is_scheduled",
            "task_status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "task_status",
            "is_scheduled",
            "duration_display",
            "participant_count",
            "participant_names",
            "completed_tasks",
            "total_points_earned",
            "days_remaining",
            "created_at",
            "updated_at",
        ]

    @extend_schema_field(serializers.IntegerField())
    def get_participant_count(self, obj):
        return obj.user_streaks.count()

    @extend_schema_field(serializers.ListField(child=serializers.DictField()))
    def get_participant_names(self, obj):
        return [
            {
                "id": str(us.user.id),
                "name": us.user.full_name
                or f"{us.user.first_name or ''} {us.user.last_name or ''}".strip(),
                "joined_at": us.joined_at,
                "current_count": us.current_count,
                "completed": us.completed,
                "reward_issued": us.reward_issued,
            }
            for us in obj.user_streaks.select_related("user").all()
        ]

    @extend_schema_field(serializers.IntegerField())
    def get_completed_tasks(self, obj):
        return obj.user_streaks.filter(completed=True).count()

    @extend_schema_field(serializers.IntegerField())
    def get_total_points_earned(self, obj):
        completed = obj.user_streaks.filter(completed=True).count()
        return completed * obj.reward_points

    @extend_schema_field(serializers.IntegerField())
    def get_days_remaining(self, obj):
        from django.utils import timezone

        remaining = obj.end_date - timezone.now()
        return max(0, remaining.days)


class InAppTaskUpdateSerializer(serializers.ModelSerializer):
    """Admin PATCH — allows editing, pausing, or cancelling a task."""

    class Meta:
        model = StreakChallenge
        fields = [
            "name",
            "description",
            "end_date",
            "reward_points",
            "reminder_time",
            "participant_cap",
            "target_min_tier",
            "target_state",
            "mission_category",
            "vas_category",
            "action_type",
            "required_count",
            "min_amount_per_action",
            "total_min_amount",
            "monthly_cap_points",
            "is_recurring",
            "recurrence_period",
            "kyc_target_tier",
            "is_active",
            "is_paused",
            "is_cancelled",
        ]

    def validate(self, data):
        if self.instance.streak_type != "financial_task":
            if any(
                data.get(field)
                for field in InAppTaskCreateSerializer.FINANCIAL_TASK_FIELDS
            ):
                raise serializers.ValidationError(
                    "mission_category/vas_category/action_type and related fields "
                    "only apply to streak_type='financial_task'."
                )
        return data


class ReferralTaskCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReferralTask
        fields = [
            "name",
            "description",
            "mode",
            "target_referral_count",
            "reward_points",
            "target_min_tier",
            "target_state",
        ]

    def validate(self, data):
        if data.get("target_referral_count", 0) < 1:
            raise serializers.ValidationError(
                "target_referral_count must be at least 1."
            )

        mode = data.get("mode")
        if mode == "gamification" and not data.get("reward_points"):
            raise serializers.ValidationError(
                "reward_points is required for gamification mode tasks."
            )
        if mode == "walk_to_earn_gate" and data.get("reward_points"):
            raise serializers.ValidationError(
                "reward_points is not used for walk_to_earn_gate mode tasks — leave it unset."
            )

        return data


class ReferralTaskSerializer(serializers.ModelSerializer):
    """Full read serializer for admin task management."""

    participant_count = serializers.SerializerMethodField()
    completed_count = serializers.SerializerMethodField()
    total_points_distributed = serializers.SerializerMethodField()

    class Meta:
        model = ReferralTask
        fields = [
            "id",
            "name",
            "description",
            "mode",
            "target_referral_count",
            "reward_points",
            "target_min_tier",
            "target_state",
            "is_active",
            "is_paused",
            "is_cancelled",
            "task_status",
            "participant_count",
            "completed_count",
            "total_points_distributed",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "task_status",
            "participant_count",
            "completed_count",
            "total_points_distributed",
            "created_at",
            "updated_at",
        ]

    @extend_schema_field(serializers.IntegerField())
    def get_participant_count(self, obj):
        if obj.mode != "gamification":
            return 0
        return obj.user_progress.count()

    @extend_schema_field(serializers.IntegerField())
    def get_completed_count(self, obj):
        if obj.mode != "gamification":
            return 0
        return obj.user_progress.filter(completed=True).count()

    @extend_schema_field(serializers.IntegerField())
    def get_total_points_distributed(self, obj):
        if obj.mode != "gamification":
            return 0
        completed = obj.user_progress.filter(reward_issued=True).count()
        return completed * obj.reward_points


class ReferralTaskUpdateSerializer(serializers.ModelSerializer):
    """Admin PATCH — allows editing, pausing, or cancelling a task. `mode` is
    intentionally not patchable; cancel and recreate instead."""

    class Meta:
        model = ReferralTask
        fields = [
            "name",
            "description",
            "target_referral_count",
            "reward_points",
            "target_min_tier",
            "target_state",
            "is_active",
            "is_paused",
            "is_cancelled",
        ]


class ReferralTaskProgressEntrySerializer(serializers.Serializer):
    """Member-facing progress entry for a single active gamification-mode task."""

    task_id = serializers.UUIDField()
    name = serializers.CharField()
    description = serializers.CharField()
    target_referral_count = serializers.IntegerField()
    reward_points = serializers.IntegerField()
    completed = serializers.BooleanField()
    reward_issued = serializers.BooleanField()


class RewardTierSerializer(serializers.ModelSerializer):
    class Meta:
        model = RewardTier
        fields = ["id", "label", "min_value", "max_value", "points"]
        read_only_fields = ["id"]


class RewardRuleSerializer(serializers.ModelSerializer):
    """Full read serializer — includes the value-banded tiers for this rule."""

    tiers = RewardTierSerializer(many=True, read_only=True)
    source_display = serializers.CharField(source="get_source_display", read_only=True)

    class Meta:
        model = RewardRule
        fields = [
            "id",
            "source",
            "source_display",
            "label",
            "description",
            "is_active",
            "one_time_only",
            "monthly_cap_points",
            "monthly_cap_count",
            "target_min_tier",
            "target_state",
            "tiers",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "source_display", "tiers", "created_at", "updated_at"]


class RewardRuleCreateSerializer(serializers.ModelSerializer):
    """Used by admin to create a new PicaPoints reward rule (tiers added separately)."""

    class Meta:
        model = RewardRule
        fields = [
            "source",
            "label",
            "description",
            "is_active",
            "one_time_only",
            "monthly_cap_points",
            "monthly_cap_count",
            "target_min_tier",
            "target_state",
        ]

    def validate_source(self, value):
        if RewardRule.objects.filter(source=value).exists():
            raise serializers.ValidationError(
                f"A reward rule for source '{value}' already exists."
            )
        return value


class RewardRuleUpdateSerializer(serializers.ModelSerializer):
    """Admin PATCH — edit or activate/deactivate a reward rule."""

    class Meta:
        model = RewardRule
        fields = [
            "label",
            "description",
            "is_active",
            "one_time_only",
            "monthly_cap_points",
            "monthly_cap_count",
            "target_min_tier",
            "target_state",
        ]


class RewardTierCreateSerializer(serializers.ModelSerializer):
    """Used by admin to add a value band to an existing reward rule."""

    class Meta:
        model = RewardTier
        fields = ["label", "min_value", "max_value", "points"]

    def validate(self, data):
        max_value = data.get("max_value")
        if max_value is not None and max_value < data["min_value"]:
            raise serializers.ValidationError(
                "max_value cannot be less than min_value."
            )
        return data


class RewardTierUpdateSerializer(serializers.ModelSerializer):
    """Admin PATCH — edit a single value band."""

    class Meta:
        model = RewardTier
        fields = ["label", "min_value", "max_value", "points"]

    def validate(self, data):
        min_value = data.get("min_value", getattr(self.instance, "min_value", None))
        max_value = data.get("max_value", getattr(self.instance, "max_value", None))
        if max_value is not None and min_value is not None and max_value < min_value:
            raise serializers.ValidationError(
                "max_value cannot be less than min_value."
            )
        return data


# ==========================================
# Public / User-facing Serializers
# ==========================================


class UserGeneratedContentDetailSerializer(serializers.ModelSerializer):
    """
    Serializer for the public single-task endpoint.

    Includes full task details, financial information, and computed properties
    that are safe to expose to end users.
    """

    available_slots = serializers.SerializerMethodField()
    is_fully_booked = serializers.SerializerMethodField()
    unused_credit = serializers.SerializerMethodField()
    cost_per_engagement = serializers.SerializerMethodField()
    task_type_display = serializers.SerializerMethodField()
    gender_display = serializers.SerializerMethodField()
    demography_display = serializers.SerializerMethodField()

    class Meta:
        model = UserGeneratedContent
        fields = [
            "id",
            "business_or_brand_name",
            "type_of_business",
            "task_name",
            "task_type",
            "task_type_display",
            "description",
            "unique_identifiers",
            "use_brand_slogan",
            "brand_slogan",
            "thumbnail_url",
            "sample_url",
            "slot_cap",
            "slots_filled",
            "available_slots",
            "is_fully_booked",
            "unlimited_slots",
            "reward_points",
            "auto_boost",
            "auto_boost_points",
            "unused_credit",
            "cost_per_engagement",
            "gender",
            "gender_display",
            "demography",
            "demography_display",
            "location_perimeter",
            "countries",
            "states",
            "cities",
            "task_duration",
            "campaign_duration",
            "created_at",
            "updated_at",
            "is_active",
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.IntegerField(allow_null=True))
    def get_available_slots(self, obj):
        """Get the number of available slots for the task."""
        return obj.available_slots

    @extend_schema_field(serializers.BooleanField())
    def get_is_fully_booked(self, obj):
        """Check if the task is fully booked."""
        return obj.is_fully_booked

    @extend_schema_field(serializers.CharField())
    def get_unused_credit(self, obj):
        """Get unused credit as a string representation."""
        return str(obj.unused_credit)

    @extend_schema_field(serializers.CharField())
    def get_cost_per_engagement(self, obj):
        """Get cost per engagement as a string representation."""
        return str(obj.cost_per_engagement)

    @extend_schema_field(serializers.CharField())
    def get_task_type_display(self, obj):
        """Get the display name for the task type."""
        return dict(UserGeneratedContent.TaskType.choices).get(
            obj.task_type, obj.task_type
        )

    @extend_schema_field(serializers.CharField())
    def get_gender_display(self, obj):
        """Get the display name for gender."""
        return obj.get_gender_display() if obj.gender else None

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_demography_display(self, obj):
        """Get the display name for demography."""
        return obj.get_demography_display() if obj.demography else None


# ==========================================
# Brand-facing Serializer
# ==========================================


class BrandUserGeneratedContentSerializer(serializers.ModelSerializer):
    """
    Serializer for brand users to create, list, update, and manage their UGC tasks.

    Brands can create and manage their own content tasks with appropriate
    validations and business logic.

    Payment fields (`pin`, `payment_option`, `biometrics`) are write-only and
    are consumed by the view's payment flow (CreateAdAndOnboardBrandView-style
    wallet debit / credit application) rather than by this serializer directly.
    `user` is never accepted as input — it is injected by the view from
    `request.user` after payment succeeds.
    """

    amount = serializers.CharField(
        max_length=155,
        required=True,
        allow_blank=False,
        allow_null=False,
        help_text="Monetary amount for the task",
    )
    targeting_type = serializers.ChoiceField(
        choices=["broad", "city", "niche", "influencer"],
        default="broad",
        help_text="Pricing multiplier: broad/city/niche/influencer",
    )
    pin = serializers.CharField(max_length=6, write_only=True, required=False)
    payment_option = serializers.CharField(
        max_length=20, write_only=True, required=True
    )
    card_reference = serializers.CharField(
        write_only=True, required=False, allow_blank=True
    )
    biometrics = serializers.BooleanField(write_only=True, required=False)

    # Owner (read-only — set by the view, never accepted from the client)
    user = serializers.PrimaryKeyRelatedField(read_only=True)

    # Computed fields (read-only)
    available_slots = serializers.SerializerMethodField()
    is_fully_booked = serializers.SerializerMethodField()
    unused_credit = serializers.SerializerMethodField()
    cost_per_engagement = serializers.SerializerMethodField()

    class Meta:
        model = UserGeneratedContent
        fields = [
            "id",
            "user",
            "pin",
            "payment_option",
            "card_reference",
            "biometrics",
            "business_or_brand_name",
            "type_of_business",
            "task_name",
            "task_type",
            "description",
            "unique_identifiers",
            "use_brand_slogan",
            "brand_slogan",
            "thumbnail_url",
            "sample_url",
            "slot_cap",
            "slots_filled",
            "available_slots",
            "is_fully_booked",
            "unlimited_slots",
            "reward_points",
            "auto_boost",
            "auto_boost_points",
            "amount",
            "credit_settled",
            "is_active",
            "gender",
            "demography",
            "location_perimeter",
            "targeting_type",
            "countries",
            "states",
            "cities",
            "task_duration",
            "campaign_duration",
            "unused_credit",
            "cost_per_engagement",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "user",
            "slots_filled",
            "created_at",
            "updated_at",
            "credit_settled",
            "unused_credit",
            "cost_per_engagement",
            "available_slots",
            "is_fully_booked",
        ]

    @extend_schema_field(serializers.IntegerField(allow_null=True))
    def get_available_slots(self, obj):
        """Get the number of available slots for the task."""
        return obj.available_slots

    @extend_schema_field(serializers.BooleanField())
    def get_is_fully_booked(self, obj):
        """Check if the task is fully booked."""
        return obj.is_fully_booked

    @extend_schema_field(serializers.CharField())
    def get_unused_credit(self, obj):
        """Get unused credit as a string representation."""
        return str(obj.unused_credit) if obj.unused_credit else "0.00"

    @extend_schema_field(serializers.CharField())
    def get_cost_per_engagement(self, obj):
        """Get cost per engagement as a string representation."""
        return str(obj.cost_per_engagement) if obj.cost_per_engagement else "0.00"

    def validate_amount(self, value):
        """
        Validate the amount field.

        Args:
            value (str): Amount string to validate

        Returns:
            str: Validated amount string

        Raises:
            serializers.ValidationError: If amount is invalid
        """
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Amount is required for the task.")

        try:
            amount_decimal = Decimal(value)
            if amount_decimal <= 0:
                raise serializers.ValidationError("Amount must be greater than 0.")
            if amount_decimal > 9999999.99:
                raise serializers.ValidationError(
                    "Amount exceeds maximum allowed value of 9,999,999.99."
                )
            if amount_decimal.as_tuple().exponent < -2:
                raise serializers.ValidationError(
                    "Amount cannot have more than 2 decimal places."
                )
        except (ValueError, TypeError, InvalidOperation):
            raise serializers.ValidationError(
                "Amount must be a valid decimal number (e.g., '1000.00')."
            )

        return f"{amount_decimal:.2f}"

    def validate_task_name(self, value):
        """
        Validate task name length and content.

        Args:
            value (str): Task name to validate

        Returns:
            str: Stripped and validated task name

        Raises:
            serializers.ValidationError: If task name is too short or invalid
        """
        value = value.strip()
        if len(value) < 5:
            raise serializers.ValidationError(
                "Task name must be at least 5 characters long."
            )
        if len(value) > 255:
            raise serializers.ValidationError("Task name cannot exceed 255 characters.")
        return value

    def validate_description(self, value):
        """
        Validate task description length.

        Args:
            value (str): Description to validate

        Returns:
            str: Stripped and validated description

        Raises:
            serializers.ValidationError: If description is too short or invalid
        """
        value = value.strip()
        if len(value) < 20:
            raise serializers.ValidationError(
                "Description must be at least 20 characters long."
            )
        if len(value) > 1000:
            raise serializers.ValidationError(
                "Description cannot exceed 1000 characters."
            )
        return value

    def validate_slot_cap(self, value):
        """
        Validate slot cap value.

        Args:
            value (int): Slot cap to validate

        Returns:
            int: Validated slot cap

        Raises:
            serializers.ValidationError: If slot cap is negative or invalid
        """
        if value < 0:
            raise serializers.ValidationError("Slot cap cannot be negative.")
        if value > 100000:
            raise serializers.ValidationError("Slot cap cannot exceed 100,000 slots.")
        return value

    def validate(self, attrs):
        """
        Perform cross-field validation.

        Validates:
        - Location perimeter requires appropriate location data
        - Brand slogan is provided if use_brand_slogan is True
        - Campaign duration is valid
        - Task type is valid
        - Amount is sufficient for slot count

        Args:
            attrs (dict): Dictionary of validated attributes

        Returns:
            dict: Validated attributes

        Raises:
            serializers.ValidationError: If any validation fails
        """
        location_perimeter = attrs.get("location_perimeter")
        states = attrs.get("states", [])
        cities = attrs.get("cities", [])

        if location_perimeter == UserGeneratedContent.LocationPerimeter.STATE:
            if not states:
                raise serializers.ValidationError(
                    {
                        "states": "States must be provided when location_perimeter is 'State'."
                    }
                )
            if any(not state.strip() for state in states):
                raise serializers.ValidationError(
                    {"states": "State names cannot be empty."}
                )

        if location_perimeter == UserGeneratedContent.LocationPerimeter.CITIES:
            if not cities:
                raise serializers.ValidationError(
                    {
                        "cities": "Cities must be provided when location_perimeter is 'Cities'."
                    }
                )
            if any(not city.strip() for city in cities):
                raise serializers.ValidationError(
                    {"cities": "City names cannot be empty."}
                )

        if attrs.get("use_brand_slogan") and not attrs.get("brand_slogan"):
            raise serializers.ValidationError(
                {
                    "brand_slogan": "Brand slogan is required when use_brand_slogan is True."
                }
            )

        task_duration = attrs.get("task_duration")
        if task_duration and task_duration.total_seconds() <= 0:
            raise serializers.ValidationError(
                {"task_duration": "Task duration must be positive."}
            )

        campaign_duration = attrs.get("campaign_duration")
        if campaign_duration and campaign_duration.total_seconds() <= 0:
            raise serializers.ValidationError(
                {"campaign_duration": "Campaign duration must be positive."}
            )

        task_type = attrs.get("task_type")
        if task_type and task_type not in dict(UserGeneratedContent.TaskType.choices):
            raise serializers.ValidationError(
                {
                    "task_type": f"Invalid task type. Must be one of: {', '.join(dict(UserGeneratedContent.TaskType.choices).keys())}."
                }
            )

        countries = attrs.get("countries", [])
        if countries and not isinstance(countries, list):
            raise serializers.ValidationError(
                {"countries": "Countries must be a list of country names."}
            )

        if states and not isinstance(states, list):
            raise serializers.ValidationError(
                {"states": "States must be a list of state names."}
            )

        if cities and not isinstance(cities, list):
            raise serializers.ValidationError(
                {"cities": "Cities must be a list of city names."}
            )

        payment_option = attrs.get("payment_option")
        if payment_option == "WALLET" and not attrs.get("pin"):
            raise serializers.ValidationError(
                {"pin": "This field is required when paying with WALLET."}
            )
        if payment_option == "CARD" and not attrs.get("card_reference"):
            raise serializers.ValidationError(
                {"card_reference": "This field is required when paying with CARD."}
            )

        logger.info(
            "Brand UGC task validation successful: task_name=%r task_type=%r amount=%r",
            attrs.get("task_name", "")[:80],
            task_type,
            attrs.get("amount", "0"),
        )

        return attrs

    def create(self, validated_data):
        """
        Create a new UGC task for the brand.

        The owning brand is taken from the serializer context (set by the
        view as `request.user`) rather than from client input, so a brand
        can never create a task on behalf of another user.

        Args:
            validated_data (dict): Validated data for task creation

        Returns:
            UserGeneratedContent: Created task instance

        Raises:
            serializers.ValidationError: If slot_cap is missing/invalid, or
                if no authenticated user is available in context.

        Note:
            - Reward points are auto-calculated based on task type
            - This method does NOT charge the brand's wallet. Payment
              (wallet debit + BrandAdCreditWallet credit application) is
              handled by the view *before* calling serializer.save().
        """
        validated_data.pop("pin", None)
        validated_data.pop("payment_option", None)
        validated_data.pop("card_reference", None)
        validated_data.pop("biometrics", None)

        request = self.context.get("request")
        if not request or not request.user or not request.user.is_authenticated:
            raise serializers.ValidationError(
                {"user": "Authentication required to create a task."}
            )
        validated_data["user"] = request.user

        if "slot_cap" not in validated_data:
            raise serializers.ValidationError(
                {"slot_cap": "Slot cap is required for the task."}
            )

        slot_cap = validated_data.get("slot_cap", 0)
        if slot_cap <= 0 and not validated_data.get("unlimited_slots", False):
            raise serializers.ValidationError(
                {
                    "slot_cap": "Either slot_cap must be greater than 0 or unlimited_slots must be True."
                }
            )

        if not validated_data.get("reward_points"):
            task_type = validated_data.get("task_type")
            if task_type:
                try:
                    TASK_TYPE_TO_KEY = {
                        "make_a_video": "Make a video",
                        "take_a_picture": "Take a picture",
                    }
                    key = TASK_TYPE_TO_KEY.get(task_type)
                    if key:
                        config = PointConfig.objects.filter(key=key).first()
                        if config:
                            validated_data["reward_points"] = config.value
                except Exception as e:
                    logger.warning(f"Error storing points: {e}")

        task = UserGeneratedContent.objects.create(**validated_data)

        logger.info(
            "Brand UGC task created: id=%s task_name=%r amount=%r brand=%s",
            task.id,
            task.task_name,
            task.amount,
            task.user_id,
        )

        return task

    def update(self, instance, validated_data):
        """
        Update an existing UGC task.

        Args:
            instance (UserGeneratedContent): Existing task instance
            validated_data (dict): Validated update data

        Returns:
            UserGeneratedContent: Updated task instance

        Note:
            - Certain fields cannot be updated once set (e.g., id, created_at)
            - Slot cap can only be increased, not decreased
            - `user` can never be reassigned via update
        """
        if "slot_cap" in validated_data:
            new_slot_cap = validated_data["slot_cap"]
            if new_slot_cap < instance.slot_cap:
                logger.warning(
                    "Attempted to decrease slot cap: task_id=%s from=%s to=%s",
                    instance.id,
                    instance.slot_cap,
                    new_slot_cap,
                )
                raise serializers.ValidationError(
                    {"slot_cap": "Slot cap can only be increased, not decreased."}
                )

        disallowed_fields = ["created_at", "id", "user"]
        for field in disallowed_fields:
            if field in validated_data:
                validated_data.pop(field)

        for field, value in validated_data.items():
            setattr(instance, field, value)

        instance.save()

        logger.info(
            "Brand UGC task updated: id=%s task_name=%r amount=%r",
            instance.id,
            instance.task_name,
            instance.amount,
        )

        return instance


# ==========================================
# Admin-facing Serializer
# ==========================================


class AdminUserGeneratedContentSerializer(serializers.ModelSerializer):
    """
    Full administrator serializer for managing UGC tasks.

    Admins have full CRUD operations and can view all fields including
    sensitive data and administrative fields. Unlike the brand serializer,
    `user` is writable here so admins can create or reassign a task on
    behalf of any brand.
    """

    user = serializers.PrimaryKeyRelatedField(queryset=User.objects.all())

    available_slots = serializers.SerializerMethodField()
    is_fully_booked = serializers.SerializerMethodField()
    unused_credit = serializers.SerializerMethodField()
    cost_per_engagement = serializers.SerializerMethodField()
    task_type_display = serializers.SerializerMethodField()
    gender_display = serializers.SerializerMethodField()
    demography_display = serializers.SerializerMethodField()

    class Meta:
        model = UserGeneratedContent
        fields = [
            "id",
            "user",
            "business_or_brand_name",
            "type_of_business",
            "task_name",
            "task_type",
            "task_type_display",
            "description",
            "unique_identifiers",
            "use_brand_slogan",
            "brand_slogan",
            "sample_url",
            "thumbnail_url",
            "slot_cap",
            "slots_filled",
            "available_slots",
            "is_fully_booked",
            "unlimited_slots",
            "reward_points",
            "auto_boost",
            "auto_boost_points",
            "amount",
            "credit_settled",
            "is_active",
            "gender",
            "gender_display",
            "demography",
            "demography_display",
            "location_perimeter",
            "targeting_type",
            "countries",
            "states",
            "cities",
            "task_duration",
            "campaign_duration",
            "unused_credit",
            "cost_per_engagement",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "slots_filled"]

    @extend_schema_field(serializers.IntegerField(allow_null=True))
    def get_available_slots(self, obj):
        """Get the number of available slots for the task."""
        return obj.available_slots

    @extend_schema_field(serializers.BooleanField())
    def get_is_fully_booked(self, obj):
        """Check if the task is fully booked."""
        return obj.is_fully_booked

    @extend_schema_field(serializers.CharField())
    def get_unused_credit(self, obj):
        """Get unused credit as a string representation."""
        return str(obj.unused_credit)

    @extend_schema_field(serializers.CharField())
    def get_cost_per_engagement(self, obj):
        """Get cost per engagement as a string representation."""
        return str(obj.cost_per_engagement)

    @extend_schema_field(serializers.CharField())
    def get_task_type_display(self, obj):
        """Get the display name for the task type."""
        return dict(UserGeneratedContent.TaskType.choices).get(
            obj.task_type, obj.task_type
        )

    @extend_schema_field(serializers.CharField())
    def get_gender_display(self, obj):
        """Get the display name for gender."""
        return obj.get_gender_display() if obj.gender else None

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_demography_display(self, obj):
        """Get the display name for demography."""
        return obj.get_demography_display() if obj.demography else None

    def validate_task_name(self, value):
        """
        Validate task name length and content.

        Args:
            value (str): Task name to validate

        Returns:
            str: Stripped and validated task name
        """
        value = value.strip()
        if len(value) < 5:
            raise serializers.ValidationError(
                "Task name must be at least 5 characters long."
            )
        return value

    def validate(self, attrs):
        """
        Perform cross-field validation for admin operations.

        Args:
            attrs (dict): Dictionary of validated attributes

        Returns:
            dict: Validated attributes

        Raises:
            serializers.ValidationError: If any validation fails
        """
        location_perimeter = attrs.get("location_perimeter")
        states = attrs.get("states", [])
        cities = attrs.get("cities", [])

        if location_perimeter == UserGeneratedContent.LocationPerimeter.STATE:
            if not states:
                raise serializers.ValidationError(
                    {
                        "states": "States must be provided when location_perimeter is 'State'."
                    }
                )

        if location_perimeter == UserGeneratedContent.LocationPerimeter.CITIES:
            if not cities:
                raise serializers.ValidationError(
                    {
                        "cities": "Cities must be provided when location_perimeter is 'Cities'."
                    }
                )

        if attrs.get("use_brand_slogan") and not attrs.get("brand_slogan"):
            raise serializers.ValidationError(
                {
                    "brand_slogan": "Brand slogan is required when use_brand_slogan is True."
                }
            )

        task_duration = attrs.get("task_duration")
        if task_duration and task_duration.total_seconds() <= 0:
            raise serializers.ValidationError(
                {"task_duration": "Task duration must be positive."}
            )

        campaign_duration = attrs.get("campaign_duration")
        if campaign_duration and campaign_duration.total_seconds() <= 0:
            raise serializers.ValidationError(
                {"campaign_duration": "Campaign duration must be positive."}
            )

        logger.info(
            "Admin UGC task validation successful: task_name=%r",
            attrs.get("task_name", "")[:80],
        )

        return attrs

    def create(self, validated_data):
        """
        Create a new UGC task as an administrator.

        Args:
            validated_data (dict): Validated data for task creation. Must
                include `user` (the brand the task is created for).

        Returns:
            UserGeneratedContent: Created task instance
        """
        validated_data.setdefault("slot_cap", 0)
        validated_data.setdefault("auto_boost_points", 0)
        validated_data.setdefault("amount", "0.00")
        validated_data.setdefault("slots_filled", 0)

        task = UserGeneratedContent.objects.create(**validated_data)

        logger.info(
            "Admin UGC task created: id=%s task_name=%r for_user=%s",
            task.id,
            task.task_name,
            task.user_id,
        )

        return task

    def update(self, instance, validated_data):
        """
        Update an existing UGC task as an administrator.

        Args:
            instance (UserGeneratedContent): Existing task instance
            validated_data (dict): Validated update data

        Returns:
            UserGeneratedContent: Updated task instance
        """
        for field, value in validated_data.items():
            setattr(instance, field, value)

        instance.save()

        logger.info(
            "Admin UGC task updated: id=%s task_name=%r",
            instance.id,
            instance.task_name,
        )

        return instance

    def delete(self, instance):
        """
        Delete a UGC task as an administrator.

        Args:
            instance (UserGeneratedContent): Task instance to delete

        Returns:
            bool: True if deletion was successful

        Raises:
            serializers.ValidationError: If the task still has filled slots.
        """
        task_id = instance.id
        task_name = instance.task_name

        if instance.slots_filled > 0:
            raise serializers.ValidationError("Cannot delete a task with filled slots.")

        instance.delete()

        logger.info("Admin UGC task deleted: id=%s task_name=%r", task_id, task_name)

        return True


# ==============================================
#  User-Generated Content Submission Serializers
# ==============================================


class UGCTaskSubmissionSerializer(serializers.ModelSerializer):
    """Serializer for UGC task submissions."""

    task_name = serializers.CharField(source="task.task_name", read_only=True)
    task_type = serializers.CharField(source="task.task_type", read_only=True)
    reward_points = serializers.IntegerField(
        source="task.reward_points", read_only=True
    )
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    submitted_at_display = serializers.SerializerMethodField()

    class Meta:
        model = UGCTaskSubmission
        fields = [
            "id",
            "task",
            "task_name",
            "task_type",
            "reward_points",
            "media_url",
            "caption",
            "status",
            "status_display",
            "rejection_reason",
            "submitted_at",
            "submitted_at_display",
            "reviewed_at",
            "points_awarded",
            "points_reason",
            "ip_address",
        ]
        read_only_fields = [
            "id",
            "status",
            "rejection_reason",
            "submitted_at",
            "reviewed_at",
            "points_awarded",
            "points_reason",
            "status_display",
            "submitted_at_display",
            "ip_address",
        ]

    @extend_schema_field(serializers.CharField())
    def get_submitted_at_display(self, obj):
        if obj.submitted_at:
            return obj.submitted_at.strftime("%b %d, %Y at %I:%M %p")
        return None


class UGCTaskSubmitSerializer(serializers.ModelSerializer):
    """Serializer for submitting a UGC task."""

    class Meta:
        model = UGCTaskSubmission
        fields = [
            "task",
            "media_url",
            "caption",
        ]

    def validate_media_url(self, value):
        """Validate the media URL with stronger checks."""
        if not value:
            raise serializers.ValidationError("Media URL is required.")

        # Basic URL validation
        validator = URLValidator()
        try:
            validator(value)
        except ValidationError:
            raise serializers.ValidationError("Invalid media URL format.")

        # Enforce Cloudinary URLs
        allowed_domains = [
            "res.cloudinary.com",
            "cloudinary.com",
        ]

        if not any(domain in value.lower() for domain in allowed_domains):
            raise serializers.ValidationError(
                f"Media URL must be from Cloudinary. Supported: {', '.join(allowed_domains)}"
            )

        # Check file extension
        valid_extensions = [
            ".jpg",
            ".jpeg",
            ".png",
            ".gif",
            ".webp",
            ".mp4",
            ".mov",
            ".avi",
            ".webm",
        ]
        if not any(value.lower().endswith(ext) for ext in valid_extensions):
            raise serializers.ValidationError(
                f"Invalid file type. Supported: {', '.join(valid_extensions)}"
            )

        return value

    def validate(self, attrs):
        """Cross-field validation."""
        task = attrs.get("task")
        user = self.context.get("request").user

        # Check if task is active and available
        if not task.is_active:
            raise serializers.ValidationError("This task is no longer active.")

        if task.is_fully_booked:
            raise serializers.ValidationError("This task has reached its slot limit.")

        if task.is_expired:
            raise serializers.ValidationError("This task has expired.")

        # Check if user already submitted (pending or approved only)
        if UGCTaskSubmission.objects.filter(
            user=user, task=task, status__in=["pending", "approved"]
        ).exists():
            raise serializers.ValidationError("You have already submitted this task.")

        return attrs

    def create(self, validated_data):
        """Create a new submission and auto-approve."""
        user = self.context.get("request").user
        ip_address = self.context.get("ip_address")

        submission, success, message = UGCTaskSubmission.auto_approve(
            user=user,
            task=validated_data["task"],
            media_url=validated_data["media_url"],
            caption=validated_data.get("caption", ""),
            ip_address=ip_address,
        )

        if not success:
            raise serializers.ValidationError(message)

        return submission


class UGCTaskProgressSerializer(serializers.ModelSerializer):
    """Serializer for user's UGC task progress."""

    completion_rate = serializers.SerializerMethodField()
    next_milestone = serializers.SerializerMethodField()
    ugc_level = serializers.SerializerMethodField()

    class Meta:
        model = UGCTaskProgress
        fields = [
            "id",
            "total_submissions",
            "approved_submissions",
            "rejected_submissions",
            "current_streak",
            "longest_streak",
            "last_submission_date",
            "completed_task_types",
            "achievements",
            "first_submission_at",
            "completion_rate",
            "next_milestone",
            "ugc_level",
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.FloatField())
    def get_completion_rate(self, obj):
        if obj.total_submissions == 0:
            return 0.0
        return round((obj.approved_submissions / obj.total_submissions) * 100, 1)

    @extend_schema_field(serializers.IntegerField())
    def get_next_milestone(self, obj):
        milestones = [1, 5, 10, 25, 50, 100, 250, 500]
        for milestone in milestones:
            if obj.approved_submissions < milestone:
                return milestone
        return None

    @extend_schema_field(serializers.CharField())
    def get_ugc_level(self, obj):
        from gamification.points import Points

        return Points.get_ugc_level(obj.approved_submissions)


class UGCLeaderboardSerializer(serializers.ModelSerializer):
    """Serializer for UGC leaderboard entries."""

    user_name = serializers.CharField(source="user.get_full_name", read_only=True)
    user_email = serializers.EmailField(source="user.email", read_only=True)
    profile_image = serializers.SerializerMethodField()

    class Meta:
        model = UGCLeaderboard
        fields = [
            "user",
            "user_name",
            "user_email",
            "profile_image",
            "rank",
            "points_earned",
            "tasks_completed",
            "period_start",
            "period_end",
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.URLField(allow_null=True))
    def get_profile_image(self, obj):
        if hasattr(obj.user, "profile_image"):
            return obj.user.profile_image.url if obj.user.profile_image else None
        return None
