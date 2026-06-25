# Third party imports.
from rest_framework import serializers

# In project imports.
from accounts.models import User, UserNotification
from .models import HandleChangeRequest, MemberSurvey, UserLocation
from fmcg.models import Favourite
from support.models import Ticket


class ProfileImageSerializer(serializers.Serializer):
    class Meta:
        model = User
        fields = [
            "profile_img_url",
        ]


class GetUserSerializer(serializers.ModelSerializer):
    """Serailizers for retrieving User profile."""

    balance = serializers.SerializerMethodField()
    redeemable = serializers.SerializerMethodField()
    tier = serializers.CharField(read_only=True)
    socials = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "first_name",
            "last_name",
            "active_role",
            "has_wallet",
            "profile_img_url",
            "alert_type_choice",
            "country",
            "state",
            "city",
            "phone_number",
            "email",
            "created_at",
            "updated_at",
            "is_verified",
            "total_points",
            "level",
            "has_done_survey",
            "is_member",
            "has_created_pin",
            "has_bonus",
            "welcome_bonus",
            "has_card",
            "balance",
            "redeemable",
            "is_bvn_verified",
            "is_nin_verified",
            "points_naira_value",
            "tier",
            "referral_code",
            "socials",
        ]

    def get_balance(self, obj) -> int:
        points = getattr(obj, "points_set", None)
        if points and points.exists():
            return points.first().balance
        return 0

    def get_redeemable(self, obj) -> int:
        points = getattr(obj, "points_set", None)
        if points and points.exists():
            return points.first().redeemable
        return 0

    def get_socials(self, obj) -> dict | None:
        try:
            profile = obj.social_profile
        except MemberSurvey.DoesNotExist:
            return None
        return {
            "facebook": {
                "handle": profile.facebook_handle,
                "followers": profile.facebook_followers,
            },
            "twitter": {
                "handle": profile.twitter_handle,
                "followers": profile.twitter_followers,
            },
            "instagram": {
                "handle": profile.instagram_handle,
                "followers": profile.instagram_followers,
            },
            "tiktok": {
                "handle": profile.tiktok_handle,
                "followers": profile.tiktok_followers,
            },
            "youtube": {
                "handle": profile.youtube_handle,
                "followers": profile.youtube_followers,
            },
            "linkedin": {"handle": profile.linkedin_handle, "followers": None},
            "threads": {
                "handle": profile.thread_handle,
                "followers": profile.thread_followers,
            },
            "telegram": {
                "handle": profile.telegram_handle,
                "followers": profile.telegram_followers,
            },
        }


class UpdateUserSerializer(serializers.ModelSerializer):
    """Serailizers for updating our users' profile."""

    class Meta:
        model = User
        fields = [
            "id",
            "state",
            "city",
            "created_at",
            "updated_at",
        ]


class SetAlertTypeSerializer(serializers.ModelSerializer):
    """Serailizers for updating our users' profile."""

    class Meta:
        model = User
        fields = ["alert_type_choice"]


class MemberSurveySerializers(serializers.ModelSerializer):
    """Serializer for member survey and social profile."""

    class Meta:
        model = MemberSurvey
        fields = [
            "id",
            "age_bracket",
            "sex",
            "religion",
            "wheredoyoulive",
            "state",
            "facebook_handle",
            "twitter_handle",
            "instagram_handle",
            "tiktok_handle",
            "youtube_handle",
            "linkedin_handle",
        ]


class ChangePasswordSerializer(serializers.ModelSerializer):
    old_password = serializers.CharField(max_length=68, min_length=10, write_only=True)
    new_password = serializers.CharField(max_length=68, min_length=10, write_only=True)

    class Meta:
        model = User
        fields = ["old_password", "new_password"]


class DeleteUserSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)


class NotificationSerializers(serializers.Serializer):
    class Meta:
        model = UserNotification
        fields = ["id", "title", "message", "read"]


class ClearNotificationSerializer(serializers.Serializer):
    message = serializers.CharField(max_length=200)


class DeleteNotificationStatusSerializer(serializers.Serializer):
    message = serializers.CharField(max_length=200)


