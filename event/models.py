"""
Event ticketing models: Event, Ticket, Purchase, Order, Codes, Transfers,
and partner settlement records.
"""

import uuid
import logging
import secrets
import string
import io
from datetime import timedelta
from decimal import Decimal

import qrcode
import cloudinary.uploader
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import F, Q
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from django.contrib.gis.db import models as gis_models
from django.contrib.gis.geos import Point


from accounts.models import User
from partners.models import PartnerCommissionRule, BUSINESS_CATEGORY
from banking.models import EncryptedCharField

logger = logging.getLogger(__name__)


class Event(models.Model):
    """Event details, lifecycle, and location."""

    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        IN_REVIEW = "in_review", _("In Review")
        REJECTED = "rejected", _("Rejected")
        ON_SALE = "on_sale", _("On Sale")
        EXPIRED = "expired", _("Expired")
        CANCELLED = "cancelled", _("Cancelled")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Core Details
    user = models.ForeignKey(
        to=User,
        on_delete=models.CASCADE,
        related_name="create_event",
        help_text="The partner who created and owns this event",
    )
    event_name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=280, unique=True, blank=True)
    description = models.TextField()
    category = models.CharField(
        max_length=255,
        choices=BUSINESS_CATEGORY,
        help_text="Must match partner's verified business category",
    )
    tags = models.JSONField(default=list, null=True, blank=True)

    # Location
    location = gis_models.PointField(
        geography=True,
        null=True,
        blank=True,
        spatial_index=True,
        help_text="Event location as a geographic point",
    )
    address = models.TextField(
        null=True, blank=True, help_text="Location, if Event is Physical"
    )
    mode = models.CharField(
        max_length=255,
        default="Physical",
        help_text="Event Mode: Physical, Online, or Hybrid",
    )
    link = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Link, if event is Online or Hybrid",
    )

    # Views
    view_count = models.PositiveIntegerField(default=0)

    # Media (Images/Videos)
    media = models.JSONField(default=list, null=True, blank=True)

    # Status, Date, and Timestamps
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True
    )
    rejection_reason = models.CharField(
        max_length=500,
        blank=True,
        default="",
        help_text="Set by admin when status is REJECTED",
    )
    reviewed_by = models.ForeignKey(
        to=User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_events",
        help_text="Admin who last actioned this event's review status",
    )
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    approved_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-approved_at", "-created_at"]
        indexes = [
            models.Index(fields=["status", "approved_at"]),
            models.Index(fields=["user", "status"]),
            models.Index(fields=["slug"]),
        ]

    def __str__(self) -> str:
        return self.event_name

    def save(self, *args, **kwargs) -> None:
        if not self.slug:
            # Use retry loop with random suffix to avoid race conditions
            base_slug = slugify(self.event_name)
            if not base_slug:
                base_slug = "event"

            # Try up to 5 times with random suffixes
            for attempt in range(5):
                if attempt == 0:
                    candidate = base_slug
                else:
                    random_suffix = secrets.token_hex(3)
                    candidate = f"{base_slug}-{random_suffix}"

                if not Event.objects.filter(slug=candidate).exists():
                    self.slug = candidate
                    break
            else:
                self.slug = f"{base_slug}-{uuid.uuid4().hex[:8]}"

        if self.status == self.Status.ON_SALE and self.approved_at is None:
            self.approved_at = timezone.now()

        if self.status == self.Status.CANCELLED and self.cancelled_at is None:
            self.cancelled_at = timezone.now()

        super().save(*args, **kwargs)

    @property
    def latitude(self):
        """Derive latitude from location."""
        if self.location:
            return self.location.y
        return None

    @property
    def longitude(self):
        """Derive longitude from location."""
        if self.location:
            return self.location.x
        return None

    def set_location(self, latitude, longitude):
        """Set location from lat/lng."""
        if latitude is not None and longitude is not None:
            self.location = Point(longitude, latitude, srid=4326)

    def update_view_count(self) -> None:
        Event.objects.filter(pk=self.pk).update(view_count=F("view_count") + 1)

    @property
    def is_on_sale(self) -> bool:
        return self.status == self.Status.ON_SALE

    @property
    def is_upcoming(self) -> bool:
        return self.start_date > timezone.now()

    @property
    def is_past(self) -> bool:
        return self.end_date < timezone.now()


