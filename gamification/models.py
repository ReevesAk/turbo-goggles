import datetime
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
    ("social_engagement", "Social Engagement"),
    ("admin_adjustment", "Admin Adjustment"),
    ("penalty", "Penalty"),
    ("points_redemption", "Points Redemption"),
    # Brand campaign task types
    ("watch_video", "Watch Video"),
    ("website_visit", "Website Visit"),
    ("store_visit", "Store Visit"),
    ("survey_completion", "Survey Completion"),
    ("app_download", "App Download"),
    ("brand_task", "Brand Task"),
    # PicaPoints mission categories
    ("kyc_upgrade", "KYC Tier Upgrade"),
    ("wallet_funding", "Wallet Funding"),
    ("airtime_purchase", "Airtime Purchase"),
    ("data_purchase", "Data Purchase"),
    ("bills_payment", "Bills Payment"),
    ("marketplace_usage", "Marketplace Usage"),
    ("walk_to_earn", "Walk To Earn"),
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
        indexes = [
            models.Index(fields=["user", "source", "created_at"], name="pointtx_user_source_date_idx"),
        ]

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
    duration_minutes = models.PositiveIntegerField(default=0)
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

    @property
    def duration_display(self):
        parts = []
        if self.duration_days:
            parts.append(f"{self.duration_days} day{'s' if self.duration_days != 1 else ''}")
        if self.duration_minutes:
            parts.append(f"{self.duration_minutes} minute{'s' if self.duration_minutes != 1 else ''}")
        return " ".join(parts) if parts else "0 minutes"

    def __str__(self):
        return f"{self.name} ({self.streak_type}, {self.duration_days}d {self.duration_minutes}m)"

    @property
    def is_ongoing(self):
        today = timezone.now().date()
        start = self.start_date.date() if isinstance(self.start_date, datetime.datetime) else self.start_date
        end = self.end_date.date() if isinstance(self.end_date, datetime.datetime) else self.end_date
        return self.is_active and not self.is_paused and start <= today <= end

    @property
    def is_scheduled(self):
        today = timezone.now().date()
        start = self.start_date.date() if isinstance(self.start_date, datetime.datetime) else self.start_date
        return not self.is_cancelled and today < start

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

    @property
    def status(self):
        if timezone.now() >= self.campaign_end_time:
            return "expired"
        return "active"


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


class RewardRule(models.Model):
    """
    Admin-configurable rule for a PicaPoints mission category (e.g. airtime
    purchase, wallet funding, KYC upgrade). One rule per `source`; the actual
    point amounts live on child `RewardTier` rows so a single rule can pay out
    different points for different value bands (e.g. ₦500-999 vs ₦5000+).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source = models.CharField(max_length=30, choices=TRANSACTION_SOURCE_CHOICES, unique=True)
    label = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    # If True, this rule can only ever pay out once per user (e.g. KYC tier upgrade).
    one_time_only = models.BooleanField(default=False)
    # Ceilings enforced against the PointTransaction ledger for the current
    # calendar month. Leave both null for an uncapped rule.
    monthly_cap_points = models.PositiveIntegerField(null=True, blank=True)
    monthly_cap_count = models.PositiveIntegerField(null=True, blank=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="reward_rules_created"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.label} ({self.source})"


class RewardTier(models.Model):
    """
    A value band within a RewardRule, e.g. "min_value=500, max_value=999,
    points=5" for airtime purchases. `max_value` null means unbounded (the
    top tier, e.g. "₦5000+"). For non-monetary rules (KYC tier, streak week
    number) `min_value`/`max_value` hold the tier/week number instead of naira.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    rule = models.ForeignKey(RewardRule, on_delete=models.CASCADE, related_name="tiers")
    label = models.CharField(max_length=100, blank=True)
    min_value = models.DecimalField(max_digits=12, decimal_places=2)
    max_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    points = models.PositiveIntegerField()

    class Meta:
        ordering = ["min_value"]

    def __str__(self):
        upper = str(self.max_value) if self.max_value is not None else "+"
        return f"{self.rule.source}: {self.min_value}-{upper} → {self.points}pts"

    def matches(self, value: Decimal) -> bool:
        if value < self.min_value:
            return False
        if self.max_value is not None and value > self.max_value:
            return False
        return True
