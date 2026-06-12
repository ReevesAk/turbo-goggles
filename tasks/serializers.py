from rest_framework import serializers

from .models import SocialProfile, SocialTask, TaskSubmission, VerificationResult, UserTrustScore


class SocialProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = SocialProfile
        fields = ["x_username", "instagram_username", "facebook_username", "tiktok_username"]


class SocialTaskSerializer(serializers.ModelSerializer):
    is_expired = serializers.BooleanField(read_only=True)
    is_available = serializers.BooleanField(read_only=True)

    class Meta:
        model = SocialTask
        fields = [
            "id", "title", "description", "platform", "task_type",
            "target_url", "target_account", "required_hashtag",
            "required_mention", "required_keywords",
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
            "username_matched", "hashtag_found", "mention_found", "action_confirmed",
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
            "verification",
        ]
        read_only_fields = [
            "id", "status", "reward_issued", "rejection_reason",
            "reviewed_at", "verification",
        ]


class SubmitTaskSerializer(serializers.ModelSerializer):
    """Used when a user submits proof for a task."""

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
        return TaskSubmission.objects.create(user=user, **validated_data)


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
