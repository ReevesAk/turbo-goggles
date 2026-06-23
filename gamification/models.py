from decimal import Decimal

from django.db import models
from django.utils import timezone

import uuid

from accounts.models import User


TIER_TO_RATE = {
    "Explorer": Decimal("0.50"),
    "Challenger": Decimal("1.00"),
    "Influencer": Decimal("1.50"),
    "Champion": Decimal("2.00"),
    "Elite": Decimal("2.50"),
    "Legend": Decimal("3.00"),
}


# Create your models here.
class GamificationModel(models.Model):
    """
    Model for gamification management.
    """

    user = models.ForeignKey(to=User, on_delete=models.CASCADE)
    member_id = models.CharField(max_length=255, null=True)
    activity_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    date = models.DateTimeField(auto_now_add=True)


class Points(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    balance = models.IntegerField(default=0)
    tier = models.CharField(max_length=20, default="Starter")
    naira_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    @property
    def redeemable(self):
        tier = getattr(self.user, "tier", None)
        rate = TIER_TO_RATE.get(tier, Decimal("0"))
        return int((self.balance or 0) * rate)


TRANSACTION_SOURCE_CHOICES = (
    ("task_completion", "Task Completion"),
    ("daily_login", "Daily Login"),
    ("referral", "Referral"),
    ("service_purchase", "Service Purchase"),
    ("financial_task", "Financial Task"),
    ("streak_bonus", "Streak Bonus"),
    ("special_campaign", "Special Campaign"),
    ("admin_adjustment", "Admin Adjustment"),
    ("penalty", "Penalty"),
    # Brand campaign task types
    ("watch_video", "Watch Video"),
    ("website_visit", "Website Visit"),
    ("store_visit", "Store Visit"),
    ("survey_completion", "Survey Completion"),
    ("app_download", "App Download"),
    ("brand_task", "Brand Task"),
)


class PointTransaction(models.Model):
    """Immutable ledger entry for every points movement."""

    AWARD = "award"
    DEDUCT = "deduct"
    TRANSACTION_TYPES = ((AWARD, "Award"), (DEDUCT, "Deduction"))

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="point_transactions")
    transaction_type = models.CharField(choices=TRANSACTION_TYPES, max_length=10)
    amount = models.PositiveIntegerField()
    reason = models.CharField(max_length=255)
    source = models.CharField(choices=TRANSACTION_SOURCE_CHOICES, max_length=30, default="admin_adjustment")
    reference_id = models.CharField(max_length=100, blank=True, null=True)
    triggered_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="triggered_transactions"
    )
    balance_after = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.transaction_type} {self.amount}pts → {self.user} [{self.source}]"


STREAK_TYPE_CHOICES = (
    ("daily_login", "Daily Login"),
    ("service_purchase", "Service Purchase"),
    ("financial_task", "Financial Task"),
    ("social_engagement", "Social Engagement"),
    ("referral", "Referral"),
    ("special_campaign", "Special Campaign"),
    ("watch_video", "Watch Video"),
    ("website_visit", "Website Visit"),
    ("store_visit", "Store Visit"),
    ("survey_completion", "Survey Completion"),
    ("app_download", "App Download"),
    ("brand_task", "Brand Task"),
)

SCHEDULE_TYPE_CHOICES = (
    ("once", "Once"),
    ("weekly", "Weekly"),
    ("monthly", "Monthly"),
    ("every_three_months", "Every Three Months"),
    ("every_six_months", "Every Six Months"),
    ("yearly", "Yearly"),
)


class PointConfig(models.Model):
    key = models.CharField(max_length=50, unique=True)
    label = models.CharField(max_length=100)
    value = models.PositiveIntegerField()
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="point_configs_updated"
    )

    def __str__(self):
        return f"{self.label}: {self.value} pts"


class StreakChallenge(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    streak_type = models.CharField(max_length=50, choices=STREAK_TYPE_CHOICES)
    duration_days = models.PositiveIntegerField()
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    reward_points = models.PositiveIntegerField()
    reminder_time = models.TimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    is_paused = models.BooleanField(default=False)
    is_cancelled = models.BooleanField(default=False)
    # Scheduling
    schedule_type = models.CharField(
        max_length=20, choices=SCHEDULE_TYPE_CHOICES, null=True, blank=True
    )
    scheduled_start_time = models.TimeField(null=True, blank=True)
    # Participant cap (e.g. "600k participant" shown on task cards)
    participant_cap = models.PositiveIntegerField(null=True, blank=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="streak_challenges_created"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.streak_type}, {self.duration_days}d)"

    @property
    def is_ongoing(self):
        now = timezone.now()
        return self.is_active and not self.is_paused and self.start_date <= now <= self.end_date

    @property
    def is_scheduled(self):
        return not self.is_cancelled and timezone.now() < self.start_date

    @property
    def task_status(self):
        if self.is_cancelled:
            return "cancelled"
        if self.is_ongoing:
            return "active"
        return "inactive"


class UserStreak(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="streaks")
    challenge = models.ForeignKey(StreakChallenge, on_delete=models.CASCADE, related_name="user_streaks")
    current_count = models.PositiveIntegerField(default=0)
    longest_count = models.PositiveIntegerField(default=0)
    last_activity_date = models.DateField(null=True, blank=True)
    completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    reward_issued = models.BooleanField(default=False)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "challenge")

    def __str__(self):
        return f"{self.user} | {self.challenge.name} | {self.current_count}/{self.challenge.duration_days}"


class StreakHistory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="streak_histories")
    challenge = models.ForeignKey(StreakChallenge, on_delete=models.CASCADE, related_name="streak_histories")
    streak_count_reached = models.PositiveIntegerField()
    broken_at = models.DateField(null=True, blank=True)
    completed = models.BooleanField(default=False)
    reward_issued = models.BooleanField(default=False)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-recorded_at"]

    def __str__(self):
        status = "completed" if self.completed else f"broken at {self.broken_at}"
        return f"{self.user} | {self.challenge.name} | {self.streak_count_reached}d ({status})"


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


def get_current_date():
    return timezone.now().date()


class StepSessionModel(models.Model):
    session_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    campaign = models.ForeignKey(StepCampaignModel, on_delete=models.CASCADE, related_name="sessions")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="step_sessions")
    session_date = models.DateField(default=get_current_date)
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
        if self.started_at and self.campaign.time_limit:
            return self.started_at + self.campaign.time_limit
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
