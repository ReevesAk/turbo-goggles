# Third party imports.
from rest_framework import serializers

# In project imports.
from .models import (
    Ticket, AgentRating
)


class CreateTicketSerializers(serializers.ModelSerializer):
    email = serializers.CharField(max_length=68, min_length=6, write_only=True)

    class Meta:
        model = Ticket
        fields = [
            "id",
            "title",
            "email",
            "description",
        ]


class AssignTicketSerializers(serializers.ModelSerializer):
    agent_email = serializers.CharField(max_length=68, min_length=6, write_only=True)
    pin = serializers.CharField(max_length=5, min_length=6, write_only=True)
    ticket_id = serializers.CharField(max_length=68, min_length=6, write_only=True)

    class Meta:
        model = Ticket
        fields = [
            "pin",
            "ticket_id",
            "agent_email",
        ]


class AgentRatingSerializers(serializers.ModelSerializer):
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
