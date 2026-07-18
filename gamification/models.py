import datetime
import uuid
from decimal import Decimal

from django.db import models
from django.utils import timezone


from accounts.models import User
from django.utils.translation import gettext_lazy as _
from adverts.pricing import compute_cost_per_engagement

# Kept in sync with TIER_VALUES/MIN_POINTS_REQUIRED in gamification/points.py
# by hand - points.py imports from this module, so it can't be imported back.
TIER_TO_RATE = {
    "Explorer": Decimal("0.40"),
    "Challenger": Decimal("0.70"),
    "Influencer": Decimal("1.00"),
    "Champion": Decimal("1.30"),
    "Elite": Decimal("1.60"),
    "Legend": Decimal("2.00"),
}
MIN_POINTS_REQUIRED = 700


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
        """Available balance, once it meets the minimum needed to redeem to
        wallet - the full balance, not capped at the minimum."""
        if self.tier == "Starter" or self.balance < MIN_POINTS_REQUIRED:
            return 0
        return self.balance


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
    ("make_video", "Make a video"),
    ("take_picture", "Take a picture"),
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

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="point_transactions"
    )
    transaction_type = models.CharField(choices=TRANSACTION_TYPES, max_length=10)
    amount = models.PositiveIntegerField()
    reason = models.CharField(max_length=255)
    source = models.CharField(
        choices=TRANSACTION_SOURCE_CHOICES, max_length=30, default="admin_adjustment"
    )
    reference_id = models.CharField(max_length=100, blank=True, null=True)
    triggered_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="triggered_transactions",
    )
    balance_after = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["user", "source", "created_at"],
                name="pointtx_user_source_date_idx",
            ),
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
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="point_configs_updated",
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
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="streak_challenges_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def duration_display(self):
        parts = []
        if self.duration_days:
            parts.append(
                f"{self.duration_days} day{'s' if self.duration_days != 1 else ''}"
            )
        if self.duration_minutes:
            parts.append(
                f"{self.duration_minutes} minute{'s' if self.duration_minutes != 1 else ''}"
            )
        return " ".join(parts) if parts else "0 minutes"

    def __str__(self):
        return f"{self.name} ({self.streak_type}, {self.duration_days}d {self.duration_minutes}m)"

    @property
    def is_ongoing(self):
        today = timezone.now().date()
        start = (
            self.start_date.date()
            if isinstance(self.start_date, datetime.datetime)
            else self.start_date
        )
        end = (
            self.end_date.date()
            if isinstance(self.end_date, datetime.datetime)
            else self.end_date
        )
        return self.is_active and not self.is_paused and start <= today <= end

    @property
    def is_scheduled(self):
        today = timezone.now().date()
        start = (
            self.start_date.date()
            if isinstance(self.start_date, datetime.datetime)
            else self.start_date
        )
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
    challenge = models.ForeignKey(
        StreakChallenge, on_delete=models.CASCADE, related_name="user_streaks"
    )
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
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="streak_histories"
    )
    challenge = models.ForeignKey(
        StreakChallenge, on_delete=models.CASCADE, related_name="streak_histories"
    )
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
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="campaigns_created"
    )
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
    campaign = models.ForeignKey(
        StepCampaignModel, on_delete=models.CASCADE, related_name="sessions"
    )
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="step_sessions"
    )
    session_date = models.DateField(default=get_current_date)
    step_count = models.PositiveIntegerField(default=0)
    completed = models.BooleanField(default=False)
    started_at = models.DateTimeField(null=True, blank=True)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "session_date", "campaign")

    def __str__(self):
        return f"{self.user} | {self.campaign.name} | {self.session_date}"

    @property
    def total_steps(self):
        return (
            StepSessionModel.objects.filter(
                user=self.user, campaign=self.campaign
            ).aggregate(models.Sum("step_count"))["step_count__sum"]
            or 0
        )

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
    source = models.CharField(
        max_length=30, choices=TRANSACTION_SOURCE_CHOICES, unique=True
    )
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
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reward_rules_created",
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
    max_value = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
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