class Ticket(models.Model):
    """Ticket type with pricing and capacity for an event."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    event = models.ForeignKey(
        to=Event, on_delete=models.CASCADE, related_name="create_ticket"
    )
    name = models.CharField(max_length=255, help_text="Ticket Name Eg: Regular")
    description = models.TextField(blank=True, default="")
    price = models.DecimalField(max_digits=14, decimal_places=2)
    slot_cap = models.PositiveIntegerField(
        default=0, help_text="Maximum number of slots available for this ticket"
    )
    slots_filled = models.PositiveIntegerField(
        default=0, help_text="Number of slots already filled"
    )
    unlimited_slots = models.BooleanField(
        default=False, help_text="Whether this ticket type has unlimited slots"
    )
    sales_start_date = models.DateTimeField(null=True, blank=True)
    sales_end_date = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(
        default=True, help_text="Whether this ticket type is currently purchasable"
    )
    min_purchase = models.PositiveIntegerField(default=1)
    max_purchase = models.PositiveIntegerField(default=10)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["price"]
        indexes = [
            models.Index(fields=["event", "is_active"]),
            models.Index(fields=["event", "sales_start_date", "sales_end_date"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} - {self.event.event_name}"

    def clean(self):
        if self.slot_cap and self.slots_filled > self.slot_cap:
            raise ValidationError("Slots filled cannot exceed slot cap")
        if self.min_purchase > self.max_purchase:
            raise ValidationError("Minimum purchase cannot exceed maximum")
        if self.sales_start_date and self.sales_end_date:
            if self.sales_end_date <= self.sales_start_date:
                raise ValidationError("Sales end date must be after start date")

    @property
    def available_slots(self) -> int | None:
        if self.unlimited_slots:
            return None
        return max(0, (self.slot_cap or 0) - (self.slots_filled or 0))

    @property
    def is_sold_out(self) -> bool:
        if self.unlimited_slots:
            return False
        return (self.slots_filled or 0) >= (self.slot_cap or 0)

    @property
    def is_on_sale(self) -> bool:
        if not self.is_active or self.is_sold_out or not self.event.is_on_sale:
            return False
        now = timezone.now()
        if self.sales_start_date and now < self.sales_start_date:
            return False
        if self.sales_end_date and now > self.sales_end_date:
            return False
        return True

    @transaction.atomic
    def reserve_slots(self, quantity: int) -> bool:
        """
        Atomically reserve slots using queryset update.
        Returns True if successful, False if insufficient slots.
        """
        if self.unlimited_slots:
            return True

        # Use select_for_update to lock the row
        locked_ticket = Ticket.objects.select_for_update().get(pk=self.pk)

        if locked_ticket.slots_filled + quantity > locked_ticket.slot_cap:
            return False

        # Use locked_ticket.slot_cap in the filter
        updated = Ticket.objects.filter(
            pk=self.pk, slots_filled__lte=locked_ticket.slot_cap - quantity
        ).update(slots_filled=F("slots_filled") + quantity, updated_at=timezone.now())

        # Refresh the instance to reflect the updated state
        self.refresh_from_db()

        return updated == 1


class TicketPurchase(models.Model):
    """Line item for a ticket purchase within an order."""

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        PAID = "paid", _("Paid")
        FAILED = "failed", _("Failed")
        REFUNDED = "refunded", _("Refunded")
        CANCELLED = "cancelled", _("Cancelled")
        EXPIRED = "expired", _("Expired")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payment_reference = models.CharField(
        max_length=255, blank=True, default="", help_text="Payment gateway reference"
    )
    order = models.ForeignKey(
        to="TicketOrder",
        on_delete=models.CASCADE,
        related_name="items",
        null=True,
        blank=True,
        help_text="The order this line item belongs to",
    )

    member = models.ForeignKey(
        to=User,
        on_delete=models.CASCADE,
        related_name="ticket_purchases",
        help_text="The member who bought the ticket(s)",
    )
    ticket = models.ForeignKey(
        to=Ticket, on_delete=models.CASCADE, related_name="purchases"
    )
    event = models.ForeignKey(
        to=Event, on_delete=models.CASCADE, related_name="ticket_purchases"
    )
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        help_text="Ticket price at the time of purchase",
    )
    total_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        help_text="unit_price * quantity, snapshotted at purchase time",
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True
    )

    purchased_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-purchased_at"]
        indexes = [
            models.Index(fields=["member", "status"]),
            models.Index(fields=["event", "status"]),
            models.Index(fields=["order", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.member} x{self.quantity} - {self.ticket.name}"

    def save(self, *args, **kwargs) -> None:
        if not self.event_id:
            self.event_id = self.ticket.event_id
        if not self.total_amount:
            self.total_amount = (self.unit_price or Decimal("0")) * (self.quantity or 0)
        super().save(*args, **kwargs)

    @property
    def is_paid(self) -> bool:
        return self.status == self.Status.PAID

    @property
    def is_within_transfer_window(self) -> bool:
        if not self.is_paid:
            return False
        config = TicketConfiguration.get_solo()
        window_end = self.purchased_at + config.transfer_window
        if self.event.start_date <= timezone.now():
            return False
        return timezone.now() <= window_end

    def mark_as_paid(self, tx_reference: str) -> None:
        """
        Mark purchase as paid and trigger QR code generation asynchronously.
        """
        from .tasks import generate_ticket_qr_async

        with transaction.atomic():
            purchase = TicketPurchase.objects.select_for_update().get(pk=self.pk)

            if purchase.status != TicketPurchase.Status.PENDING:
                return

            if not purchase.ticket.reserve_slots(purchase.quantity):
                purchase.status = TicketPurchase.Status.FAILED
                purchase.save(update_fields=["status", "updated_at"])
                raise ValueError(
                    f"Insufficient slots available for ticket: {purchase.ticket.name}"
                )

            purchase.status = TicketPurchase.Status.PAID
            purchase.payment_reference = tx_reference
            purchase.save(update_fields=["status", "payment_reference", "updated_at"])

            # Create ticket codes and trigger async QR generation
            codes = []
            for number in range(purchase.quantity):
                code = TicketCode(
                    purchase=purchase,
                    current_owner=purchase.member,
                )
                code.code = code._generate_unique_code()
                codes.append(code)

            TicketCode.objects.bulk_create(codes)

            # Trigger QR generation asynchronously
            for code in codes:
                transaction.on_commit(
                    lambda code_id=str(code.id): generate_ticket_qr_async.delay(code_id)
                )

            # Create partner sale record
            PartnerTicketSale.create_from_purchases([purchase])


class TicketOrder(models.Model):
    """Cart/checkout grouping multiple ticket purchases."""

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        PAID = "paid", _("Paid")
        FAILED = "failed", _("Failed")
        REFUNDED = "refunded", _("Refunded")
        CANCELLED = "cancelled", _("Cancelled")
        EXPIRED = "expired", _("Expired")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    member = models.ForeignKey(
        to=User,
        on_delete=models.CASCADE,
        related_name="ticket_orders",
        help_text="The member who placed this order",
    )
    event = models.ForeignKey(
        to=Event,
        on_delete=models.CASCADE,
        related_name="ticket_orders",
        help_text="The event this order is for",
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    total_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        help_text="Total amount for all items in this order",
    )
    payment_reference = models.CharField(
        max_length=255, blank=True, default="", help_text="Payment gateway reference"
    )
    idempotency_key = models.CharField(
        max_length=255,
        unique=True,
        null=True,
        blank=True,
        help_text="Client-provided key to prevent duplicate orders",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["member", "status"]),
            models.Index(fields=["event", "status"]),
            models.Index(fields=["idempotency_key"]),
        ]

    def __str__(self) -> str:
        return f"Order {self.id} - {self.member.get_full_name()}"

    def save(self, *args, **kwargs) -> None:
        if not self.expires_at and self.status == self.Status.PENDING:
            self.expires_at = timezone.now() + timedelta(minutes=30)
        super().save(*args, **kwargs)

    @property
    def is_paid(self) -> bool:
        return self.status == self.Status.PAID

    @property
    def is_expired(self) -> bool:
        if self.status != self.Status.PENDING:
            return False
        if not self.expires_at:
            return False
        return timezone.now() > self.expires_at

    def mark_as_paid(self, tx_reference: str) -> None:
        """
        Mark this order as paid and finalize all ticket purchases.
        QR generation happens asynchronously.
        """
        from .tasks import generate_ticket_qr_async

        with transaction.atomic():
            order = TicketOrder.objects.select_for_update().get(pk=self.pk)

            purchases = TicketPurchase.objects.select_for_update().filter(
                order=order, status=TicketPurchase.Status.PENDING
            )

            if not purchases.exists():
                if order.status == TicketOrder.Status.PENDING:
                    order.status = TicketOrder.Status.FAILED
                    order.save(update_fields=["status"])
                raise ValueError("No pending purchases found for this order")

            failed_purchases = []
            for purchase in purchases:
                if not purchase.ticket.reserve_slots(purchase.quantity):
                    failed_purchases.append(purchase)

            if failed_purchases:
                order.status = TicketOrder.Status.FAILED
                order.save(update_fields=["status", "updated_at"])

                for purchase in failed_purchases:
                    purchase.status = TicketPurchase.Status.FAILED
                    purchase.save(update_fields=["status", "updated_at"])

                raise ValueError(
                    f"Insufficient slots available for tickets: {', '.join(p.ticket.name for p in failed_purchases)}"
                )

            # Update all purchases
            all_codes = []
            for purchase in purchases:
                purchase.status = TicketPurchase.Status.PAID
                purchase.payment_reference = tx_reference
                purchase.save(
                    update_fields=["status", "payment_reference", "updated_at"]
                )

                codes = []
                for number in range(purchase.quantity):
                    code = TicketCode(
                        purchase=purchase,
                        current_owner=order.member,
                    )
                    code.code = code._generate_unique_code()
                    codes.append(code)

                TicketCode.objects.bulk_create(codes)
                all_codes.extend(codes)

            # Update order status
            order.status = TicketOrder.Status.PAID
            order.payment_reference = tx_reference
            order.save(update_fields=["status", "payment_reference", "updated_at"])

            # Trigger async QR generation for all codes
            for code in all_codes:
                transaction.on_commit(
                    lambda code_id=str(code.id): generate_ticket_qr_async.delay(code_id)
                )

            # Create partner sale records
            PartnerTicketSale.create_from_purchases(purchases)


# ── QR Code Helpers ─────────────────────────────────────────────────────────


def _make_ticket_code_prefix(purchase_id: str) -> str:
    alphabet = string.ascii_uppercase + string.digits
    alphabet = (
        alphabet.replace("O", "").replace("0", "").replace("I", "").replace("1", "")
    )
    suffix = "".join(secrets.choice(alphabet) for _ in range(6))
    return f"TKT-{suffix}"


def _make_unique_ticket_code() -> str:
    import secrets
    import string

    alphabet = string.ascii_uppercase + string.digits
    alphabet = (
        alphabet.replace("O", "").replace("0", "").replace("I", "").replace("1", "")
    )

    while True:
        suffix = "".join(secrets.choice(alphabet) for _ in range(6))
        candidate = f"TKT-{suffix}"
        if not TicketCode.objects.filter(code=candidate).exists():
            return candidate


def generate_ticket_qr_image_and_upload(token: str) -> str:
    """Generate QR code image and upload to Cloudinary."""
    qr_content = f"picadailys://ticket?token={token}"
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(qr_content)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    try:
        upload_result = cloudinary.uploader.upload(
            buffer,
            folder="ticket_qr",
            public_id=token,
            resource_type="image",
            overwrite=False,
        )
        return upload_result.get("secure_url", "")
    except Exception:
        logger.exception(
            "Failed to upload ticket QR code to Cloudinary for token %s", token
        )
        return ""


class TicketCode(models.Model):
    """Individual scannable ticket instance with QR code."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    purchase = models.ForeignKey(
        to=TicketPurchase, on_delete=models.CASCADE, related_name="codes"
    )
    current_owner = models.ForeignKey(
        to=User,
        on_delete=models.CASCADE,
        related_name="owned_ticket_codes",
        help_text=(
            "Current holder of this slot. Set to purchase.member on "
            "issuance and reassigned by TicketTransfer.accept()."
        ),
    )

    token = models.UUIDField(
        unique=True,
        default=uuid.uuid4,
        editable=False,
        db_index=True,
        help_text="Opaque value encoded into QR image; the primary check-in method",
    )

    qr_image_url = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        help_text="Cloudinary URL of the generated QR code image",
    )

    code = models.CharField(
        max_length=20,
        unique=True,
        blank=True,
        help_text="Short human-readable fallback code for manual entry",
    )

    is_checked_in = models.BooleanField(default=False)
    checked_in_at = models.DateTimeField(null=True, blank=True)
    checked_in_by = models.ForeignKey(
        to=User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="checked_in_tickets",
        help_text="Admin/Partner who scanned this ticket at the venue",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["token"]),
            models.Index(fields=["code"]),
            models.Index(fields=["current_owner", "is_checked_in"]),
        ]

    def __str__(self) -> str:
        return str(self.token)

    def save(self, *args, **kwargs) -> None:
        is_new = self._state.adding
        if is_new and not self.current_owner_id:
            self.current_owner_id = self.purchase.member_id

        if is_new and not self.code:
            self.code = self._generate_unique_code()

        super().save(*args, **kwargs)

        # QR generation is now handled by the async task, not here

    def _generate_unique_code(self) -> str:
        import secrets
        import string

        alphabet = string.ascii_uppercase + string.digits
        alphabet = (
            alphabet.replace("O", "").replace("0", "").replace("I", "").replace("1", "")
        )

        purchase_prefix = str(self.purchase_id)[:4] if self.purchase_id else "TKT"

        for number in range(10):
            suffix = "".join(secrets.choice(alphabet) for _ in range(6))
            candidate = f"{purchase_prefix}-{suffix}"
            if not TicketCode.objects.filter(code=candidate).exists():
                return candidate

        return f"TKT-{uuid.uuid4().hex[:8].upper()}"

    @classmethod
    def verify(
        cls, scanned_value: str, event_id: uuid.UUID | None = None
    ) -> "TicketCode | None":
        if not scanned_value:
            return None

        try:
            token_uuid = uuid.UUID(str(scanned_value))
            query = cls.objects.filter(token=token_uuid)
            if event_id:
                query = query.filter(purchase__event_id=event_id)
            return query.select_related(
                "purchase", "purchase__event", "purchase__ticket", "current_owner"
            ).first()
        except (ValueError, ValidationError):
            pass

        query = cls.objects.filter(code__iexact=scanned_value)
        if event_id:
            query = query.filter(purchase__event_id=event_id)
        return query.select_related(
            "purchase", "purchase__event", "purchase__ticket", "current_owner"
        ).first()

    def check_in(self, by: User) -> None:
        if self.is_checked_in:
            raise ValidationError("Ticket already checked in")
        if not self.purchase.is_paid:
            raise ValidationError("Cannot check in unpaid ticket")
        if self.purchase.event.end_date < timezone.now():
            raise ValidationError("Event has already ended")

        self.is_checked_in = True
        self.checked_in_at = timezone.now()
        self.checked_in_by = by
        self.save(update_fields=["is_checked_in", "checked_in_at", "checked_in_by"])


