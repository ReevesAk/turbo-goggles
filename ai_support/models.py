import uuid
from django.db import models
from django.utils import timezone

from accounts.models import User
from support.models import Ticket


class AISupportSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="ai_support_sessions")
    ticket = models.OneToOneField(
        Ticket, null=True, blank=True, on_delete=models.SET_NULL, related_name="ai_session"
    )
    messages = models.JSONField(default=list)
    resolved_by_ai = models.BooleanField(default=False)
    escalated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Session {self.id} — {self.user}"

    @property
    def is_escalated(self):
        return self.escalated_at is not None

    def escalate(self, ticket):
        self.ticket = ticket
        self.escalated_at = timezone.now()
        self.save(update_fields=["ticket", "escalated_at", "updated_at"])
