# Third party imports.
from rest_framework import serializers

# In project imports.
from .models import (
    Ticket, AgentRating
)
from accounts.models import User


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
