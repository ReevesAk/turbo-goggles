import uuid

from django.db import models
from django.utils import timezone

CONTACT_TYPE = (
    ("Personal Use", "Personal Use"),
    ("Business Use", "Business Use"),
)

REACH_ME_CHANNELS = (("Phone", "Phone"), ("WhatsApp", "WhatsApp"), ("Email", "Email"))

INTEREST = (
    ("Brand Advertisement", "Brand Advertisement"),
    ("Members", "Members"),
    ("Partners", "Parnters"),
)


class JobModel(models.Model):
    title = models.CharField(max_length=255)
    location = models.CharField(max_length=255)
    company = models.CharField(max_length=255, null=True, blank=True)
    job_type = models.CharField(max_length=100, null=True, blank=True)
    job_summary = models.TextField(null=True, blank=True)

    key_responsibilities = models.JSONField(default=list, blank=True)
    requirements = models.JSONField(default=list, blank=True)

    salary = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

    def has_expired(self):
        return self.expires_at and self.expires_at <= timezone.now()

    def save(self, *args, **kwargs):
        # Automatically deactivate if expired
        if self.has_expired():
            self.is_active = False
        super().save(*args, **kwargs)


class Applications(models.Model):
    job = models.ForeignKey(
        JobModel,
        on_delete=models.CASCADE,
        related_name="applications",
        null=True,
    )
    job_title = models.CharField(max_length=255, null=True)
    first_name = models.CharField(max_length=255, null=True)
    last_name = models.CharField(max_length=255, null=True)
    email = models.EmailField(max_length=255, null=True)
    gender = models.CharField(max_length=10, null=True)
    phone_number = models.CharField(max_length=15, null=True)
    state = models.CharField(max_length=100, null=True)
    lga = models.CharField(max_length=100, null=True)
    address = models.CharField(max_length=255, null=True)
    cv = models.URLField(max_length=255, null=True)
    portfolio = models.URLField(max_length=255, null=True)
    cover_letter = models.URLField(max_length=255, null=True)
    waitlist = models.BooleanField(default=False, null=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True)


class NewsletterSubscribers(models.Model):
    email = models.EmailField(max_length=255, unique=True)
    token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, null=True)
    subscribed_at = models.DateTimeField(auto_now_add=True)


class ContactUs(models.Model):
    contact_type = models.CharField(choices=CONTACT_TYPE, max_length=50, null=True)
    first_name = models.CharField(max_length=255, null=True, blank=True)
    last_name = models.CharField(max_length=255, null=True, blank=True)
    business_name = models.CharField(max_length=150, null=True, blank=True)
    product_of_interest = models.CharField(choices=INTEREST, null=True)
    channel = models.JSONField(null=True, blank=True)
    message = models.TextField(null=True)
    accept_policy = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, null=True)
