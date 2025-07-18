from django.db import models

import uuid

from accounts.models import User


# Create your models here.
class GamificationModel(models.Model):
    """
    Model for gamification management.
    """

    user = models.ForeignKey(to=User, on_delete=models.CASCADE)
    member_id = models.CharField(max_length=255, null=True)
    activity_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    assigned_to = models.CharField(max_length=150, null=True)
    pts = models.FloatField(null=True)
    is_done = models.BooleanField(default=False)
    date = models.DateTimeField(auto_now_add=True)
    task_url = models.CharField(max_length=250, null=True)
    remarks = models.CharField(max_length=255, null=True, blank=True)


class Points(models.Model):
    user = models.ForeignKey(to=User, on_delete=models.CASCADE)
    gamification = models.ForeignKey(to=GamificationModel, on_delete=models.CASCADE)
    balance = models.FloatField(null=True)
