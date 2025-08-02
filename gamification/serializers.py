# Third party imports.
from rest_framework import serializers

# In project imports.
from accounts.models import User
from .models import StepCampaignModel, StepSessionModel


class SSOLoginSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)

    class Meta:
        model = User
        fields = [
            "email",
        ]


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
