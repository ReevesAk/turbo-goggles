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


class ActivityModel(BaseModel):
    user = models.ForeignKey(to=User, on_delete=models.SET_NULL, null=True)
    title = models.CharField(max_length=100, null=True)
    description = models.TextField(null=True)
