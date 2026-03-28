# Third party imports.
from rest_framework import serializers

# In project imports.
from accounts.models import User, UserNotification
from .models import MemberSurvey
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
        ]

    def get_balance(self, obj):
        points = getattr(obj, "points_set", None)
        if points and points.exists():
            return points.first().balance
        return 0

    def get_redeemable(self, obj):
        points = getattr(obj, "points_set", None)
        if points and points.exists():
            return points.first().redeemable
        return 0


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


class MemberSurverySerializers(serializers.ModelSerializer):
    """Serailizers for  conducting member survery."""

    class Meta:
        model = MemberSurvey
        fields = [
            "id",
            "age_bracket",
            "sex",
            "religion",
            "wheredoyoulive",
            "state",
            "facebook_followers",
            "facebook_handle",
            "twitter_followers",
            "twitter_handle",
            "thread_followers",
            "thread_handle",
            "instagram_followers",
            "instagram_handle",
            "telegram_followers",
            "telegram_handle",
            "leisure_activities",
            "phone_activities",
            "music_genre",
            "social_event",
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

    class Meta:
        model = None
        fields = ["service_id", "phone_number", "form_of_gift"]


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
