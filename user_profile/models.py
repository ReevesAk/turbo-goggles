from django.db import models
from django.utils import timezone
from cloudinary.models import CloudinaryField

from accounts.models import User
from .choices import FOLLOWERS


class ProfileImage(models.Model):
    user = models.ForeignKey(to=User, on_delete=models.CASCADE)
    image = CloudinaryField(null=True)
    timestamp = models.DateTimeField(default=timezone.now)


PLATFORM_CHOICES = (
    ("android", "Android"),
    ("ios", "iOS"),
    ("web", "Web"),
)


class DeviceToken(models.Model):
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="device_tokens"
    )
    token = models.TextField()
    platform = models.CharField(
        max_length=10, choices=PLATFORM_CHOICES, default="android"
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "token")

    def __str__(self):
        return f"{self.user} [{self.platform}]"


class MemberSurvey(models.Model):
    user = models.OneToOneField(
        to=User, on_delete=models.CASCADE, related_name="social_profile"
    )
    age_bracket = models.CharField(max_length=150, null=True)
    sex = models.CharField(max_length=155, null=True)
    religion = models.CharField(max_length=150, null=True)
    wheredoyoulive = models.CharField(max_length=200, null=True)
    state = models.CharField(max_length=100, null=True)
    facebook_followers = models.CharField(choices=FOLLOWERS, max_length=255, null=True)
    facebook_handle = models.CharField(max_length=255, null=True)
    twitter_followers = models.CharField(choices=FOLLOWERS, max_length=255, null=True)
    twitter_handle = models.CharField(max_length=255, null=True)
    thread_followers = models.CharField(choices=FOLLOWERS, max_length=255, null=True)
    thread_handle = models.CharField(max_length=255, null=True)
    instagram_followers = models.CharField(choices=FOLLOWERS, max_length=255, null=True)
    instagram_handle = models.CharField(max_length=255, null=True)
    tiktok_followers = models.CharField(
        choices=FOLLOWERS, max_length=255, null=True, blank=True
    )
    tiktok_handle = models.CharField(max_length=255, null=True, blank=True)
    youtube_followers = models.CharField(
        choices=FOLLOWERS, max_length=255, null=True, blank=True
    )
    youtube_handle = models.CharField(max_length=255, null=True, blank=True)
    linkedin_handle = models.CharField(max_length=255, null=True, blank=True)
    telegram_followers = models.CharField(choices=FOLLOWERS, max_length=255, null=True)
    telegram_handle = models.CharField(max_length=255, null=True)
    allow_handle_change = models.BooleanField(default=False)

    def get_username_for_platform(self, platform: str) -> str | None:
        mapping = {
            "X": self.twitter_handle,
            "X(Twitter)": self.twitter_handle,
            "Instagram": self.instagram_handle,
            "Facebook": self.facebook_handle,
            "TikTok": self.tiktok_handle,
            "YouTube": self.youtube_handle,
            "LinkedIn": self.linkedin_handle,
        }
        return mapping.get(platform)


HANDLE_PLATFORM_CHOICES = (
    ("facebook", "Facebook"),
    ("twitter", "X (Twitter)"),
    ("instagram", "Instagram"),
    ("tiktok", "TikTok"),
    ("youtube", "YouTube"),
    ("linkedin", "LinkedIn"),
)

HANDLE_REQUEST_STATUS = (
    ("pending", "Pending"),
    ("approved", "Approved"),
    ("rejected", "Rejected"),
)


class HandleChangeRequest(models.Model):
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="handle_change_requests"
    )
    platform = models.CharField(max_length=20, choices=HANDLE_PLATFORM_CHOICES)
    new_handle = models.CharField(max_length=255)
    proof_url = models.URLField(
        max_length=500, help_text="Screenshot proving ownership of the new handle"
    )
    status = models.CharField(
        max_length=10, choices=HANDLE_REQUEST_STATUS, default="pending"
    )
    admin_note = models.TextField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_handle_requests",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
