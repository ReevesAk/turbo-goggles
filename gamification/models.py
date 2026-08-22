import datetime
import uuid
from decimal import Decimal

from django.db import models
from django.utils import timezone
from django.db.models import F


from accounts.models import User
from django.utils.translation import gettext_lazy as _
from adverts.pricing import compute_cost_per_engagement
from user_profile.choices import LEVELS

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

# Structured sub-categorization for streak_type="financial_task" in-app tasks,
# so the mobile client can deep-link into the right screen instead of parsing
# free-text description. Only meaningful when streak_type="financial_task" —
# enforced in InAppTaskCreateSerializer/InAppTaskUpdateSerializer, not here.
MISSION_CATEGORY_CHOICES = (
    ("kyc_upgrade", "KYC Tier Upgrade"),
    ("wallet_funding", "Wallet Funding"),
    ("vas", "Airtime/Data (VAS)"),
    ("bills_payment", "Bills Payment"),
    ("transfer", "Transfer"),
    ("referral_task", "Referral Task"),
    ("streak_task", "Streak Task"),
)

VAS_CATEGORY_CHOICES = (
    ("airtime", "Airtime"),
    ("data", "Data"),
    ("cable_tv", "Cable TV"),
    ("electricity", "Electricity"),
    ("internet", "Internet"),
    ("education", "Education"),
    ("event_tickets", "Event Tickets"),
    ("gift_cards", "Gift Cards"),
)

ACTION_TYPE_CHOICES = (
    ("count_based", "Count Based"),
    ("amount_based", "Amount Based"),
    ("one_time", "One Time"),
    # Same semantics as count_based (required_count times within the
    # challenge window) - a distinct value so the client/admin UI can label
    # it "streak" for mission_category="streak_task" without it being
    # confused with a generic count-based mission. See
    # _validate_financial_task_fields and InAppTaskFeedSerializer._get_progress
    # for the two places that treat it identically to count_based.
    ("streak", "Streak"),
)

RECURRENCE_PERIOD_CHOICES = (
    ("weekly", "Weekly"),
    ("monthly", "Monthly"),
)

SCHEDULE_TYPE_CHOICES = (
    ("once", "Once"),
    ("weekly", "Weekly"),
    ("monthly", "Monthly"),
    ("every_three_months", "Every Three Months"),
    ("every_six_months", "Every Six Months"),
    ("yearly", "Yearly"),
)

# Push-notification targeting choices, shared across the task/campaign models
# below. Values match UserGeneratedContent.Gender/Demography further down
# this file, and MemberSurvey.sex/age_bracket (user_profile/models.py) once
# normalized — see gamification/eligibility.py.
TARGET_GENDER_CHOICES = (
    ("male", "Male"),
    ("female", "Female"),
    ("all", "All"),
)

TARGET_AGE_BRACKET_CHOICES = (
    ("18 - 25", "18 - 25"),
    ("26 - 35", "26 - 35"),
    ("36 - 45", "36 - 45"),
    ("46+", "46+"),
)

# Tier order for "notify at or above this tier" targeting - derived from the
# canonical user_profile.choices.LEVELS list (also used by accounts.models.User
# .update_level and gamification/points.py's TIER_VALUES, kept in sync by hand).
TARGET_TIER_CHOICES = tuple((lvl["title"], lvl["title"]) for lvl in LEVELS)


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
    # Push-notification targeting (optional). Blank means notify every
    # has_done_survey member, same as today.
    target_min_tier = models.CharField(
        max_length=20,
        choices=TARGET_TIER_CHOICES,
        null=True,
        blank=True,
        help_text="Only notify members at or above this engagement tier.",
    )
    target_state = models.CharField(
        max_length=155,
        null=True,
        blank=True,
        help_text="Only notify members in this state (mainly relevant for website_visit/store_visit streak types).",
    )
    # Structured sub-category fields — only meaningful when streak_type=
    # "financial_task". Give the mobile app enough to deep-link into the
    # right screen and render a target/progress, instead of parsing
    # free-text description.
    mission_category = models.CharField(
        max_length=20, choices=MISSION_CATEGORY_CHOICES, null=True, blank=True
    )
    vas_category = models.CharField(
        max_length=20,
        choices=VAS_CATEGORY_CHOICES,
        null=True,
        blank=True,
        help_text="Only set when mission_category is 'vas' or 'bills_payment'.",
    )
    action_type = models.CharField(
        max_length=20, choices=ACTION_TYPE_CHOICES, null=True, blank=True
    )
    required_count = models.PositiveIntegerField(
        null=True, blank=True, help_text="Used when action_type='count_based'."
    )
    min_amount_per_action = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    total_min_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Used when action_type='amount_based'.",
    )
    monthly_cap_points = models.PositiveIntegerField(null=True, blank=True)
    is_recurring = models.BooleanField(default=False)
    recurrence_period = models.CharField(
        max_length=10, choices=RECURRENCE_PERIOD_CHOICES, null=True, blank=True
    )
    kyc_target_tier = models.PositiveIntegerField(
        null=True, blank=True, help_text="Used when mission_category='kyc_upgrade'."
    )
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
    def days_remaining(self):
        remaining = self.end_date - timezone.now()
        return max(0, remaining.days)

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
    # Push-notification targeting (optional). Blank means notify every
    # has_done_survey member, same as today.
    target_gender = models.CharField(
        max_length=10,
        choices=TARGET_GENDER_CHOICES,
        null=True,
        blank=True,
        help_text="Only notify members of this gender.",
    )
    target_age_bracket = models.CharField(
        max_length=20,
        choices=TARGET_AGE_BRACKET_CHOICES,
        null=True,
        blank=True,
        help_text="Only notify members in this age bracket.",
    )

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
    # Push-notification targeting (optional) for the "new mission available"
    # announcement sent when this rule is created. Blank means notify every
    # has_done_survey member. For source="kyc_upgrade" the eligibility check
    # additionally excludes already-verified members automatically, on top of
    # whatever's set here - see gamification/eligibility.py.
    target_min_tier = models.CharField(
        max_length=20,
        choices=TARGET_TIER_CHOICES,
        null=True,
        blank=True,
        help_text="Only notify members at or above this engagement tier.",
    )
    target_state = models.CharField(
        max_length=155,
        null=True,
        blank=True,
        help_text="Only notify members in this state.",
    )

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


