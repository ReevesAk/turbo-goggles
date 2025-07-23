# Third party imports.
from rest_framework import serializers

# In project imports.
from accounts.models import User
from .models import StepCampaignModel, StepSessionModel


class SSOLoginSerializer(serializers.ModelSerializer):

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
        fields = ["id", "name", "description", "duration", "step_target", "reward_points", "created_at"]


class StepCampaignDetailSerializer(serializers.ModelSerializer):
    participants = serializers.SerializerMethodField()

    class Meta:
        model = StepCampaignModel
        fields = [
            "id", "name", "description", "duration", "step_target",
            "reward_points", "created_at", "participants"
        ]

    def get_participants(self, obj):
        # Assuming there's a related model like StepCampaignParticipation or M2M through
        participants = obj.participants.all()  # Update this according to your relationship
        return [{"user_id": u.id, "full_name": u.full_name} for u in participants]


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


class StepCountSessionSerializer(serializers.ModelSerializer):
    campaign_name = serializers.CharField(source="campaign.name", read_only=True)
    step_target = serializers.IntegerField(source="campaign.step_target", read_only=True)

    class Meta:
        model = StepSessionModel
        fields = [
            "session_id", "campaign", "campaign_name",
            "session_date", "step_count", "completed", "step_target"
        ]
        read_only_fields = ["session_id", "completed"]
