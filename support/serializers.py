# Third party imports.
from rest_framework import serializers

# In project imports.
from accounts.models import User
from .models import (
    Ticket, AgentRating
)
from accounts.models import User
from accounts.models import USER_CATEGORY_CHOICES, AccountType


class CreateTicketSerializers(serializers.ModelSerializer):
    email = serializers.CharField(max_length=68, min_length=6, write_only=True)

    class Meta:
        model = Ticket
        fields = [
            "id",
            "category",
            "channel",
            "email",
            "description",
        ]


class TicketSerializers(serializers.ModelSerializer):

    class Meta:
        model = Ticket
        fields = [
            "id",
            "number",
            "category",
            "channel",
            "description",
            "escalation_level",
            "status",
            "assigned_at",
        ]


class UserWithTicketsSerializer(serializers.ModelSerializer):
    user_tickets = TicketSerializers(many=True, read_only=True)

    class Meta:
        model = User
        fields = ['id', 'first_name', 'last_name', 'email', 'user_tickets']


class AssignTicketSerializers(serializers.ModelSerializer):
    agent_email = serializers.CharField(max_length=68, min_length=6, write_only=True)
    pin = serializers.CharField(max_length=5, min_length=6, write_only=True)
    ticket_number = serializers.CharField(max_length=68, min_length=6, write_only=True)

    class Meta:
        model = Ticket
        fields = [
            "pin",
            "ticket_number",
            "agent_email",
            "status",
            "escalation_level"
        ]


class AgentRatingSerializers(serializers.ModelSerializer):
    rating_comment = serializers.CharField(max_length=68, min_length=6, write_only=True, required=False)

    class Meta:
        model = AgentRating
        fields = [
            "id",
            "rating",
            "rating_comment"
        ]


class PusherSerializers(serializers.ModelSerializer):
    message = serializers.CharField(max_length=68, min_length=6, write_only=True)

    class Meta:
        model = AgentRating
        fields = [
            "id",
            "message",
        ]


class AddAgentSerializer(serializers.ModelSerializer):
    """Serializer for other agents initial registration step."""

    role = serializers.ListField(
        child=serializers.ChoiceField(choices=USER_CATEGORY_CHOICES), write_only=True
    )

    class Meta:
        model = User
        fields = ["id", "role", "full_name", "email"]
        extra_kwargs = {"email": {"required": True}}

    def validate(self, attrs):
        return super().validate(attrs)

    def create(self, validated_data):
        user_types = validated_data.pop("roles", [])
        user = super().create(validated_data)

        # Assign multiple AccountType entries based on roles
        AccountType.objects.bulk_create(
            [AccountType(user=user, user_type=user_type) for user_type in user_types]
        )

        return user


class AddAgentContdSerializer(serializers.ModelSerializer):
    """Serializer for other support agents first-time registration."""

    password2 = serializers.CharField(max_length=68, min_length=6, write_only=True)

    class Meta:
        model = User
        fields = ["phone_number", "password", "password2"]
        extra_kwargs = {"password": {"write_only": True}}

    def validate(self, attrs):
        password = attrs.get("password")
        password2 = attrs.get("password2")

        if password != password2:
            raise serializers.ValidationError(
                {"password": "Passwords do not match."}
            )

        return attrs

    def create(self, validated_data):
        validated_data.pop("password2")  # Remove password2 from validated data
        user = User(**validated_data)
        user.set_password(validated_data["password"])  # Hash the password
        user.save()
        return user

    def update(self, instance, validated_data):
        validated_data.pop("password2", None)  # Remove password2 if present
        if "password" in validated_data:
            instance.set_password(validated_data["password"])
        return super().update(instance, validated_data)


class SupportAgentLoginSerializers(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["email", "password"]


class CreateAgentPinSerializer(serializers.ModelSerializer):
    """Serailizers for agents first time pin creation."""

    pin = serializers.CharField(min_length=5, write_only=True)

    class Meta:
        model = User
        fields = ["pin"]
        extra_kwargs = {"pin": {"write_only": True}}

    def validate_pin(self, value):
        if not value.isdigit() or len(value) != 5:
            raise serializers.ValidationError("Pin must be a 5-digit number.")
        return value