class Referral(models.Model):
    """
    Append-only ledger row for a single successful referral event, created
    once when a new user registers with another user's referral_code or
    walk_to_earn_referral_code.
    """

    REFERRAL_TYPE_CHOICES = (
        ("gamification", "Gamification"),
        ("walk_to_earn", "Walk To Earn"),
    )

    referrer = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="referrals_made"
    )
    referred = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="referred_by"
    )
    referral_code_used = models.CharField(max_length=50)
    # Which code was used - determines which counter got incremented:
    # "gamification" -> referrer.referral_count (drives ReferralTask
    # mode="gamification" and StreakChallenge referral_task progress).
    # "walk_to_earn" -> referrer.walk_to_earn_referral_count (drives ONLY
    # the walk_to_earn_gate check) - these two counters are intentionally
    # separate, see Referrals.record_referral/record_walk_to_earn_referral.
    referral_type = models.CharField(
        max_length=20, choices=REFERRAL_TYPE_CHOICES, default="gamification"
    )
    # False if the referrer failed Points.check_credibility() at record time —
    # the referral is still logged, but the relevant counter was not
    # incremented and no progress was advanced.
    counted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["referrer", "created_at"], name="referral_referrer_date_idx"
            ),
        ]

    def __str__(self):
        return f"{self.referrer.email} referred {self.referred.email}"


