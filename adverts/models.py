import uuid
from datetime import timedelta
from decimal import Decimal

from django.db import models
from django.utils import timezone
from django.contrib.gis.db import models as gis_models
from django.contrib.gis.geos import Point

from accounts.models import User
from gamification.models import UserGeneratedContent
from .pricing import TARGETING_TYPE_CHOICES, compute_cost_per_engagement

DEMOGRAPHY = (
    ("18+", "18+"),
    ("18 - 25", "18 - 25"),
    ("26 - 35", "26 - 35"),
    ("36 - 45", "36 - 45"),
    ("46+", "46+"),
)

TYPE_OF_BUSUINESS = (
    ("Online", "Online"),
    ("Physical", "Physical"),
    ("Hybrid", "Hybrid"),
)

GENDER = (
    ("Male", "Male"),
    ("Female", "Female"),
    ("All", "All"),
)

INDUSTRY_CHOICES = (
    ("Technology", "Technology"),
    ("Fashion & Beauty", "Fashion & Beauty"),
    ("Food & Drinks", "Food & Drinks"),
    ("Health & Fitness", "Health & Fitness"),
    ("Travels", "Travels"),
    ("Education", "Education"),
    ("Entertainment", "Entertainment"),
    ("Home Decor", "Home Decor"),
    ("Sports", "Sports"),
    ("Business & Finance", "Business & Finance"),
    ("Retail & General Trade", "Retail & General Trade"),
    ("Charities & Membership", "Charities & Membership"),
)

BRAND_OBJECTIVE = (
    ("Brand Awareness", "Brand Awareness"),
    ("Generate Leads", "Generate Leads"),
    ("Drive Sales", "Drive Sales"),
    ("Promote Awareness(Engagement)", "Promote Awareness(Engagement)"),
)

LOCATION_TYPE_CHOICES = (
    ("nationwide", "Nationwide"),
    ("states", "States"),
    ("cities", "Cities"),
)

TASK_TYPE_CHOICES = (
    ("watch_video", "Watch Video"),
    ("social_engage", "Social Engage"),
    ("website_visit", "Website Visit"),
    ("store_visit", "Store Visit"),
    ("survey", "Survey"),
    ("app_download", "App Download"),
)


