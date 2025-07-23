from django.db import models
from django.utils import timezone
from datetime import timedelta

import uuid

from accounts.models import User


# Create your models here.
class GamificationModel(models.Model):
    """
    Model for gamification management.
    """

    user = models.ForeignKey(to=User, on_delete=models.CASCADE)
    member_id = models.CharField(max_length=255, null=True)
    activity_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    assigned_to = models.CharField(max_length=150, null=True)
    pts = models.FloatField(null=True)
    is_done = models.BooleanField(default=False)
    date = models.DateTimeField(auto_now_add=True)
    task_url = models.CharField(max_length=250, null=True)
    remarks = models.CharField(max_length=255, null=True, blank=True)


class Points(models.Model):
    user = models.ForeignKey(to=User, on_delete=models.CASCADE)
    gamification = models.ForeignKey(to=GamificationModel, on_delete=models.CASCADE)
    balance = models.FloatField(null=True)


class StepCampaignModel(models.Model):
    campaign_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    name = models.CharField(max_length=255)
    duration = models.DurationField()
    description = models.TextField(blank=True, null=True)
    step_target = models.PositiveIntegerField()
    reward_points = models.PositiveIntegerField()
    time_limit = models.DurationField(null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="campaigns_created")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    @property
    def campaign_end_time(self):
        return self.created_at + self.duration

    @property
    def is_campaign_active(self):
        return timezone.now() < self.campaign_end_time


class StepSessionModel(models.Model):
    session_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    campaign = models.ForeignKey(StepCampaignModel, on_delete=models.CASCADE, related_name="sessions")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="step_sessions")
    session_date = models.DateField(default=timezone.now)
    step_count = models.PositiveIntegerField(default=0)
    completed = models.BooleanField(default=False)
    started_at = models.DateTimeField(null=True, blank=True)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'session_date', 'campaign')

    def __str__(self):
        return f"{self.user} | {self.campaign.name} | {self.session_date}"

    @property
    def total_steps(self):
        return StepSessionModel.objects.filter(
            user=self.user,
            campaign=self.campaign
        ).aggregate(models.Sum("step_count"))["step_count__sum"] or 0

    @property
    def personal_deadline(self):
        if self.started_at and self.time_limit:
            return self.started_at + self.time_limit
        return None

    @property
    def is_within_personal_time_limit(self):
        if self.personal_deadline:
            return timezone.now() <= self.personal_deadline
        return True  # If not set, default to always valid

    @property
    def can_still_accumulate(self):
        return self.campaign.is_campaign_active and self.is_within_personal_time_limit

    def check_completion(self):
        if not self.completed and self.total_steps >= self.campaign.step_target:
            self.completed = True
            self.save()
        return self.completed
