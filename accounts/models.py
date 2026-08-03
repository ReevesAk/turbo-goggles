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
    ("PartnersAdmin", "PartnersAdmin"),
    ("ContentAdmin", "ContentAdmin"),
    ("WalletAdmin", "WalletAdmin"),
    ("FmcgAdmin", "FmcgAdmin"),
)

ALERT_TYPE = (("Email", "Email"), ("SMS", "SMS"), ("Both", "Both"))

BRAND_TYPE = (
    ("Individual", "Individual"),
    ("Company", "Company"),
    ("Business", "Business"),
)

TRANSACTION_TYPE = (
    ("Transfer to Picadailys Account", "Transfer to Picadailys Account"),
    ("Transfer to Bank Account", "Transfer to Bank Account"),
    ("Points Redemption to Wallet", "Points Redemption to Wallet"),
    ("Brand Promotion", "Brand Promotion"),
    ("UGC Task Funding", "UGC Task Funding"),
    ("Data", "Data"),
    ("Airtime", "Airtime"),
    ("Bill Payment", "Bill Payment"),
    ("Hotel", "Hotel"),
    ("Travel", "Travel"),
    ("Education", "Education"),
    ("Leisure", "Leisure"),
    ("Consumables", "Consumables"),
    ("Food", "Food"),
    ("Health", "Health"),
    ("Insurance", "Insurance"),
    ("Gym", "Gym"),
    ("Cinema", "Cinema"),
    ("Courier", "Courier"),
    ("Partner Service", "Partner Service"),
)


# User describes the database model for each user.
class User(AbstractBaseUser, PermissionsMixin):
    # Agent/admin pin brute-force protection
    agent_pin_attempts = models.IntegerField(default=0, null=True)
    agent_pin_locked_until = models.DateTimeField(null=True, blank=True)
    first_name = models.CharField(max_length=255, null=True)
    last_name = models.CharField(max_length=255, null=True)
    full_name = models.CharField(max_length=255, null=True, blank=True)
    password = models.CharField(max_length=255, null=True)
    phone_number = models.CharField(max_length=20, unique=True, null=True)
    email = models.CharField(max_length=80, unique=True, null=True, blank=True)
    country = models.CharField(max_length=155, blank=False)
    referral_code = models.CharField(max_length=50, null=True, blank=True)
    state = models.CharField(max_length=155, blank=False)
    city = models.CharField(max_length=155, blank=False)
    profile_img_url = models.CharField(max_length=255, null=True)
    alert_type_choice = models.CharField(
        choices=ALERT_TYPE, default="Both", max_length=50, null=True
    )
    is_bvn_verified = models.BooleanField(default=False)
    is_nin_verified = models.BooleanField(default=False)
    has_wallet = models.BooleanField(default=False)
    is_verified = models.BooleanField(default=False)
    is_member = models.BooleanField(default=False)
    has_done_survey = models.BooleanField(default=False)
    total_points = models.IntegerField(default=0, null=True)
    points_naira_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        null=True,
        blank=True,
        help_text="Naira value of user's redeemable points",
    )
    level = models.CharField(max_length=20, default="Starter", null=True)
    welcome_bonus = models.FloatField(default=Decimal("0.00"))
    has_bonus = models.BooleanField(default=False)
    has_created_pin = models.BooleanField(default=False)
    has_card = models.BooleanField(default=False)
    admin_pin = models.CharField(max_length=128, null=True, blank=True)
    is_admin_pin_set = models.BooleanField(default=False, null=True)
    agent_pin = models.CharField(max_length=128, null=True, blank=True)
    is_agent_pin_set = models.BooleanField(default=False, null=True)
    is_admin_disabled = models.BooleanField(default=False, null=True)
    is_agent_disabled = models.BooleanField(default=False, null=True)
    is_biometric_enabled = models.BooleanField(default=False, null=True)

    password_attempts = models.IntegerField(default=0, null=True)
    password_locked_until = models.DateTimeField(null=True, blank=True)

    # Brand details.
    has_promoted = models.BooleanField(default=False)

    # Partner details.
    active_role = models.CharField(max_length=150, null=True)

    business_name = models.CharField(max_length=500, null=True)
    website = models.CharField(max_length=255, null=True)
    business_category = models.CharField(max_length=255, null=True)
    business_verified = models.BooleanField(default=False)
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_disabled = models.BooleanField(default=False, null=True)
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    date_joined = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    last_login = models.DateTimeField(null=True, blank=True)

    consent_given = models.BooleanField(default=False)
    consent_given_at = models.DateTimeField(null=True, blank=True)

    USERNAME_FIELD = "phone_number"
    REQUIRED_FIELDS = []

    objects = CustomUserManager()

    def __str__(self):
        return self.phone_number

    def update_level(self):
        # Kept in sync with Points.get_user_tier() in gamification/points.py by
        # hand - that module imports from here, so it can't be imported back.
        LEVELS = [
            {"title": "Starter", "min_points": 0},
            {"title": "Explorer", "min_points": 700},
            {"title": "Challenger", "min_points": 1500},
            {"title": "Influencer", "min_points": 3000},
            {"title": "Champion", "min_points": 6000},
            {"title": "Elite", "min_points": 10000},
            {"title": "Legend", "min_points": 18000},
        ]

        for level in reversed(LEVELS):
            if self.total_points >= level["min_points"]:
                self.level = level["title"]
                break

    class Meta:
        ordering = ["-created_at"]


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
    device_name = models.CharField(max_length=255, null=True)
    device_os = models.CharField(max_length=100, null=True)
    created_at = models.DateTimeField(auto_now_add=True)


