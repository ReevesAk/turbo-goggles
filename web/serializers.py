import re

# Third party imports.
from rest_framework import serializers

# In project imports.
from .models import (
    Applications,
    ContactUs
)


from .models import JobModel, NewsletterSubscribers

PHONE_REGEX = re.compile(r"^\+?[1-9]\d{7,14}$")


class JobSerializer(serializers.ModelSerializer):
    pin = serializers.CharField(
        max_length=5, min_length=5, required=True, allow_blank=True
    )
    key_responsibilities = serializers.ListField(
        child=serializers.CharField(),
        required=False
    )
    requirements = serializers.ListField(
        child=serializers.CharField(),
        required=False
    )

    class Meta:
        model = JobModel
        fields = [
            "id",
            "pin",
            "title",
            "job_type",
            "company",
            "job_summary",
            "key_responsibilities",
            "requirements",
            "location",
            "salary",
            "is_active",
            "expires_at",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class ListJobSerializer(serializers.ModelSerializer):
    key_responsibilities = serializers.ListField(
        child=serializers.CharField(),
        required=False
    )
    requirements = serializers.ListField(
        child=serializers.CharField(),
        required=False
    )

    class Meta:
        model = JobModel
        fields = [
            "id",
            "title",
            "job_type",
            "company",
            "job_summary",
            "key_responsibilities",
            "requirements",
            "location",
            "salary",
            "is_active",
            "expires_at",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class ApplicationsSerializers(serializers.ModelSerializer):
    cv = serializers.FileField(write_only=True)

    class Meta:
        model = Applications
        fields = [
            "first_name",
            "last_name",
            "gender",
            "phone_number",
            "state",
            "lga",
            "address",
            "email",
            "cv",
        ]


class GetApplicationsSerializers(serializers.ModelSerializer):
    class Meta:
        model = Applications
        fields = [
            "id",
            "first_name",
            "last_name",
            "gender",
            "phone_number",
            "state",
            "lga",
            "address",
            "email",
            "cv",
        ]


class NewsletterSubscribersSerializer(serializers.ModelSerializer):
    class Meta:
        model = NewsletterSubscribers
        fields = ["id", "email", "subscribed_at"]
        read_only_fields = ["id", "subscribed_at"]


class UnsubscribeNewsletterSerializer(serializers.ModelSerializer):
    class Meta:
        model = NewsletterSubscribers
        fields = ["token"]


class ContactUsSerializer(serializers.ModelSerializer):
    channel = serializers.DictField()

    class Meta:
        model = ContactUs
        fields = [
            "contact_type",
            "first_name",
            "last_name",
            "businesss_name",
            "product_of_interest",
            "channel",
            "message",
            "accept_policy",
        ]

    def validate_channel(self, value):
        """
        channel format:
        {
            "type": "email" | "phone" | "whatsapp",
            "value": "<string>"
        }
        """
        if not isinstance(value, dict):
            raise serializers.ValidationError("Channel must be an object.")

        channel_type = value.get("type")
        channel_value = value.get("value")

        allowed_types = ["email", "phone", "whatsapp"]

        if channel_type not in allowed_types:
            raise serializers.ValidationError(
                f"Channel type must be one of {allowed_types}."
            )

        if not channel_value:
            raise serializers.ValidationError("Channel value is required.")

        # Email validation
        if channel_type == "email":
            serializers.EmailField().run_validation(channel_value)

        # Phone / WhatsApp validation
        if channel_type in ["phone", "whatsapp"]:
            if not PHONE_REGEX.match(channel_value):
                raise serializers.ValidationError(
                    "Invalid phone number format. Use international format e.g. +2348012345678"
                )

        return value

    def validate(self, data):
        contact_type = data.get("contact_type")

        if not data.get("accept_policy"):
            raise serializers.ValidationError({
                "accept_policy": "You must accept the policy to continue."
            })

        if contact_type == "Business Use":
            if not data.get("businesss_name"):
                raise serializers.ValidationError({
                    "businesss_name": "Business name is required for Business Use."
                })

        if contact_type == "Personal Use":
            if not data.get("first_name") or not data.get("last_name"):
                raise serializers.ValidationError({
                    "full_name": "First and last name are required for Personal Use."
                })

            if data.get("businesss_name"):
                raise serializers.ValidationError({
                    "businesss_name": "Business name is not allowed for Personal Use."
                })

        return data
