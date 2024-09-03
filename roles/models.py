from decimal import Decimal

from django.db import models
import uuid

from accounts.models import User


class GamificationModel(models.Model):
    """
    Model for gamification management.
    """

    user = models.ForeignKey(to=User, on_delete=models.CASCADE)
    title = models.CharField(max_length=255, null=True)
    task_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    description = models.CharField(max_length=255, null=True)
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


class Applications(models.Model):
    name = models.CharField(max_length=255, null=True)
    email = models.EmailField(max_length=255, null=True)
    role = models.CharField(max_length=150, null=True)
    cover_letter = models.CharField(max_length=255, null=True)
    certificates = models.CharField(max_length=255, null=True)
    portfolio = models.CharField(max_length=200, null=True, blank=True)
    cv = models.CharField(max_length=255, null=True)


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