class ReferralTask(models.Model):
    """
    Admin-configured referral task. Two modes, both driven by the referrer's
    cumulative accounts.User.referral_count:
      - "gamification": referrer earns reward_points on hitting target_referral_count.
      - "walk_to_earn_gate": a global prerequisite — members need
        target_referral_count referrals before JoinCampaignView lets them in.
        Only one walk_to_earn_gate task is ever effectively active at a time;
        activating a new one auto-deactivates the previous (see save()).
    """

    MODE_CHOICES = (
        ("gamification", "Gamification"),
        ("walk_to_earn_gate", "Walk To Earn Gate"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    mode = models.CharField(max_length=20, choices=MODE_CHOICES)
    target_referral_count = models.PositiveIntegerField()
    # Ignored/must be 0 for walk_to_earn_gate mode — see ReferralTaskCreateSerializer.
    reward_points = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    is_paused = models.BooleanField(default=False)
    is_cancelled = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="referral_tasks_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # Push-notification targeting (optional). Only used for mode="gamification"
    # - a walk_to_earn_gate task is a silent prerequisite, not an announcement,
    # so no push is ever sent for it regardless of these fields.
    target_min_tier = models.CharField(
        max_length=20,
        choices=TARGET_TIER_CHOICES,
        null=True,
        blank=True,
        help_text="Only notify members at or above this engagement tier.",
    )
    target_state = models.CharField(
        max_length=155,
        null=True,
        blank=True,
        help_text="Only notify members in this state.",
    )

    class Meta:
        indexes = [
            models.Index(
                fields=["mode", "is_active"], name="referraltask_mode_active_idx"
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.mode}, target={self.target_referral_count})"

    @property
    def task_status(self):
        if self.is_cancelled:
            return "cancelled"
        if self.is_active and not self.is_paused:
            return "active"
        return "inactive"

    @property
    def is_effectively_active(self):
        return self.is_active and not self.is_paused and not self.is_cancelled

    def save(self, *args, **kwargs):
        becomes_active_gate = (
            self.mode == "walk_to_earn_gate" and self.is_effectively_active
        )
        super().save(*args, **kwargs)
        if becomes_active_gate:
            ReferralTask.objects.filter(
                mode="walk_to_earn_gate", is_active=True
            ).exclude(pk=self.pk).update(is_active=False)


class UserReferralTaskProgress(models.Model):
    """
    Per-user progress on a "gamification"-mode ReferralTask. Rows are created
    lazily the moment a referrer's count first meets the task's target —
    there's no explicit "join" step for this task type. walk_to_earn_gate
    tasks never get progress rows; gate checks are a live count comparison.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="referral_task_progress"
    )
    task = models.ForeignKey(
        ReferralTask, on_delete=models.CASCADE, related_name="user_progress"
    )
    referral_count_at_completion = models.PositiveIntegerField(null=True, blank=True)
    completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    reward_issued = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "task")

    def __str__(self):
        return f"{self.user.email} | {self.task.name} | completed={self.completed}"


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
        max_length=1000,
        blank=True,
        default="",
        help_text="Detailed description of the task requirements",
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
        max_length=500,
        blank=True,
        default="",
        help_text="URL to the task thumbnail image or video",
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
        # Local import: commons.py imports gamification.models at module
        # load time, so importing commons here at module level would be
        # circular.
        from commons import is_slot_target_reached

        return is_slot_target_reached(self.slot_cap, self.slots_filled)

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


# ========================================
# User-Generated Content Submission Models
# ========================================


class UGCTaskSubmission(models.Model):
    """
    Represents a user's submission for a UGC task.
    Submissions start as PENDING and are approved or rejected by an admin
    review action - points are only awarded on approval.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="ugc_submissions"
    )
    task = models.ForeignKey(
        UserGeneratedContent, on_delete=models.CASCADE, related_name="submissions"
    )

    # Single media URL (only one file per submission)
    media_url = models.URLField(
        max_length=500, help_text="URL of the submitted image or video"
    )
    caption = models.TextField(
        blank=True, help_text="Optional caption for the submission"
    )

    # Status tracking - auto-approved or rejected
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    rejection_reason = models.CharField(
        max_length=255, blank=True, help_text="Reason for rejection"
    )

    # Timestamps
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    # Points tracking
    points_awarded = models.PositiveIntegerField(default=0)
    points_reason = models.CharField(max_length=255, blank=True)

    # Metadata
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ["-submitted_at"]

        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["task", "status"]),
            models.Index(fields=["-submitted_at"]),
        ]

    def __str__(self):
        return f"{self.user.email} - {self.task.task_name} ({self.status})"

    @classmethod
    def submit(cls, user, task, media_url, caption="", ip_address=None):
        """
        Create a submission in PENDING status. No points are awarded and no
        notification is sent here - that only happens once a reviewer calls
        approve() on the submission.
        Returns (submission, success, message)
        """
        # Validate task is active
        if not task.is_active:
            return None, False, "Task is no longer active"

        if task.is_fully_booked:
            return None, False, "Task has reached its slot limit"

        if task.is_expired:
            return None, False, "Task has expired"

        # Check for duplicate submission (pending or approved only)
        if cls.objects.filter(
            user=user, task=task, status__in=["pending", "approved"]
        ).exists():
            return None, False, "You have already submitted this task"

        # Use atomic transaction with select_for_update
        from django.db import transaction

        with transaction.atomic():
            # Lock the task row to prevent race conditions
            task = UserGeneratedContent.objects.select_for_update().get(id=task.id)

            # Re-check slot availability under lock
            if task.is_fully_booked:
                return None, False, "Task has reached its slot limit"

            # Create submission
            submission = cls.objects.create(
                user=user,
                task=task,
                media_url=media_url,
                caption=caption,
                status=cls.Status.PENDING,
                ip_address=ip_address,
            )

            progress, _ = UGCTaskProgress.objects.select_for_update().get_or_create(
                user=user
            )
            progress.record_submission(submission)

        return submission, True, "Submission received and pending review"

    def approve(self):
        """
        Approve a pending submission and award points.
        Guards against double-award if the submission is already approved.
        Returns (success, message)
        """
        if self.status == self.Status.APPROVED:
            return False, "Submission already approved"

        from django.db import transaction

        from gamification.points import Points

        with transaction.atomic():
            task = UserGeneratedContent.objects.select_for_update().get(id=self.task_id)
            progress, _ = UGCTaskProgress.objects.select_for_update().get_or_create(
                user=self.user
            )

            # Get UGC level from progress
            ugc_level = Points.get_ugc_level(progress.approved_submissions)

            # Use UGC level multiplier, fallback to generic level
            level_multiplier = Points.get_level_multiplier(ugc_level)
            final_points = int((task.reward_points or 0) * level_multiplier)

            success, message = Points.award(
                user=self.user,
                amount=final_points,
                reason=f"UGC Task completed: {task.task_name}",
                source="ugc_task_completion",
                reference_id=str(task.id),
            )

            if not success:
                return False, message

            self.status = self.Status.APPROVED
            self.reviewed_at = timezone.now()
            self.points_awarded = final_points
            self.points_reason = message
            self.save()

            # Atomic slot increment using F()
            task.slots_filled = F("slots_filled") + 1
            task.save(update_fields=["slots_filled"])

            # Update user progress
            progress.record_approval(self)

            # Check for streak bonuses and achievements
            Points.check_ugc_streak_bonus(self.user, progress)
            Points.check_ugc_achievement(self.user, progress)

        return True, f"Task approved! {final_points} points awarded"

    def reject(self, reason=""):
        """
        Reject a pending submission. No points are awarded and no
        "points awarded" notification is sent.
        Returns (success, message)
        """
        if self.status == self.Status.APPROVED:
            return False, "Cannot reject an already-approved submission"

        self.status = self.Status.REJECTED
        self.rejection_reason = reason
        self.reviewed_at = timezone.now()
        self.save()

        progress, _ = UGCTaskProgress.objects.get_or_create(user=self.user)
        progress.record_rejection()

        return True, "Submission rejected"


