# Third party imports.
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field

# In project imports.
from accounts.models import User
from .models import PointConfig, StepCampaignModel, StepSessionModel, StreakChallenge, StreakHistory, UserStreak, SCHEDULE_TYPE_CHOICES


class SSOLoginSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)

    class Meta:
        model = User
        fields = [
            "email",
        ]


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
    time_remaining = serializers.DurationField(read_only=True)
    completed = serializers.BooleanField(read_only=True)

    class Meta:
        model = StepCampaignModel
        fields = [
            'id', "campaign_id", "name", "duration", "step_target", "reward_points",
            "created_by", "created_at", "description",
            "completed", "time_limit",
            "total_steps", "is_campaign_active", "time_remaining"
        ]
        read_only_fields = ['created_by', 'created_at']


class StepCampaignListSerializer(serializers.ModelSerializer):
    class Meta:
        model = StepCampaignModel
        fields = ["id", "campaign_id", "name", "description", "duration", "step_target", "reward_points", "created_at"]


class StepCampaignDetailSerializer(serializers.ModelSerializer):
    participants = serializers.SerializerMethodField()
    duration = serializers.SerializerMethodField()
    created_at = serializers.SerializerMethodField()

    class Meta:
        model = StepCampaignModel
        fields = [
            "id", "name", "description", "duration", "step_target",
            "reward_points", "created_at", "participants"
        ]

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

    class Meta:
        model = StreakChallenge
        fields = [
            "id", "name", "description", "streak_type", "duration_days",
            "start_date", "end_date", "reward_points", "reminder_time",
            "is_active", "is_paused", "is_ongoing", "participant_count",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    @extend_schema_field(serializers.IntegerField())
    def get_participant_count(self, obj):
        return obj.user_streaks.count()


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
            total_days = max(1, (end - start).days)
            if data.get("duration_days", 0) > total_days:
                raise serializers.ValidationError(
                    "duration_days cannot exceed the duration of the challenge."
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
    participant_count = serializers.SerializerMethodField()
    days_remaining = serializers.SerializerMethodField()

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
            "participant_cap",
            "participant_count",
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
        read_only_fields = ["id", "task_status", "is_scheduled", "participant_count", "days_remaining", "created_at", "updated_at"]

    @extend_schema_field(serializers.IntegerField())
    def get_participant_count(self, obj):
        return obj.user_streaks.count()

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
