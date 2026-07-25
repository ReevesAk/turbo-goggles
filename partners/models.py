from decimal import Decimal

from django.db import models
import uuid

from accounts.models import User, TxModel

BUSINESS_CATEGORY = (
    ("Restaurant", "Restaurant"),
    ("Gym", "Gym"),
    ("Cinema", "Cinema"),
    ("Delivery Services", "Delivery Services"),
    ("Consumable Services", "Consumable Services"),
    ("Travel", "Travel"),
    ("Hotel", "Hotel"),
)


class VerifyCAC(models.Model):
    """Model for verifying partner business."""

    users = models.ForeignKey(to=User, on_delete=models.CASCADE, null=True)
    rc_number = models.CharField(max_length=255, null=True)
    business_name = models.CharField(max_length=255, null=True)

    def __str__(self):
        return f"{self.id}"


class PartnerServices(models.Model):
    """Model for partner services."""

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="related_services"
    )
    business = models.CharField(choices=BUSINESS_CATEGORY, max_length=255, null=True)
    service = models.CharField(max_length=255, null=True)
    service_star = models.CharField(max_length=50, null=True, blank=True)
    price = models.FloatField(null=True, help_text="Partner's negotiated cost price.")
    description = models.TextField(null=True)
    from_station = models.CharField(max_length=255, null=True, blank=True)
    destination = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True)

    # Commission negotiated by a PartnersAdmin. A service is not visible on
    # self-serve until this is set - commission_set is the gate, not price
    # or business_verified.
    commission_rate = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    commission_set = models.BooleanField(default=False)
    final_price = models.FloatField(
        null=True,
        blank=True,
        help_text="price + commission. Set once commission_rate is.",
    )

    def set_commission(self, commission_rate):
        """Negotiate & lock in this service's commission - the gate that
        makes it eligible to appear on self-serve."""
        price = Decimal(str(self.price or 0))
        commission_rate = Decimal(str(commission_rate))
        self.commission_rate = commission_rate
        self.final_price = float(price + (price * commission_rate / Decimal("100")))
        self.commission_set = True
        self.save(update_fields=["commission_rate", "final_price", "commission_set"])


class CustomerRating(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    service = models.ForeignKey(
        PartnerServices, on_delete=models.CASCADE, related_name="customer_rating"
    )
    rating = models.CharField(max_length=50, null=True, blank=True)
    review = models.TextField(null=True, blank=True)
    slug = models.SlugField(default="", max_length=155, null=False)


class PartnerServicePhotos(models.Model):
    """Model for partner service photos."""

    partner = models.ForeignKey(
        PartnerServices,
        on_delete=models.CASCADE,
        related_name="service_photos",
        null=True,
    )
    photo = models.CharField(max_length=255, null=True)


class AvailablePartnerGymTrainers(models.Model):
    """Model for gym partner service photos."""

    partner = models.ForeignKey(
        PartnerServices,
        on_delete=models.CASCADE,
        related_name="gym_trainers",
        null=True,
    )
    trainer_name = models.CharField(max_length=255, null=True)
    trainer_price = models.FloatField(null=True)
    trainer_photo = models.CharField(max_length=255, null=True)


class PartnerCommissionRule(models.Model):
    """
    Admin-configurable commission PicaDailys takes from a partner service
    category. Referenced (not copied) at purchase time - PartnerPurchase
    snapshots the resulting amount so historical numbers survive a later
    rate change, same pattern as banking.CashbackRule.
    """

    business = models.CharField(max_length=255, choices=BUSINESS_CATEGORY, unique=True)
    commission_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text="Percentage PicaDailys takes from each purchase in this category.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.business}: {self.commission_rate}%"


class PartnerPurchase(models.Model):
    """A member's purchase of a partner service."""

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="partner_purchases"
    )
    service = models.ForeignKey(
        PartnerServices, on_delete=models.CASCADE, related_name="purchases"
    )
    tx = models.ForeignKey(
        TxModel,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="partner_purchase_tx",
    )
    # Snapshotted from PartnerCommissionRule at purchase time - not recomputed
    # later, so historical figures don't shift if the rule's rate changes.
    commission_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    payout_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    # Whether the partner has confirmed receipt of the payout for this
    # purchase - used to detect Reconciliation Differences (money left the
    # user's wallet but the partner hasn't confirmed receipt after a grace
    # period). No automated flow sets this yet - it's flipped manually
    # (e.g. via Django admin) until a real settlement-confirmation flow
    # exists.
    settled = models.BooleanField(default=False)
    settled_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.user} purchased {self.service} — payout {self.payout_amount}"
