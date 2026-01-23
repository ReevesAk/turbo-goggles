import uuid

from django.db import models
from basemodel import BaseModel

from accounts.models import User

PRIORITY = (
    ("Low", "Low"),
    ("Medium", "Medium"),
    ("High", "High"),
)

STATUS = (
    ("Queuing", "Queuing"),
    ("Closed", "Closed"),
    ("In-Progress", "In-Progress"),
    ("Unopened", "Unopened"),
    ("Reassigned", "Reassigned"),
    ("Overdue", "Overdue"),
    ("Closed", "Closed")
)

AGENT_RATING = (
    ("Awesome", "Awesome"),
    ("Okay", "Okay"),
    ("Terrible", "Terrible")
)

TICKET_CHANNELS = (
    ("App", "App"),
    ("Email", "Email"),
    ("Call", "Call"),
    ("Website", "Website"),
)


class Ticket(BaseModel):
    number = models.CharField(max_length=20, unique=True, null=True)  # Prefixed unique number
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted = models.BooleanField(default=False)

    user = models.ForeignKey(
        to=User, on_delete=models.SET_NULL,
        null=True, related_name="user_tickets"
    )
    title = models.CharField(max_length=150, null=True)
    customer_name = models.CharField(max_length=254, null=True)
    customer_email = models.EmailField(max_length=254, null=True)
    category = models.CharField(max_length=150, null=True)
    channel = models.CharField(max_length=50, choices=TICKET_CHANNELS, null=True)
    assigned_to = models.ForeignKey(
        to=User, on_delete=models.SET_NULL,
        null=True, related_name="assigned_tickets"
    )
    description = models.TextField(null=True)
    priority = models.CharField(choices=PRIORITY, max_length=150, null=True)
    status = models.CharField(choices=STATUS, max_length=150, null=True, blank=True)
    assigned_at = models.DateTimeField(null=True, blank=True)
    attachments = models.URLField(max_length=255, null=True, blank=True)

    def save(self, *args, **kwargs):
        is_new = self.pk is None  # Check if this is a new object

        super().save(*args, **kwargs)  # Save once to get `id`

        # Only generate number after the first save
        if is_new and not self.number:
            self.number = f"TCK{self.id:04d}"
            # Save again without triggering another number generation
            kwargs['force_insert'] = False
            super().save(update_fields=["number"])


class TicketAssignmentHistory(models.Model):
    ticket = models.ForeignKey(
        Ticket,
        on_delete=models.CASCADE,
        related_name="assignment_history"
    )
    assigned_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="tickets_assigned"
    )
    previous_agent = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="previous_ticket_assignments"
    )
    new_agent = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="new_ticket_assignments"
    )
    priority = models.CharField(max_length=20, null=True)
    reason = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class AgentRating(models.Model):
    user = models.ForeignKey(to=User, on_delete=models.SET_NULL, null=True, related_name="user_rating")
    agent = models.ForeignKey(to=User, on_delete=models.SET_NULL, null=True, related_name="agent_rated")
    ticket = models.UUIDField(default=uuid.uuid4, editable=False)
    rating = models.CharField(max_length=150, choices=AGENT_RATING, null=True)
    rating_comment = models.TextField(null=True, blank=True)
