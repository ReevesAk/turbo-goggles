from decimal import Decimal

from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.utils import timezone

from .user_manager import CustomUserManager


USER_CATEGORY_CHOICES = (
    ("SuperAdmin", "SuperAdmin"),
    ("Manager", "Manager"),
    ("Moderator", "Moderator"),
    ("Agent", "Agent"),
    ("User", "User"),
    ("Partner", "Partner"),
    ("Member", "Member"),
    ("BrandAd", "BrandAd"),
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

BRAND_TYPE = (
    ("Individual", "Individual"),
    ("Company", "Company"),
    ("Business", "Business"),
)

TRANSACTION_TYPE = (
    ("Transfer to Picadailys Account", "Transfer to Picadailys Account"),
    ("Transfer to Bank Account", "Transfer to Bank Account"),
    ("Data", "Data"),
    ("Airtime", "Airtime"),
    ("Data", "Data"),
    ("Electricity", "Electricity"),
    ("Hotel", "Hotel"),
    ("Travel", "Travel"),
    ("Education", "Education"),
    ("Leisure", "Leisure"),
    ("Consumables", "Consumables"),
    ("Food", "Food"),
    ("Health", "Health"),
    ("Insurance", "Insurance"),
)


# User describes the database model for each user.
class User(AbstractBaseUser, PermissionsMixin):
    first_name = models.CharField(max_length=255, null=True)
    last_name = models.CharField(max_length=255, null=True)
    full_name = models.CharField(max_length=255, null=True, blank=True)
    password = models.CharField(max_length=255, null=True)
    phone_number = models.CharField(max_length=20, unique=True, null=True)
    email = models.CharField(max_length=80, unique=True, null=True, blank=True)
    country = models.CharField(max_length=155, blank=False)
    state = models.CharField(max_length=155, blank=False)
    city = models.CharField(max_length=155, blank=False)
    profile_img_url = models.CharField(max_length=255, null=True)
    is_bvn_verified = models.BooleanField(default=False)
    has_wallet = models.BooleanField(default=False)
    is_verified = models.BooleanField(default=False)
    is_member = models.BooleanField(default=False)
    has_done_survey = models.BooleanField(default=False)
    welcome_bonus = models.FloatField(default=Decimal("0.00"))
    has_bonus = models.BooleanField(default=False)
    has_created_pin = models.BooleanField(default=False)
    has_card = models.BooleanField(default=False)
    admin_pin = models.CharField(max_length=128, null=True, blank=True)
    is_admin_pin_set = models.BooleanField(default=False, null=True)
    is_admin_disabled = models.BooleanField(default=False, null=True)
    is_biometric_enabled = models.BooleanField(default=False, null=True)

    # Brand details.
    address = models.CharField(max_length=155, blank=False, null=True)
    whoareyou = models.CharField(choices=BRAND_TYPE, max_length=150, null=True)
    name = models.CharField(max_length=155, blank=False, null=True)
    brand_email = models.CharField(max_length=80, unique=True, null=True)
    brand_phone_number = models.CharField(max_length=20, unique=True, null=True)
    brand_type = models.CharField(max_length=155, blank=False, null=True)
    has_promoted = models.BooleanField(default=False)
    online_presence = models.CharField(max_length=20, null=True)

    # Brand onboarding.
    brand_name = models.CharField(max_length=255, null=True)
    description = models.CharField(max_length=150, null=True)
    services = models.CharField(max_length=255, null=True)
    website = models.CharField(max_length=150, null=True)
    facebook = models.CharField(max_length=150, null=True)
    twitter = models.CharField(max_length=150, null=True)
    instagram = models.CharField(max_length=150, null=True)
    telegram = models.CharField(max_length=150, null=True)

    # Partner details.
    active_role = models.CharField(max_length=150, null=True)

    business_name = models.CharField(max_length=500, null=True)
    website = models.CharField(max_length=255, null=True)
    business_category = models.CharField(max_length=255, null=True)
    business_verified = models.BooleanField(default=False)
    is_cac_approved = models.BooleanField(default=False, null=True)
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_disabled = models.BooleanField(default=False, null=True)
    date_joined = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    last_login = models.DateTimeField(null=True, blank=True)

    USERNAME_FIELD = "phone_number"
    REQUIRED_FIELDS = []

    objects = CustomUserManager()

    def __str__(self):
        return self.phone_number


class AccountType(models.Model):
    user = models.ForeignKey(
        to=User, related_name="account_types", on_delete=models.CASCADE, null=True
    )
    user_type = models.CharField(
        choices=USER_CATEGORY_CHOICES, max_length=40, null=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class DeviceId(models.Model):
    user = models.ForeignKey(to=User, on_delete=models.CASCADE)
    device_id = models.CharField(max_length=250, null=True)
    created_at = models.DateTimeField(auto_now_add=True)


class OTP(models.Model):
    otp = models.CharField(max_length=6, null=True)
    user_id = models.IntegerField()
    expires_at = models.DateTimeField(auto_now_add=True)


class TxModel(models.Model):
    user = models.ForeignKey(to=User, on_delete=models.CASCADE)
    tx_reference = models.CharField(max_length=100, null=True)
    tx_type = models.CharField(choices=TRANSACTION_TYPE, max_length=200, null=True)
    tx_id = models.CharField(max_length=255, null=True)
    amount = models.FloatField(default=Decimal("0.00"), null=True)
    description = models.CharField(max_length=255, null=True)
    rwd = models.FloatField(null=True)
    date = models.DateTimeField(auto_now_add=True)


class Rewards(models.Model):
    user = models.ForeignKey(to=User, on_delete=models.CASCADE)
    transaction = models.ForeignKey(
        to=TxModel, on_delete=models.SET_NULL, null=True, blank=True
    )
    mystery_box = models.CharField(max_length=255, null=True)
    form_of_gift = models.CharField(max_length=100, null=True)
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)


class UserNotification(models.Model):
    user = models.ForeignKey(
        to=User, related_name="notification", on_delete=models.CASCADE
    )
    title = models.CharField(max_length=100, blank=True, null=True)
    message = models.CharField(max_length=255, null=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


class PurchaseModel(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="purchases")
    service_type = models.CharField(
        max_length=150, null=True
    )  # Service type (e.g., Restaurant, Gym)
    service_id = models.PositiveIntegerField(
        null=True
    )  # ID of the specific service purchased
    amount = models.FloatField(null=True, blank=True)
    purchase_date = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-purchase_date"]

    def __str__(self):
        return f"Purchase #{self.id} - {self.user.username} - {self.service_type}"
