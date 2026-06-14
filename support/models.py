from datetime import timedelta
from django.utils import timezone

from django.db import models
from basemodel import BaseModel

from accounts.models import User

PRIORITY = (
    ("Low", "Low"),
    ("Medium", "Medium"),
    ("High", "High"),
)

STATUS = (
    ("New", "New"),
    ("In-Progress", "In-Progress"),
    ("Awaiting Customer", "Awaiting Customer"),
    ("Escalated", "Escalated"),
    ("Resolved", "Resolved"),
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
    ("Social Media", "Social Media"),
)


class Ticket(BaseModel):
    number = models.CharField(max_length=50, unique=True, null=True)  # Prefixed unique number
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    opened_at = models.DateTimeField(null=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted = models.BooleanField(default=False)

    user = models.ForeignKey(
        to=User, on_delete=models.SET_NULL,
        null=True, related_name="user_tickets"
    )
    title = models.CharField(max_length=150, null=True)
    customer_name = models.CharField(max_length=254, null=True)
    customer_email = models.EmailField(max_length=254, null=True)
    customer_phone_number = models.CharField(max_length=20, null=True)
    category = models.CharField(max_length=150, null=True)
    resolution_hours = models.IntegerField(null=True, blank=True)
    channel = models.CharField(max_length=50, choices=TICKET_CHANNELS, null=True)
    assigned_to = models.ForeignKey(
        to=User, on_delete=models.SET_NULL,
        null=True, related_name="assigned_tickets"
    )
    agent_role = models.CharField(max_length=150, null=True)
    description = models.TextField(null=True)
    priority = models.CharField(choices=PRIORITY, max_length=150, null=True)
    status = models.CharField(choices=STATUS, max_length=150, null=True, blank=True)
    assigned_at = models.DateTimeField(null=True, blank=True)
    ticket_attachment = models.URLField(max_length=255, null=True, blank=True)
    resolution_attachment = models.URLField(max_length=255, null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        to=User, on_delete=models.SET_NULL,
        null=True, related_name="resolved_tickets"
    )

    @property
    def remaining_time(self):
        if not self.opened_at:
            return None

        deadline = self.opened_at + timedelta(hours=self.resolution_hours)
        return max(deadline - timezone.now(), timedelta(seconds=0))

    def save(self, *args, **kwargs):
        is_new = self.pk is None

        super().save(*args, **kwargs)

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
    action = models.CharField(max_length=50, null=True)  # e.g., "assign" or "reassign"
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class TicketRRTrail(BaseModel):
    """
    Tracks routing, escalation, and handover history (RR).
    """

    ACTIONS = (
        ("assign", "Assign"),
        ("reassign", "Reassign"),
        ("escalate", "Escalate"),
        ("resolve", "Resolve"),
        ("close", "Close"),
    )

    ticket = models.ForeignKey(
        Ticket,
        on_delete=models.CASCADE,
        related_name="rr_trail"
    )

    action = models.CharField(max_length=20, choices=ACTIONS)

    from_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="rr_from_user"
    )

    to_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="rr_to_user"
    )

    from_role = models.CharField(max_length=150, null=True, blank=True)
    to_role = models.CharField(max_length=150, null=True, blank=True)

    reason = models.CharField(max_length=255, null=True, blank=True)

    happened_at = models.DateTimeField(auto_now_add=True)


class AgentRating(models.Model):
    user = models.ForeignKey(
        to=User, on_delete=models.SET_NULL,
        null=True, related_name="user_rating"
    )
    agent = models.ForeignKey(
        to=User, on_delete=models.SET_NULL,
        null=True, related_name="agent_rated"
    )
    ticket = models.ForeignKey(
        to=Ticket,
        on_delete=models.CASCADE,
        related_name="ratings"
    )
    rating = models.CharField(max_length=150, choices=AGENT_RATING, null=True)
    rating_comment = models.TextField(null=True, blank=True)

    class Meta:
        unique_together = ("user", "ticket")
    