class TicketTransfer(models.Model):
    """Ownership transfer request for a single TicketCode."""

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        ACCEPTED = "accepted", _("Accepted")
        DECLINED = "declined", _("Declined")
        CANCELLED = "cancelled", _("Cancelled")
        EXPIRED = "expired", _("Expired")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    ticket_code = models.ForeignKey(
        to=TicketCode, on_delete=models.CASCADE, related_name="transfers"
    )
    from_user = models.ForeignKey(
        to=User, on_delete=models.CASCADE, related_name="ticket_transfers_sent"
    )
    to_user = models.ForeignKey(
        to=User, on_delete=models.CASCADE, related_name="ticket_transfers_received"
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    requested_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)
    invite_expires_at = models.DateTimeField(
        help_text="Auto-computed on creation from TicketConfiguration.transfer_invite_ttl"
    )

    class Meta:
        ordering = ["-requested_at"]
        indexes = [
            models.Index(fields=["ticket_code", "status"]),
            models.Index(fields=["to_user", "status"]),
        ]

    def __str__(self) -> str:
        return (
            f"{self.ticket_code_id}: {self.from_user} -> {self.to_user} ({self.status})"
        )

    def save(self, *args, **kwargs) -> None:
        if not self.invite_expires_at:
            config = TicketConfiguration.get_solo()
            self.invite_expires_at = timezone.now() + config.transfer_invite_ttl
        super().save(*args, **kwargs)

    @property
    def is_invite_expired(self) -> bool:
        return timezone.now() > self.invite_expires_at

    @transaction.atomic
    def accept(self) -> None:
        if self.status != self.Status.PENDING:
            raise ValidationError("Transfer is no longer pending")
        if self.is_invite_expired:
            self.status = self.Status.EXPIRED
            self.save(update_fields=["status", "responded_at"])
            raise ValidationError("Transfer invite has expired")

        self.status = self.Status.ACCEPTED
        self.responded_at = timezone.now()
        self.save(update_fields=["status", "responded_at"])

        TicketCode.objects.filter(pk=self.ticket_code_id).update(
            current_owner=self.to_user
        )

        TicketTransfer.objects.filter(
            ticket_code_id=self.ticket_code_id, status=self.Status.PENDING
        ).exclude(pk=self.pk).update(
            status=self.Status.CANCELLED, responded_at=timezone.now()
        )

    def decline(self) -> None:
        if self.status != self.Status.PENDING:
            raise ValidationError("Transfer is no longer pending")
        self.status = self.Status.DECLINED
        self.responded_at = timezone.now()
        self.save(update_fields=["status", "responded_at"])

    def cancel(self) -> None:
        if self.status != self.Status.PENDING:
            raise ValidationError("Transfer is no longer pending")
        self.status = self.Status.CANCELLED
        self.responded_at = timezone.now()
        self.save(update_fields=["status", "responded_at"])


