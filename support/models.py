import uuid

from django.db import models
from django.utils import timezone
from basemodel import BaseModel

from accounts.models import User

ESCALATION_LEVEL = (
    ("Management", "Management"),
)

STATUS = (
    ("Resolved", "Resolved"),
    ("In-Progress", "In-Progress"),
    ("Queuing", "Queuing")
)


AGENT_RATING = (
    ("Awesome", "Awesome"),
    ("Okay", "Okay"),
    ("Terrible", "Terrible")
)


class Ticket(BaseModel):
    user = models.ForeignKey(to=User, on_delete=models.SET_NULL, null=True, related_name="user_tickets")
    title = models.CharField(max_length=150, null=True)
    assigned_to = models.ForeignKey(to=User, on_delete=models.SET_NULL, null=True, related_name="assigned_tickets")
    description = models.TextField(null=True)
    escalation_level = models.CharField(choices=ESCALATION_LEVEL, max_length=150, null=True)
    status = models.CharField(choices=STATUS, max_length=150, null=True)
    assigned_at = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if self.assigned_to and not self.assigned_at:
            self.assigned_at = timezone.now()
        super().save(*args, **kwargs)


class AgentRating(models.Model):
    user = models.ForeignKey(to=User, on_delete=models.SET_NULL, null=True, related_name="user_rating")
    agent = models.ForeignKey(to=User, on_delete=models.SET_NULL, null=True, related_name="agent_rated")
    ticket = models.UUIDField(default=uuid.uuid4, editable=False)
    rating = models.CharField(max_length=150, choices=AGENT_RATING, null=True)
    rating_comment = models.TextField(null=True, blank=True)
