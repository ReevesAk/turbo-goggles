from rest_framework import serializers

from .models import AISupportSession


class ChatMessageSerializer(serializers.Serializer):
    session_id = serializers.UUIDField(required=False, allow_null=True)
    message = serializers.CharField(max_length=2000)


class ChatResponseSerializer(serializers.Serializer):
    session_id = serializers.UUIDField()
    reply = serializers.CharField()
    escalated = serializers.BooleanField()
    ticket_number = serializers.CharField(allow_null=True)


class SessionHistorySerializer(serializers.ModelSerializer):
    is_escalated = serializers.BooleanField(read_only=True)
    ticket_number = serializers.SerializerMethodField()

    class Meta:
        model = AISupportSession
        fields = [
            "id",
            "messages",
            "is_escalated",
            "ticket_number",
            "created_at",
            "updated_at",
        ]

    def get_ticket_number(self, obj):
        return obj.ticket.number if obj.ticket else None