class UGCTaskProgress(models.Model):
    """
    Tracks a user's progress and engagement with UGC tasks.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="ugc_progress"
    )

    # Statistics
    total_submissions = models.PositiveIntegerField(default=0)
    approved_submissions = models.PositiveIntegerField(default=0)
    rejected_submissions = models.PositiveIntegerField(default=0)

    # Streak tracking
    current_streak = models.PositiveIntegerField(default=0)
    longest_streak = models.PositiveIntegerField(default=0)
    last_submission_date = models.DateField(null=True, blank=True)

    # Achievement tracking
    achievements = models.JSONField(default=list, blank=True)

    # Task completion by type
    completed_task_types = models.JSONField(default=dict, blank=True)

    # Timestamps
    first_submission_at = models.DateTimeField(null=True, blank=True)
    last_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.email} - {self.approved_submissions} approved"

    def record_submission(self, submission):
        """Update progress when a submission is made."""
        self.total_submissions += 1

        if self.first_submission_at is None:
            self.first_submission_at = timezone.now()

        # Update streak
        today = timezone.now().date()

        if self.last_submission_date is None:
            # First submission ever - start the streak
            self.current_streak = 1
            self.longest_streak = max(self.longest_streak, 1)
        elif self.last_submission_date == today:
            pass  # Already submitted today
        elif self.last_submission_date == today - timezone.timedelta(days=1):
            # Consecutive day - increment streak
            self.current_streak += 1
            if self.current_streak > self.longest_streak:
                self.longest_streak = self.current_streak
        else:
            # Streak broken - reset to 1
            self.current_streak = 1
            # Note: longest_streak stays the same

        self.last_submission_date = today
        self.save()

    def record_approval(self, submission):
        """Update progress when a submission is approved."""
        self.approved_submissions += 1

        # Track completion by task type
        task_type = submission.task.task_type
        self.completed_task_types[task_type] = (
            self.completed_task_types.get(task_type, 0) + 1
        )

        self.save()

    def record_rejection(self):
        """Update progress when a submission is rejected."""
        self.rejected_submissions += 1
        self.save()


class UGCLeaderboard(models.Model):
    """
    Cached leaderboard for UGC task completion.
    """

    class TimeFrame(models.TextChoices):
        DAILY = "daily", "Daily"
        WEEKLY = "weekly", "Weekly"
        MONTHLY = "monthly", "Monthly"
        ALL_TIME = "all_time", "All Time"

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="ugc_leaderboard_entries"
    )
    timeframe = models.CharField(max_length=20, choices=TimeFrame.choices)
    rank = models.PositiveIntegerField()
    points_earned = models.PositiveIntegerField()
    tasks_completed = models.PositiveIntegerField()
    period_start = models.DateField()
    period_end = models.DateField()
    calculated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["timeframe", "rank"]
        unique_together = ["user", "timeframe", "period_start"]
        indexes = [
            models.Index(fields=["timeframe", "rank"]),
            models.Index(fields=["-calculated_at"]),
        ]

    def __str__(self):
        return f"{self.user.email} - #{self.rank} ({self.timeframe})"