class UserGeneratedContent(models.Model):
    """
    Model representing user-generated content tasks.

    This model handles all aspects of UGC tasks including task creation,
    demographic targeting, location restrictions, financial management,
    and engagement tracking.
    """

    class Gender(models.TextChoices):
        """
        Gender options for task targeting.
        """

        MALE = "male", _("Male")
        FEMALE = "female", _("Female")
        ALL = "all", _("All")

    class BusinessType(models.TextChoices):
        """
        Business type options for task creation.
        """

        ONLINE = "online", _("Online")
        PHYSICAL = "physical", _("Physical")
        HYBRID = "hybrid", _("Hybrid")

    class LocationPerimeter(models.TextChoices):
        """
        Geographic targeting levels for tasks.
        """

        NATION_WIDE = "nation_wide", _("Nation Wide")
        STATE = "state", _("State")
        CITIES = "cities", _("Cities")

    class Demography(models.TextChoices):
        """
        Age demographic targeting options.
        """

        AGE_18_25 = "18 - 25", _("18 - 25")
        AGE_26_35 = "26 - 35", _("26 - 35")
        AGE_36_45 = "36 - 45", _("36 - 45")
        AGE_46_PLUS = "46+", _("46+")

    class TaskType(models.TextChoices):
        """
        Task type options.
        """

        MAKE_A_VIDEO = "make_a_video", _("Make a video")
        TAKE_A_PICTURE = "take_a_picture", _("Take a picture")

    # Primary Key
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Unique identifier for the task",
    )

    # User and Business Information
    user = models.ForeignKey(
        to=User, on_delete=models.CASCADE, related_name="create_ugc"
    )
    business_or_brand_name = models.CharField(max_length=255, null=True)
    type_of_business = models.CharField(
        choices=BusinessType.choices, max_length=155, null=True
    )

    # Task Details
    task_name = models.CharField(
        max_length=255, help_text="Name/title of the user-generated content task"
    )
    task_type = models.CharField(
        max_length=255,
        choices=TaskType.choices,
        help_text="Type of the user-generated content task",
    )
    description = models.CharField(
        max_length=1000, help_text="Detailed description of the task requirements"
    )
    unique_identifiers = models.JSONField(
        default=list,
        null=True,
        blank=True,
        help_text="List of unique identifiers or keywords for the task",
    )
    use_brand_slogan = models.BooleanField(
        default=False, help_text="Whether to use a brand slogan in the content"
    )
    brand_slogan = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Brand slogan to be used if use_brand_slogan is True",
    )

    # Media
    thumbnail_url = models.URLField(
        max_length=500, help_text="URL to the task thumbnail image or video"
    )
    sample_url = models.URLField(
        max_length=500, help_text="URL to the task sample image or video"
    )

    # Slot Management
    slot_cap = models.PositiveIntegerField(
        default=0, help_text="Maximum number of slots available for this task"
    )
    slots_filled = models.PositiveIntegerField(
        default=0, help_text="Number of slots already filled"
    )
    unlimited_slots = models.BooleanField(
        default=False, help_text="Whether the task has unlimited slots"
    )
    reward_points = models.PositiveIntegerField(
        default=0,
        null=True,
        blank=True,
        help_text="Reward points for completing the task",
    )
    auto_boost = models.BooleanField(default=False)
    auto_boost_points = models.PositiveIntegerField(
        default=0, help_text="Automatic boost points for increased visibility"
    )

    # Financial Details
    amount = models.CharField(
        max_length=155,
        null=True,
        blank=True,
        help_text="Monetary amount associated with the task (string representation)",
    )
    ads_credit = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text=("Credit swept from this task's unused slots when it expired. "),
    )
    credit_settled = models.BooleanField(
        default=False, help_text="Whether the credits have been settled"
    )

    # Demographics
    gender = models.CharField(
        max_length=20,
        choices=Gender.choices,
        default=Gender.ALL,
        help_text="Target gender demographic",
    )
    demography = models.CharField(
        max_length=150,
        choices=Demography.choices,
        blank=True,
        null=True,
        help_text="Target age demographic",
    )

    # Location and Targeting
    location_perimeter = models.CharField(
        max_length=20,
        choices=LocationPerimeter.choices,
        default=LocationPerimeter.NATION_WIDE,
        help_text="Geographic coverage level for the task",
    )
    targeting_type = models.CharField(
        max_length=15,
        default="broad",
        help_text="Determines the pricing multiplier: broad/city/niche/influencer",
    )
    countries = models.JSONField(
        default=list, null=True, blank=True, help_text="List of targeted countries"
    )
    states = models.JSONField(
        default=list,
        null=True,
        blank=True,
        help_text="List of targeted states (used when location_perimeter is STATE)",
    )
    cities = models.JSONField(
        default=list,
        null=True,
        blank=True,
        help_text="List of targeted cities (used when location_perimeter is CITIES)",
    )

    # Task Scheduling and Duration
    task_duration = models.DurationField(
        null=True, blank=True, help_text="Estimated duration to complete a single task"
    )
    campaign_duration = models.DurationField(
        null=True, blank=True, help_text="Overall campaign duration"
    )

    # Status
    is_active = models.BooleanField(
        default=True,
        help_text=("Whether the task is currently active/visible."),
    )

    # Timestamps
    expiry_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text=(
            "Stored campaign end time (created/derived at save-time from campaign_duration)."
        ),
    )
    created_at = models.DateTimeField(
        auto_now_add=True, help_text="Timestamp when the task was created"
    )
    updated_at = models.DateTimeField(
        auto_now=True, help_text="Timestamp when the task was last updated"
    )

    class Meta:
        """
        Model metadata configuration.
        """

        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["task_name"]),
            models.Index(fields=["gender", "demography"]),
            models.Index(fields=["is_active", "created_at"]),
        ]
        verbose_name = _("User Generated Content")
        verbose_name_plural = _("User Generated Content Items")
        get_latest_by = "created_at"

    def __str__(self) -> str:
        """
        Human-readable representation of the model instance.

        Returns:
            str: The task name
        """
        return self.task_name

    def save(self, *args, **kwargs) -> None:
        """
        Custom save method to ensure data consistency and trigger any
        necessary business logic before saving.
        """

        if self.campaign_duration and not self.expiry_date:
            self.expiry_date = timezone.now() + self.campaign_duration

        super().save(*args, **kwargs)

    @property
    def unused_credit(self) -> Decimal:
        """
        Calculate the unused credit amount for this task.

        Returns:
            Decimal: The unused credit amount

        Example:
            >>> task.slot_cap = 100
            >>> task.slots_filled = 30
            >>> task.amount = "1000.00"
            >>> task.unused_credit
            Decimal('700.00')
        """
        # Get slot capacity
        slot_cap = self.slot_cap or 0

        # If no capacity or no amount, return 0
        if slot_cap <= 0:
            return Decimal("0")

        # Calculate unused slots
        unused_slots = max(0, slot_cap - (self.slots_filled or 0))

        # Parse amount safely
        try:
            amount = Decimal(str(self.amount or "0"))
        except Exception:
            return Decimal("0")

        # If amount is zero or negative, return 0
        if amount <= 0:
            return Decimal("0")

        # Calculate unused credit proportionally
        return (Decimal(str(unused_slots)) / Decimal(str(slot_cap))) * amount

    @property
    def cost_per_engagement(self) -> Decimal:
        """
        Calculate the cost per engagement for this task.

        This calculation uses external helper functions to determine the
        cost based on task type, duration, and targeting type.

        Returns:
            Decimal: Cost per engagement, returns 0.00 if calculation fails

        Note:
            This property requires the following external functions:
            - compute_cost_per_engagement(task_type, duration, targeting_type)
        """
        # Calculate campaign duration in seconds or days
        if self.campaign_duration:
            duration = self.campaign_duration.total_seconds() / 86400
        else:
            duration = 0

        # Validate task_type exists and duration is positive
        if self.task_type and duration > 0:
            try:
                return compute_cost_per_engagement(
                    self.task_type, duration, self.targeting_type or "broad"
                )
            except (AttributeError, TypeError, ValueError):
                return Decimal("0")

        return Decimal("0")

    @property
    def available_slots(self) -> int:
        """
        Get the number of available slots for this task.

        Returns:
            int: Number of available slots

        Example:
            >>> task.slot_cap = 100
            >>> task.slots_filled = 30
            >>> task.available_slots
            70
        """
        if self.unlimited_slots:
            return None
        return max(0, (self.slot_cap or 0) - (self.slots_filled or 0))

    @property
    def is_fully_booked(self) -> bool:
        """
        Check if the task has no available slots.

        Returns:
            bool: True if all slots are filled, False otherwise
        """
        if self.unlimited_slots:
            return False
        return self.available_slots <= 0

    @property
    def is_expired(self) -> bool:
        """Whether the campaign window has elapsed."""
        expiry = self.expiry_date
        return bool(expiry and timezone.now() >= expiry)

    @property
    def is_finished(self) -> bool:
        """
        True if the task is done: slots exhausted, campaign expired, or
        manually deactivated.
        """
        return self.is_fully_booked or self.is_expired or not self.is_active
