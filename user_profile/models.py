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
    user = models.OneToOneField(to=User, on_delete=models.CASCADE)
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
    telegram_followers = models.CharField(choices=FOLLOWERS, max_length=255, null=True)
    telegram_handle = models.CharField(max_length=255, null=True)
    leisure_activities = models.CharField(max_length=255, null=True)
    phone_activities = models.CharField(max_length=255, null=True)
    music_genre = models.CharField(max_length=255, null=True)
    social_event = models.CharField(max_length=255, null=True)