class CreateAd(models.Model):
    user = models.ForeignKey(
        to=User, on_delete=models.CASCADE, related_name="create_ad"
    )
    business_or_brand_name = models.CharField(max_length=255, null=True)
    type_of_business = models.CharField(
        choices=TYPE_OF_BUSUINESS, max_length=155, null=True
    )
    industry = models.CharField(choices=INDUSTRY_CHOICES, max_length=255, null=True)
    brand_objective = models.CharField(
        choices=BRAND_OBJECTIVE, max_length=255, null=True
    )
    campaign_name = models.CharField(max_length=150, null=True)
    expiry_date = models.DateTimeField(null=True, blank=True)
    gender = models.CharField(choices=GENDER, max_length=20, null=True)
    demography = models.CharField(
        choices=DEMOGRAPHY, max_length=150, blank=True, null=True
    )
    engagement_type = models.CharField(max_length=150, blank=True, null=True)
    daily_allocation = models.CharField(max_length=150, blank=True, null=True)

    website = models.CharField(max_length=150, blank=True, null=True)
    brand_socials = models.JSONField(default=list, blank=True)
    type_of_brand = models.CharField(max_length=100, null=True, blank=True)
    campaign_duration = models.CharField(max_length=155, null=True, blank=True)
    amount = models.CharField(max_length=155, null=True, blank=True)
    is_active = models.BooleanField(default=False, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Task type fields
    task_type = models.CharField(
        choices=TASK_TYPE_CHOICES, max_length=30, null=True, blank=True
    )
    task_name = models.CharField(max_length=255, null=True, blank=True)
    task_description = models.TextField(null=True, blank=True)
    task_details = models.JSONField(default=dict, blank=True)
    reward_points = models.PositiveIntegerField(default=0, null=True, blank=True)
    slot_cap = models.PositiveIntegerField(null=True, blank=True)
    slots_filled = models.PositiveIntegerField(default=0)
    ads_credit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    auto_boost_points = models.PositiveIntegerField(default=0)
    credit_settled = models.BooleanField(default=False)

    # co-ordinates
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    location = gis_models.PointField(
        geography=True,
        null=True,
        blank=True,
        spatial_index=True,
        help_text="Derived automatically from latitude/longitude on save.",
    )

    @property
    def cost_per_engagement(self) -> Decimal:
        try:
            duration = int(self.campaign_duration or 0)
        except (TypeError, ValueError):
            duration = 0
        if self.task_type and duration:
            return compute_cost_per_engagement(
                self.task_type, duration, self.targeting_type or "broad"
            )
        return Decimal("0")

    @property
    def unused_credit(self) -> Decimal:
        slot_cap = self.slot_cap or 0
        if slot_cap == 0:
            return Decimal("0")
        unused = max(0, slot_cap - (self.slots_filled or 0))
        try:
            amount = Decimal(str(self.amount or 0))
        except Exception:
            return Decimal("0")
        if amount <= 0:
            return Decimal("0")
        # Proportional refund: unused_slots / slot_cap × amount_paid
        return (Decimal(str(unused)) / Decimal(str(slot_cap))) * amount

    # Targeting
    location_type = models.CharField(
        choices=LOCATION_TYPE_CHOICES, max_length=20, null=True, blank=True
    )
    targeting_type = models.CharField(
        choices=TARGETING_TYPE_CHOICES,
        max_length=15,
        default="broad",
        help_text="Determines the pricing multiplier: broad/city/niche/influencer",
    )
    countries = models.JSONField(default=list, blank=True)
    auto_boost = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if self.campaign_duration and not self.expiry_date:
            self.expiry_date = timezone.now() + timedelta(
                days=int(self.campaign_duration)
            )

        if self.latitude and self.longitude:
            self.location = Point(
                float(self.longitude), float(self.latitude), srid=4326
            )
        else:
            self.location = None

        super().save(*args, **kwargs)


class BrandAdCreditWallet(models.Model):
    """Running credit balance for a brand — sourced from unfilled ad slots."""

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="ad_credit_wallet"
    )
    balance = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user} — ₦{self.balance} credit"


class BrandAdCreditLedger(models.Model):
    """Immutable log of every credit (unused slot refund) and debit (applied to new ad)."""

    CREDIT = "credit"
    DEBIT = "debit"
    TYPES = ((CREDIT, "Credit"), (DEBIT, "Debit"))

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="ad_credit_ledger"
    )
    transaction_type = models.CharField(choices=TYPES, max_length=10)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    balance_after = models.DecimalField(max_digits=14, decimal_places=2)
    source_ad = models.ForeignKey(
        CreateAd,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="credit_entries",
    )
    source_ugc_task = models.ForeignKey(
        UserGeneratedContent,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="credit_entries",
    )
    reason = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.transaction_type} ₦{self.amount} → {self.user} [{self.created_at:%Y-%m-%d}]"


class AdMedia(models.Model):
    brand = models.ForeignKey(
        to=CreateAd, on_delete=models.CASCADE, related_name="ad_media"
    )
    images = models.CharField(max_length=150, blank=True, null=True)
    videos = models.CharField(max_length=150, blank=True, null=True)

    def __str__(self) -> str:
        return (
            f"{self.images}, {self.videos}"
            if self.images and self.videos
            else "Unknown Media"
        )


class AdLocation(models.Model):
    brand = models.ForeignKey(
        to=CreateAd, on_delete=models.CASCADE, related_name="brand_location"
    )
    state = models.CharField(max_length=150, blank=True, null=True)
    city = models.CharField(max_length=150, blank=True, null=True)

    def __str__(self) -> str:
        return (
            f"{self.state}, {self.city}"
            if self.state and self.city
            else "Unknown Location"
        )


class StoreVisitQRCode(models.Model):
    """One QR code per store-visit ad campaign. Scanning it completes the task for that user."""

    ad = models.OneToOneField(
        CreateAd, on_delete=models.CASCADE, related_name="store_visit_qr"
    )
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    visit_code = models.CharField(max_length=20, unique=True, blank=True)
    qr_image_url = models.CharField(max_length=500, blank=True, null=True)
    scan_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"QR for {self.ad.campaign_name} ({self.visit_code})"
