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
        SendNewsletters,
        on_delete=models.CASCADE,
        related_name="recipients"
    )
    email = models.EmailField(null=True)
    sent = models.BooleanField(default=False)
    sent_at = models.DateTimeField(null=True, blank=True)