class ProfileStatusSerializer(serializers.Serializer):
    message = serializers.CharField(max_length=200)


class OpenRewardBoxSerializers(serializers.Serializer):
    message = serializers.CharField(max_length=200)


class ClaimRewardSerializers(serializers.Serializer):
    serviceID = serializers.CharField(max_length=68, min_length=6, write_only=True)
    phone_number = serializers.CharField(max_length=68, min_length=6, write_only=True)
    form_of_gift = serializers.CharField(max_length=68, min_length=6, write_only=True)


class SwitchToMemberSerializer(serializers.Serializer):
    message = serializers.CharField(max_length=200)


class SwitchToPartnersSerializer(serializers.Serializer):
    message = serializers.CharField(max_length=200)


class SwitchToBrandAdSerializer(serializers.Serializer):
    message = serializers.CharField(max_length=200)


class AddToFavouriteSerializer(serializers.ModelSerializer):
    object_id = serializers.CharField(max_length=200)
    model_name = serializers.CharField(max_length=200)

    class Meta:
        model = Favourite
        fields = ["object_id", "model_name"]


class FavouriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Favourite
        fields = ["id", "user", "content_type", "object_id", "added_at"]


class SupportTicketSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ticket
        fields = ["description", "category"]


class TierSerializer(serializers.Serializer):
    title = serializers.CharField()
    min_points = serializers.IntegerField()


class TierDataSerializer(serializers.Serializer):
    current_level = serializers.CharField()
    total_points = serializers.IntegerField()
    tiers = TierSerializer(many=True)


class TierListResponseSerializer(serializers.Serializer):
    status = serializers.CharField()
    message = serializers.CharField()
    data = TierDataSerializer()


class HandleChangeRequestSerializer(serializers.ModelSerializer):
    """User submits a handle change request."""

    class Meta:
        model = HandleChangeRequest
        fields = ["id", "platform", "new_handle", "proof_url", "status", "created_at"]
        read_only_fields = ["id", "status", "created_at"]


class HandleChangeRequestDetailSerializer(serializers.ModelSerializer):
    """Full detail for admin review."""

    user_email = serializers.CharField(source="user.email", read_only=True)
    user_name = serializers.CharField(source="user.full_name", read_only=True)
    reviewed_by_email = serializers.CharField(
        source="reviewed_by.email", read_only=True, default=None
    )

    class Meta:
        model = HandleChangeRequest
        fields = [
            "id",
            "user_email",
            "user_name",
            "platform",
            "new_handle",
            "proof_url",
            "status",
            "admin_note",
            "reviewed_by_email",
            "created_at",
            "reviewed_at",
        ]
        read_only_fields = fields


class ReviewHandleChangeSerializer(serializers.Serializer):
    """Admin approves or rejects a handle change request."""

    action = serializers.ChoiceField(choices=["approve", "reject"])
    admin_note = serializers.CharField(required=False, allow_blank=True)


# ===== User Location Serializers =====
class CreateUpdateUserLocationSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating user location."""

    class Meta:
        model = UserLocation
        fields = ["latitude", "longitude"]

    def validate_latitude(self, value):
        """Validate latitude is within valid range."""
        if not -90 <= value <= 90:
            raise serializers.ValidationError(
                "Latitude must be between -90 and 90 degrees."
            )
        return value

    def validate_longitude(self, value):
        """Validate longitude is within valid range."""
        if not -180 <= value <= 180:
            raise serializers.ValidationError(
                "Longitude must be between -180 and 180 degrees."
            )
        return value


class UserLocationResponseSerializer(serializers.ModelSerializer):
    """Serializer for location response with user details."""

    user_email = serializers.EmailField(source="user.email", read_only=True)
    user_name = serializers.SerializerMethodField()

    class Meta:
        model = UserLocation
        fields = [
            "id",
            "user_email",
            "user_name",
            "latitude",
            "longitude",
            "created_at",
            "updated_at",
        ]

    def get_user_name(self, obj):
        """Get user's full name or fallback to first/last name."""
        if obj.user.full_name:
            return obj.user.full_name
        return f"{obj.user.first_name or ''} {obj.user.last_name or ''}".strip()