class TicketConfiguration(models.Model):
    """
    Singleton configuration for global ticketing settings.

    This is a singleton model (only one instance exists, pk=1) that stores
    global settings like transfer windows. Admins can edit these values
    through the Django admin interface or the API endpoint.
    """

    transfer_window = models.DurationField(
        default=timedelta(hours=48),
        help_text="How long after purchase a member may initiate a ticket ownership transfer",
    )
    transfer_invite_ttl = models.DurationField(
        default=timedelta(hours=24),
        help_text="How long a transfer invite stays open for the recipient to accept/decline",
    )

    updated_by = models.ForeignKey(
        to=User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Ticket Configuration")
        verbose_name_plural = _("Ticket Configuration")

    def __str__(self) -> str:
        return "Ticket Configuration"

    def save(self, *args, **kwargs) -> None:
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs) -> None:
        pass

    @classmethod
    def get_solo(cls) -> "TicketConfiguration":
        obj, _created = cls.objects.get_or_create(pk=1)
        return obj

    @classmethod
    def get_platform_fee(cls, category: str) -> Decimal:
        """Get platform fee percentage from PartnerCommissionRule."""
        try:
            rule = PartnerCommissionRule.objects.get(business=category, is_active=True)
            return rule.commission_rate
        except PartnerCommissionRule.DoesNotExist:
            logger.warning(
                "No active PartnerCommissionRule found for category '%s'; defaulting fee to 5%%",
                category,
            )
            return Decimal("5.00")


