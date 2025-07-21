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

    class Meta:
        model = User
        fields = [
            "id",
            "first_name",
            "last_name",
            "active_role",
            "has_wallet",
            "profile_img_url",
            "country",
            "state",
            "city",
            "phone_number",
            "email",
            "created_at",
            "updated_at",
            "is_verified",
            "has_created_pin",
            "has_bonus",
            "welcome_bonus",
            "has_card",
        ]


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
            "twitter_followers",
            "thread_followers",
            "instagram_followers",
            "telegram_followers",
            "leisure_activities",
            "phone_activities",
            "music_genre",
            "social_event",
        ]


class ChangePasswordSerializer(serializers.ModelSerializer):
    old_password = serializers.CharField(max_length=68, min_length=6, write_only=True)
    new_password = serializers.CharField(max_length=68, min_length=6, write_only=True)

    class Meta:
        model = User
        fields = ["old_password", "new_password"]


class DeleteUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["email"]


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


class SwitchToUserSerializer(serializers.Serializer):
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


class SupportTicketSerializer(serializers.Serializer):
    class Meta:
        model = Ticket
        fields = ["description", "category"]
