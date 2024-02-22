# Third party imports.
from rest_framework import serializers

# In project imports.
from accounts.models import User
from vas.models import AirtimeTopup


class ProfileImageSerializer(serializers.Serializer):
    profile_image = serializers.ImageField()


class GetUserSerializer(serializers.ModelSerializer):
    """Serailizers for retrieving User profile."""

    class Meta:
        model = User
        fields = [
            "id",
            "first_name",
            "last_name",
            "account_type",
            "profile_img_url",
            "country",
            "state",
            "city",
            "phone_number",
            "email",
            "created_at",
            "updated_at",
            "is_verified",
            "is_member",
        ]


class UpdateUserSerializer(serializers.ModelSerializer):
    """Serailizers for updating our users' profile."""

    class Meta:
        model = User
        fields = [
            "id",
            "country",
            "state",
            "city",
            "created_at",
            "updated_at",
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
        fields = ['service_id', 'phone_number', 'form_of_gift']