class PartnerSaleWindow(models.Model):
    """Admin-granted window for partners to increase ticket capacity."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    partner = models.ForeignKey(
        to=User, on_delete=models.CASCADE, related_name="sale_windows"
    )
    event = models.ForeignKey(
        to=Event,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="sale_windows",
        help_text="Leave blank to grant across all of this partner's events",
    )
    granted_by = models.ForeignKey(
        to=User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="granted_sale_windows",
        help_text="Admin who granted this window",
    )
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    note = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["partner", "starts_at", "ends_at"]),
            models.Index(fields=["event", "starts_at"]),
        ]

    def __str__(self) -> str:
        scope = self.event.event_name if self.event_id else "all events"
        return f"{self.partner} - {scope}"

    def clean(self) -> None:
        if self.ends_at <= self.starts_at:
            raise ValidationError("ends_at must be after starts_at")
        if self.event and self.event.user_id != self.partner_id:
            raise ValidationError("Event does not belong to this partner")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    @property
    def is_active(self) -> bool:
        now = timezone.now()
        return self.starts_at <= now <= self.ends_at

    @classmethod
    def partner_can_increase_slots(cls, partner, event) -> bool:
        now = timezone.now()
        return (
            cls.objects.filter(partner=partner, starts_at__lte=now, ends_at__gte=now)
            .filter(Q(event=event) | Q(event__isnull=True))
            .exists()
        )


class PartnerTicketSale(models.Model):
    """
    Ledger entry for partner earnings from ticket sales.
    Uses PartnerCommissionRule for fee configuration.
    """

    class SettlementStatus(models.TextChoices):
        PENDING = "pending", _("Pending")
        SETTLED = "settled", _("Settled")
        ON_HOLD = "on_hold", _("On Hold")
        FAILED = "failed", _("Failed")
        REFUNDED = "refunded", _("Refunded")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    partner = models.ForeignKey(
        to=User,
        on_delete=models.CASCADE,
        related_name="ticket_sales",
        help_text="The partner (event owner) credited with this sale",
    )
    event = models.ForeignKey(
        to=Event, on_delete=models.CASCADE, related_name="sales_records"
    )
    ticket = models.ForeignKey(
        to=Ticket, on_delete=models.CASCADE, related_name="sales_records"
    )
    purchase = models.OneToOneField(
        to=TicketPurchase, on_delete=models.CASCADE, related_name="sale_record"
    )

    gross_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        help_text="Total amount paid by the member (== purchase.total_amount)",
    )
    platform_fee_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, help_text="Fee from PartnerCommissionRule"
    )
    platform_fee_amount = models.DecimalField(max_digits=14, decimal_places=2)
    net_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        help_text="Amount payable to the partner (gross_amount - platform_fee_amount)",
    )

    settlement_status = models.CharField(
        max_length=20,
        choices=SettlementStatus.choices,
        default=SettlementStatus.PENDING,
        db_index=True,
    )
    settled_at = models.DateTimeField(null=True, blank=True)
    payout_reference = models.CharField(max_length=255, blank=True, default="")
    settlement_attempts = models.PositiveIntegerField(default=0)
    last_settlement_error = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["partner", "settlement_status"]),
            models.Index(fields=["event", "settlement_status"]),
        ]

    def __str__(self) -> str:
        return f"{self.partner} - {self.gross_amount} ({self.settlement_status})"

    def save(self, *args, **kwargs) -> None:
        if not self.gross_amount and self.purchase_id:
            self.gross_amount = self.purchase.total_amount

        if not self.platform_fee_percentage:
            # Fee is keyed off the partner's verified business category, not the
            # partner-chosen event category, so it can't be gamed by picking a
            # lower-commission event category.
            fee_percentage = TicketConfiguration.get_platform_fee(
                self.event.user.business_category
            )
            self.platform_fee_percentage = fee_percentage
            self.platform_fee_amount = (self.gross_amount * fee_percentage) / Decimal(
                "100"
            )

        if not self.net_amount:
            self.net_amount = self.gross_amount - self.platform_fee_amount
        super().save(*args, **kwargs)

    @classmethod
    def create_from_purchases(cls, purchases):
        """Create PartnerTicketSale records for a list of purchases."""
        existing_purchase_ids = set(
            cls.objects.filter(purchase_id__in=[p.id for p in purchases]).values_list(
                "purchase_id", flat=True
            )
        )

        to_create = []
        for purchase in purchases:
            if str(purchase.id) not in existing_purchase_ids:
                fee_percentage = TicketConfiguration.get_platform_fee(
                    purchase.event.user.business_category
                )
                gross = purchase.total_amount
                fee_amount = (gross * fee_percentage) / Decimal("100")
                net = gross - fee_amount

                to_create.append(
                    cls(
                        purchase=purchase,
                        partner=purchase.event.user,
                        event=purchase.event,
                        ticket=purchase.ticket,
                        gross_amount=gross,
                        platform_fee_percentage=fee_percentage,
                        platform_fee_amount=fee_amount,
                        net_amount=net,
                    )
                )

        if to_create:
            cls.objects.bulk_create(to_create)

    @property
    def is_settled(self) -> bool:
        return self.settlement_status == self.SettlementStatus.SETTLED

    def mark_settled(self, payout_reference: str) -> None:
        self.settlement_status = self.SettlementStatus.SETTLED
        self.settled_at = timezone.now()
        self.payout_reference = payout_reference
        self.save(
            update_fields=[
                "settlement_status",
                "settled_at",
                "payout_reference",
                "updated_at",
            ]
        )


class EventPartnerProfile(models.Model):
    """
    Separate verification record that gates a partner's eligibility to create
    events and sell tickets.
    """

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        APPROVED = "approved", _("Approved")
        REJECTED = "rejected", _("Rejected")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    user = models.OneToOneField(
        to=User,
        on_delete=models.CASCADE,
        related_name="event_partner_profile",
        help_text="The partner this verification record belongs to",
    )

    # Identity (NIN)
    nin = EncryptedCharField(
        max_length=100,
        unique=True,
        help_text="National Identification Number (encrypted at rest)",
    )
    nin_verified = models.BooleanField(default=False)
    nin_name = models.CharField(
        max_length=200,
        null=True,
        blank=True,
        help_text="Full name returned by Dojah on successful NIN lookup",
    )
    nin_dob = models.CharField(
        max_length=40,
        blank=True,
        default="",
        help_text=(
            "Date of birth (ISO 8601) derived from Dojah's NIN response. "
            "Not collected from the partner."
        ),
    )

    # Business bank account
    bank_code = models.CharField(max_length=20)
    bank_name = models.CharField(max_length=150, blank=True, default="")
    bank_account_number = EncryptedCharField(
        max_length=30,
        help_text="Business bank account number (encrypted at rest)",
    )
    bank_account_name = models.CharField(
        max_length=200,
        null=True,
        blank=True,
        help_text="Name returned by 9PSB account lookup",
    )
    bank_verified = models.BooleanField(default=False)

    # Status / review
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    rejection_reason = models.CharField(
        max_length=500,
        blank=True,
        default="",
        help_text="Set by admin when status is REJECTED",
    )
    reviewed_by = models.ForeignKey(
        to=User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="event_partner_verifications_reviewed",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    submitted_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-submitted_at"]
        indexes = [
            models.Index(fields=["status", "submitted_at"]),
            models.Index(fields=["user", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.user} - {self.status}"

    # ---------------------------------------------------------------
    # Convenience
    # ---------------------------------------------------------------

    @property
    def is_approved(self) -> bool:
        return self.status == self.Status.APPROVED

    @property
    def is_pending(self) -> bool:
        return self.status == self.Status.PENDING

    @property
    def is_rejected(self) -> bool:
        return self.status == self.Status.REJECTED

    @classmethod
    def is_partner_verified(cls, user) -> bool:
        """
        The single source of truth used by the event permission gate.
        Returns True only when the user has an APPROVED profile.
        """
        return cls.objects.filter(
            user=user,
            status=cls.Status.APPROVED,
        ).exists()

    @staticmethod
    def names_match(submitted_name: str, verified_name: str) -> bool:
        """
        Case-insensitive, whitespace-normalized exact match.

        "John Doe"      vs "JOHN DOE"     -> True
        "John  Doe"     vs "John Doe"     -> True
        "John Doe"      vs "John Doe Ltd" -> False  (no substring matching)
        "  John Doe  "  vs "John Doe"     -> True
        """

        def _norm(s: str) -> str:
            return " ".join((s or "").strip().lower().split())

        return bool(submitted_name) and _norm(submitted_name) == _norm(verified_name)
