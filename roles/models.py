from decimal import Decimal

from django.db import models

from accounts.models import User

from basemodel import BaseModel

ADMIN_TYPES = (
    ("TaskAdmin", "TaskAdmin"),
    ("AdAdmin", "AdAdmin"),
    ("MembersAdmin", "MembersAdmin"),
    ("UserAdmin", "UserAdmin"),
    ("PartnersAdmin", "PartnersAdmin"),
    ("ContentAdmin", "ContentAdmin"),
    ("IntegrationAdmin", "IntegrationAdmin"),
    ("WalletAdmin", "WalletAdmin"),
    ("FmcgAdmin", "FmcgAdmin"),
)


class RestrictPartnerAccount(models.Model):
    user = models.ForeignKey(to=User, on_delete=models.CASCADE)
    reason = models.TextField(null=True)
    minimum_debit = models.FloatField(default=Decimal("0.00"), null=True, blank=True)
    maximum_debit = models.FloatField(default=Decimal("0.00"), null=True, blank=True)
    post_per_day = models.IntegerField(null=True, blank=True)
    is_restricted = models.BooleanField(default=False, null=True)


class RestrictBrandAdAccount(models.Model):
    user = models.ForeignKey(to=User, on_delete=models.CASCADE)
    reason = models.TextField(null=True)
    minimum_debit = models.FloatField(default=Decimal("0.00"), null=True, blank=True)
    maximum_debit = models.FloatField(default=Decimal("0.00"), null=True, blank=True)
    post_per_day = models.IntegerField(null=True, blank=True)
    is_restricted = models.BooleanField(default=False, null=True)


class ActivityModel(BaseModel):
    user = models.ForeignKey(to=User, on_delete=models.SET_NULL, null=True)
    title = models.CharField(max_length=100, null=True)
    description = models.TextField(null=True)


class SendNewsletters(models.Model):
    volume = models.CharField(max_length=50, null=True)
    title = models.CharField(max_length=255, null=True)
    content = models.TextField(null=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True)


class NewsletterRecipient(models.Model):
    newsletter = models.ForeignKey(
        SendNewsletters, on_delete=models.CASCADE, related_name="recipients"
    )
    email = models.EmailField(null=True)
    sent = models.BooleanField(default=False)
    sent_at = models.DateTimeField(null=True, blank=True)


KNOWLEDGE_BASE_SECTIONS = (
    ("Airtime & Data", "Airtime & Data"),
    ("Electricity", "Electricity"),
    ("Cable TV", "Cable TV"),
    ("Banking", "Banking"),
    ("Brand Ads", "Brand Ads"),
    ("Partners", "Partners"),
)

KNOWLEDGE_BASE_CONTENT_TYPES = (
    ("Website", "Website"),
    ("Social Post", "Social Post"),
    ("Email", "Email"),
)


class knowledgeBaseModel(models.Model):
    category = models.CharField(max_length=255, null=True)
    section = models.CharField(
        max_length=255, choices=KNOWLEDGE_BASE_SECTIONS, null=True
    )
    content_type = models.CharField(
        max_length=255, choices=KNOWLEDGE_BASE_CONTENT_TYPES, null=True
    )
    authors = models.JSONField(default=list, null=True, blank=True)
    caption = models.CharField(max_length=255, null=True)
    author_image_urls = models.JSONField(default=list, null=True, blank=True)
    content = models.TextField(null=True)
    ads_and_media_url = models.JSONField(default=list, null=True, blank=True)
    ad_description = models.TextField(null=True, blank=True)
    is_post_scheduled = models.BooleanField(default=False)
    selected_date_time = models.DateTimeField(null=True, blank=True)
    selected_time = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True)

    def __str__(self):
        return self.caption


class AdminMessage(BaseModel):
    """One row per admin SMS/email send (not per recipient) - an audit trail
    of who sent what to whom, updated by user_profile.tasks.send_admin_message."""

    CHANNEL_CHOICES = (("sms", "SMS"), ("email", "Email"))
    AUDIENCE_CHOICES = (
        ("selected", "Selected users"),
        ("members", "All members"),
        ("all_users", "All users"),
    )
    STATUS_CHOICES = (
        ("queued", "Queued"),
        ("sending", "Sending"),
        ("sent", "Sent"),
        ("partial", "Partially sent"),
        ("failed", "Failed"),
    )

    channel = models.CharField(max_length=10, choices=CHANNEL_CHOICES)
    audience = models.CharField(max_length=20, choices=AUDIENCE_CHOICES)
    user_ids = models.JSONField(default=list, blank=True)
    subject = models.CharField(max_length=200, blank=True)
    body = models.TextField()
    sent_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="admin_messages"
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="queued")
    recipients_targeted = models.PositiveIntegerField(default=0)
    recipients_sent = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.channel} to {self.audience} ({self.status})"
