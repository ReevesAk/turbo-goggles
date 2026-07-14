# Third party imports.
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field

# In project imports.
from accounts.models import User
from .models import (
    PointConfig,
    RewardRule,
    RewardTier,
    StepCampaignModel,
    StepSessionModel,
    StreakChallenge,
    StreakHistory,
    UserStreak,
    SCHEDULE_TYPE_CHOICES,
)


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
            raise serializers.ValidationError("Either pin or use_biometrics is required.")
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
            'id', "campaign_id", "name", "duration", "step_target", "reward_points",
            "created_by", "created_at", "description",
            "completed", "time_limit",
            "total_steps", "is_campaign_active", "status", "time_remaining"
        ]
        read_only_fields = ['created_by', 'created_at']


def _user_campaign_status(campaign, request):
    """
    "completed" if the requesting user has finished their own step target
    on this campaign, else the campaign's own active/expired state.
    """
    if request and request.user.is_authenticated:
        session = StepSessionModel.objects.filter(user=request.user, campaign=campaign).first()
        if session and session.completed:
            return "completed"
    return campaign.status


class StepCampaignListSerializer(serializers.ModelSerializer):
    status = serializers.SerializerMethodField()

    class Meta:
        model = StepCampaignModel
        fields = ["id", "campaign_id", "name", "description", "duration", "step_target", "reward_points", "created_at", "status"]

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
            "id", "name", "description", "duration", "step_target",
            "reward_points", "created_at", "status", "participants"
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
        sessions = StepSessionModel.objects.filter(campaign=obj).select_related('user')

        participants = []
        for session in sessions:
            participants.append({
                "user_id": session.user.id,
                "full_name": session.user.full_name,
                "step_count": session.step_count,
                "completed": session.completed,
                "started_at": str(session.started_at)
            })

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
    step_target = serializers.IntegerField(source="campaign.step_target", read_only=True)
    reward_points = serializers.IntegerField(source="campaign.reward_points", read_only=True)
    campaign_end_time = serializers.DateTimeField(source="campaign.campaign_end_time", read_only=True)
    time_limit = serializers.DurationField(source="campaign.time_limit", read_only=True)

    class Meta:
        model = StepSessionModel
        fields = [
            "session_id", "campaign", "campaign_name",
            "session_date", "step_count", "completed",
            "step_target", "reward_points", "started_at", "last_updated",
            "campaign_end_time", "time_limit"
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
            "id", "name", "description", "streak_type", "duration_days",
            "start_date", "end_date", "reward_points", "reminder_time",
            "is_active", "is_paused", "is_ongoing", "participant_count",
            "participant_names", "completed_tasks", "total_points_earned", "created_at",
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
                "name": us.user.full_name or f"{us.user.first_name or ''} {us.user.last_name or ''}".strip(),
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
            "name", "description", "streak_type", "duration_days",
            "start_date", "end_date", "reward_points", "reminder_time",
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
        fields = ["name", "description", "end_date", "reward_points", "reminder_time", "is_active", "is_paused"]


class UserStreakSerializer(serializers.ModelSerializer):
    challenge_name = serializers.CharField(source="challenge.name", read_only=True)
    challenge_type = serializers.CharField(source="challenge.streak_type", read_only=True)
    duration_days = serializers.IntegerField(source="challenge.duration_days", read_only=True)
    reward_points = serializers.IntegerField(source="challenge.reward_points", read_only=True)
    days_remaining = serializers.SerializerMethodField()

    class Meta:
        model = UserStreak
        fields = [
            "id", "challenge", "challenge_name", "challenge_type",
            "duration_days", "reward_points",
            "current_count", "longest_count", "last_activity_date",
            "completed", "completed_at", "reward_issued",
            "days_remaining", "joined_at",
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
            "id", "challenge", "challenge_name",
            "streak_count_reached", "broken_at", "completed", "reward_issued", "recorded_at",
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
        ]

    def validate(self, data):
        start = data.get("start_date")
        end = data.get("end_date")
        if start and end:
            if end <= start:
                raise serializers.ValidationError("end_date must be after start_date.")
            window_minutes = int((end - start).total_seconds() // 60)
            task_minutes = data.get("duration_days", 0) * 1440 + data.get("duration_minutes", 0)
            if task_minutes > window_minutes:
                raise serializers.ValidationError(
                    "Total duration (days + minutes) cannot exceed the challenge window."
                )
        if data.get("schedule_type") and not data.get("scheduled_start_time"):
            raise serializers.ValidationError(
                "scheduled_start_time is required when schedule_type is set."
            )
        return data


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
            "is_active",
            "is_paused",
            "is_cancelled",
            "is_scheduled",
            "task_status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "task_status", "is_scheduled", "duration_display", "participant_count", "participant_names", "completed_tasks", "total_points_earned", "days_remaining", "created_at", "updated_at"]

    @extend_schema_field(serializers.IntegerField())
    def get_participant_count(self, obj):
        return obj.user_streaks.count()

    @extend_schema_field(serializers.ListField(child=serializers.DictField()))
    def get_participant_names(self, obj):
        return [
            {
                "id": str(us.user.id),
                "name": us.user.full_name or f"{us.user.first_name or ''} {us.user.last_name or ''}".strip(),
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
            "is_active",
            "is_paused",
            "is_cancelled",
        ]


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
        ]


class RewardTierCreateSerializer(serializers.ModelSerializer):
    """Used by admin to add a value band to an existing reward rule."""

    class Meta:
        model = RewardTier
        fields = ["label", "min_value", "max_value", "points"]

    def validate(self, data):
        max_value = data.get("max_value")
        if max_value is not None and max_value < data["min_value"]:
            raise serializers.ValidationError("max_value cannot be less than min_value.")
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
            raise serializers.ValidationError("max_value cannot be less than min_value.")
        return data