class OTP(models.Model):
    otp = models.CharField(max_length=6, null=True)
    user_id = models.IntegerField()
    expires_at = models.DateTimeField()


class TxModel(models.Model):
    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("SUCCESS", "Success"),
        ("FAILED", "Failed"),
        ("CANCELLED", "Cancelled"),
    ]

    user = models.ForeignKey(to=User, on_delete=models.CASCADE)
    tx_reference = models.CharField(
        max_length=100, null=True, unique=True
    )  # Idempotency key
    external_tx_reference = models.CharField(
        max_length=18, null=True, blank=True
    )  # TRA-prefixed ID for third party
    tx_type = models.CharField(choices=TRANSACTION_TYPE, max_length=200, null=True)
    amount = models.FloatField(default=Decimal("0.00"), null=True)
    vat = models.FloatField(null=True, blank=True)
    transfer_fee = models.FloatField(null=True, blank=True)
    description = models.CharField(max_length=255, null=True)
    rwd = models.FloatField(null=True)
    status = models.CharField(max_length=20, default="PENDING", choices=STATUS_CHOICES)
    date = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "tx_type"]),
            models.Index(fields=["user", "date"]),
            models.Index(fields=["user", "status"]),
        ]


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


class WelcomeBonusCounter(models.Model):
    """
    Singleton counter to track how many users have been awarded the welcome bonus.
    """

    id = models.IntegerField(primary_key=True, default=1)
    awarded_count = models.IntegerField(default=0)


class WelcomeBonusAward(models.Model):
    """
    Record that a user received the welcome bonus.
    """

    user = models.ForeignKey(to=User, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=500)
    awarded_at = models.DateTimeField(auto_now_add=True)
    tx_reference = models.CharField(max_length=100, null=True, blank=True, unique=True)

    class Meta:
        ordering = ["-awarded_at"]


class UserDeletion(models.Model):
    """
    Audit log for account deletion (soft delete - see User.is_deleted).
    One row per deletion. deleted_by is null for self-service deletions.
    """

    user = models.ForeignKey(
        to=User, on_delete=models.CASCADE, related_name="deletion_records"
    )
    reason = models.TextField(blank=True)
    deleted_by = models.ForeignKey(
        to=User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="deletions_performed",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
