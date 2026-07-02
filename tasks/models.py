import uuid

from django.db import models
from django.utils import timezone

from accounts.models import User
from adverts.models import CreateAd
from basemodel import BaseModel

BRAND_SUBMISSION_STATUS = (
    ("Pending", "Pending"),
    ("Approved", "Approved"),
    ("Rejected", "Rejected"),
    ("Flagged", "Flagged"),
)


PLATFORM_CHOICES = (
    ("X", "X (Twitter)"),
    ("Instagram", "Instagram"),
    ("Facebook", "Facebook"),
    ("TikTok", "TikTok"),
    ("YouTube", "YouTube"),
)

TASK_TYPE_CHOICES = (
    ("Follow", "Follow"),
    ("Like", "Like"),
    ("Comment", "Comment"),
    ("Post", "Post"),
)

SUBMISSION_STATUS = (
    ("Pending", "Pending"),
    ("Approved", "Approved"),
    ("Rejected", "Rejected"),
    ("Flagged", "Flagged"),
)

VERDICT_CHOICES = (
    ("Pass", "Pass"),
    ("Fail", "Fail"),
    ("Uncertain", "Uncertain"),
)



class SocialTask(BaseModel):
    """A task created by a brand admin that users can complete for rewards."""

    ad = models.ForeignKey(CreateAd, on_delete=models.CASCADE, related_name="social_tasks", null=True, blank=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    platform = models.CharField(choices=PLATFORM_CHOICES, max_length=20)
    task_type = models.CharField(choices=TASK_TYPE_CHOICES, max_length=20)

    target_url = models.URLField(blank=True, null=True)
    target_account = models.CharField(max_length=150, blank=True, null=True)
    target_content_hint = models.CharField(
        max_length=300, blank=True, null=True,
        help_text=(
            "Short description of the target post/video so the AI can visually identify it. "
            "E.g. 'Video titled PicaDaily App Launch' or 'Post captioned Summer Sale is here'."
        ),
    )
    required_hashtag = models.CharField(max_length=100, blank=True, null=True)
    required_mention = models.CharField(max_length=100, blank=True, null=True)
    required_keywords = models.JSONField(default=list, blank=True)

    reward_points = models.PositiveIntegerField(default=0)
    reward_naira = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    max_submissions = models.PositiveIntegerField(default=100)
    total_submissions = models.PositiveIntegerField(default=0)

    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="tasks_created")

    @property
    def is_expired(self):
        if self.expires_at:
            return timezone.now() > self.expires_at
        return False

    @property
    def is_available(self):
        return self.is_active and not self.is_expired and self.total_submissions < self.max_submissions

    def __str__(self):
        return f"{self.platform} {self.task_type} — {self.title}"


class TaskSubmission(BaseModel):
    """Proof submitted by a user for a social task."""

    task = models.ForeignKey(SocialTask, on_delete=models.CASCADE, related_name="submissions")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="task_submissions")

    screenshot_url = models.CharField(max_length=500, blank=True, null=True)
    post_url = models.URLField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    verification_code = models.CharField(max_length=15, blank=True, null=True)

    status = models.CharField(choices=SUBMISSION_STATUS, max_length=20, default="Pending")
    reviewed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="reviewed_submissions"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True, null=True)

    reward_issued = models.BooleanField(default=False)

    class Meta:
        unique_together = ("task", "user")

    def __str__(self):
        return f"{self.user} → {self.task} [{self.status}]"


class VerificationResult(BaseModel):
    """AI verdict on a task submission."""

    submission = models.OneToOneField(TaskSubmission, on_delete=models.CASCADE, related_name="verification")

    verdict = models.CharField(choices=VERDICT_CHOICES, max_length=20)
    confidence_score = models.PositiveIntegerField(default=0)
    ai_reasoning = models.TextField(blank=True, null=True)
    flags = models.JSONField(default=list, blank=True)

    username_matched = models.BooleanField(default=False)
    hashtag_found = models.BooleanField(default=False)
    mention_found = models.BooleanField(default=False)
    action_confirmed = models.BooleanField(default=False)
    verification_code_found = models.BooleanField(default=True)
    target_matched = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.verdict} ({self.confidence_score}%) — {self.submission}"


class BrandVerificationResult(BaseModel):
    """AI verdict on a brand task submission."""

    submission = models.OneToOneField("BrandTaskSubmission", on_delete=models.CASCADE, related_name="verification")

    verdict = models.CharField(choices=VERDICT_CHOICES, max_length=20)
    confidence_score = models.PositiveIntegerField(default=0)
    ai_reasoning = models.TextField(blank=True, null=True)
    flags = models.JSONField(default=list, blank=True)

    platform_confirmed = models.BooleanField(default=True)
    username_matched = models.BooleanField(default=False)
    action_confirmed = models.BooleanField(default=False)
    target_matched = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.verdict} ({self.confidence_score}%) — {self.submission}"


class UserTrustScore(BaseModel):
    """Tracks a user's submission history and trustworthiness."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="trust_score")
    score = models.IntegerField(default=50)

    total_submissions = models.PositiveIntegerField(default=0)
    approved_submissions = models.PositiveIntegerField(default=0)
    rejected_submissions = models.PositiveIntegerField(default=0)
    flagged_submissions = models.PositiveIntegerField(default=0)

    auto_approve_threshold = models.IntegerField(default=80)

    @property
    def approval_rate(self):
        if self.total_submissions == 0:
            return 0
        return round((self.approved_submissions / self.total_submissions) * 100)

    @property
    def requires_manual_review(self):
        return self.score < 20

    @property
    def can_auto_approve(self):
        return self.score >= self.auto_approve_threshold

    def record_approval(self):
        self.approved_submissions += 1
        self.total_submissions += 1
        self.score = min(100, self.score + 2)
        self.save()

    def record_rejection(self):
        self.rejected_submissions += 1
        self.total_submissions += 1
        self.score = max(0, self.score - 10)
        self.save()

    def record_flag(self):
        self.flagged_submissions += 1
        self.total_submissions += 1
        self.score = max(0, self.score - 5)
        self.save()

    def __str__(self):
        return f"{self.user} trust: {self.score}/100"


class BrandTaskSubmission(BaseModel):
    """Proof submitted by a user for a brand ad campaign task (all 6 task types)."""

    ad = models.ForeignKey(CreateAd, on_delete=models.CASCADE, related_name="brand_submissions")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="brand_task_submissions")

    screenshot_url = models.CharField(max_length=500, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    survey_answers = models.JSONField(default=list, blank=True)

    status = models.CharField(choices=BRAND_SUBMISSION_STATUS, max_length=20, default="Pending")
    reviewed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="reviewed_brand_submissions",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True, null=True)
    reward_issued = models.BooleanField(default=False)

    class Meta:
        unique_together = ("ad", "user")

    def __str__(self):
        return f"{self.user} → {self.ad.campaign_name} [{self.status}]"
