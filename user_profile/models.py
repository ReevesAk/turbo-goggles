from django.db import models
from django.utils import timezone
from cloudinary.models import CloudinaryField

from accounts.models import User
from .choices import FOLLOWERS, SEX, BENEFICIARIES, RELIGION


class ProfileImage(models.Model):
    user = models.ForeignKey(to=User, on_delete=models.CASCADE)
    image = CloudinaryField(null=True)
    timestamp = models.DateTimeField(default=timezone.now)


class MemberSurvey(models.Model):
    user = models.OneToOneField(to=User, on_delete=models.CASCADE)
    age_bracket = models.CharField(max_length=150, null=True)
    sex = models.CharField(max_length=155, null=True)
    religion = models.CharField(max_length=150, null=True)
    wheredoyoulive = models.CharField(max_length=200, null=True)
    state = models.CharField(max_length=100, null=True)
    facebook_followers = models.CharField(choices=FOLLOWERS, max_length=255, null=True)
    twitter_followers = models.CharField(choices=FOLLOWERS, max_length=255, null=True)
    thread_followers = models.CharField(choices=FOLLOWERS, max_length=255, null=True)
    instagram_followers = models.CharField(choices=FOLLOWERS, max_length=255, null=True)
    telegram_followers = models.CharField(choices=FOLLOWERS, max_length=255, null=True)
    leisure_activities = models.CharField(max_length=255, null=True)
    phone_activities = models.CharField(max_length=255, null=True)
    music_genre = models.CharField(max_length=255, null=True)
    social_event = models.CharField(max_length=255, null=True)
