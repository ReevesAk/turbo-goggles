"""
event/models.py

Data model for the ticket module.

Roles involved:
    - Member  : the User who purchases a Ticket to attend an Event, and
                who may transfer a purchased slot to another member
                within the platform's configured transfer window.
    - Partner : the User who creates an Event and lists Tickets for
                sale against it; may be granted a time-boxed window by
                admin to increase slot capacity on an already
                approved/on-sale ticket. Partners also verify/check-in
                members at the event door using QR code scanning.
    - Admin   : reviews/approves Events, configures the transfer window,
                grants partner sale windows, and oversees payout
                settlement. Admins have system-wide oversight but do not
                perform door check-ins.
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
from django.utils.translation import gettext_lazy as _
from django.contrib.gis.db import models as gis_models

from accounts.models import User

logger = logging.getLogger(__name__)


class Event(models.Model):
    """
    Model for storing Event details.
    """

    class Status(models.TextChoices):
        """
        Review/lifecycle status for an event, set by the partner and
        moved forward by admin review.
        """

        DRAFT = "draft", _("Draft")
        IN_REVIEW = "in_review", _("In Review")
        REJECTED = "rejected", _("Rejected")
        ON_SALE = "on_sale", _("On Sale")
        EXPIRED = "expired", _("Expired")
        CANCELLED = "cancelled", _("Cancelled")  # Added missing status

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Core Details
    user = models.ForeignKey(
        to=User,
        on_delete=models.CASCADE,
        related_name="create_event",
        help_text="The partner who created and owns this event",
    )
    event_host = models.CharField(max_length=255, null=True, blank=True)
    business_name = models.CharField(max_length=255)
    business_type = models.CharField(max_length=255)
    event_name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=280, unique=True, blank=True)
    description = models.TextField()  # Changed from CharField(255) to TextField
    category = models.CharField(max_length=255, null=True, blank=True)
    tags = models.JSONField(default=list, null=True, blank=True)

    # Location
    mode = models.CharField(
        max_length=255,
        default="Physical",
        help_text="Event Mode Eg: Physical, Online or Hybrid",
    )
    link = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Link, if event is Online or Hybrid Eg: https://meet.google.com/asda-xed-ase",
    )
    address = models.TextField(
        null=True, blank=True, help_text="Location, if Event is Physical"
    )
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    location = gis_models.PointField(
        geography=True,
        null=True,
        blank=True,
        spatial_index=True,
        help_text="Derived automatically from latitude/longitude on save.",
    )

    # Views
    view_count = models.PositiveIntegerField(default=0)

    # media (Images/Videos)
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
    cancelled_at = models.DateTimeField(null=True, blank=True)  # Added
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-approved_at", "-created_at"]
        indexes = [
            models.Index(fields=["status", "approved_at"]),
            models.Index(fields=["user", "status"]),  # Added for partner queries
            models.Index(fields=["slug"]),  # Added for slug lookups
        ]

    def __str__(self) -> str:
        return self.event_name

    def save(self, *args, **kwargs) -> None:
        # Auto-generate slug if not provided
        if not self.slug:
            from django.utils.text import slugify

            base_slug = slugify(self.event_name)
            unique_slug = base_slug
            counter = 1
            while Event.objects.filter(slug=unique_slug).exists():
                unique_slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = unique_slug

        # Set location point from lat/lng
        if self.latitude and self.longitude:
            from django.contrib.gis.geos import Point

            self.location = Point(self.longitude, self.latitude, srid=4326)

        if self.status == self.Status.ON_SALE and self.approved_at is None:
            self.approved_at = timezone.now()

        if self.status == self.Status.CANCELLED and self.cancelled_at is None:
            self.cancelled_at = timezone.now()

        super().save(*args, **kwargs)

    def update_view_count(self) -> None:
        """Atomically increment view count."""
        Event.objects.filter(pk=self.pk).update(view_count=F("view_count") + 1)

    @property
    def is_on_sale(self) -> bool:
        """Check if event is currently on sale."""
        return self.status == self.Status.ON_SALE

    @property
    def is_upcoming(self) -> bool:
        """Check if event is upcoming."""
        return self.start_date > timezone.now()

    @property
    def is_past(self) -> bool:
        """Check if event has ended."""
        return self.end_date < timezone.now()


class Ticket(models.Model):
    """
    Model for storing ticket type and price attached to it for events.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    event = models.ForeignKey(
        to=Event, on_delete=models.CASCADE, related_name="create_ticket"
    )
    name = models.CharField(max_length=255, help_text="Ticket Name Eg: Regular")
    description = models.TextField(blank=True, default="")  # Changed to TextField
    price = models.DecimalField(max_digits=14, decimal_places=2)
    slot_cap = models.PositiveIntegerField(
        default=0, help_text="Maximum number of slots available for this task"
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
    min_purchase = models.PositiveIntegerField(default=1)  # Added
    max_purchase = models.PositiveIntegerField(default=10)  # Added
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
        """Validate ticket constraints."""
        # Skip validation if slots_filled is a CombinedExpression (from F() update)
        from django.db.models.expressions import CombinedExpression

        if isinstance(self.slots_filled, CombinedExpression):
            # Skip slot_cap validation during F() expression updates
            pass
        else:
            if self.slot_cap and self.slots_filled > self.slot_cap:
                raise ValidationError("Slots filled cannot exceed slot cap")

        if self.min_purchase > self.max_purchase:
            raise ValidationError("Minimum purchase cannot exceed maximum")
        if self.sales_start_date and self.sales_end_date:
            if self.sales_end_date <= self.sales_start_date:
                raise ValidationError("Sales end date must be after start date")

    def save(self, *args, **kwargs):
        # Only call clean if not using F() expressions
        if not kwargs.get("update_fields") or "slots_filled" not in kwargs.get(
            "update_fields", []
        ):
            self.clean()
        super().save(*args, **kwargs)

    @property
    def available_slots(self) -> int | None:
        """Return available slots or None for unlimited."""
        if self.unlimited_slots:
            return None
        return max(0, (self.slot_cap or 0) - (self.slots_filled or 0))

    @property
    def is_sold_out(self) -> bool:
        """Check if ticket type is sold out."""
        if self.unlimited_slots:
            return False
        return (self.slots_filled or 0) >= (self.slot_cap or 0)

    @property
    def is_on_sale(self) -> bool:
        """Check if ticket is currently on sale."""
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
        Atomically reserve slots to prevent race conditions.
        Returns True if successful, False if insufficient slots.
        """
        if self.unlimited_slots:
            return True

        locked_ticket = Ticket.objects.select_for_update().get(pk=self.pk)
        if locked_ticket.available_slots < quantity:
            return False

        locked_ticket.slots_filled = F("slots_filled") + quantity
        locked_ticket.save(update_fields=["slots_filled", "updated_at"])
        return True


class TicketPurchase(models.Model):
    """
    Records a member's purchase of one or more slots of a given Ticket.
    Acts as a line item within a TicketOrder (cart).
    """

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
        """Check if ticket is within transfer window."""
        if not self.is_paid:
            return False
        config = TicketConfiguration.get_solo()
        window_end = self.purchased_at + config.transfer_window
        if self.event.start_date <= timezone.now():
            return False
        return timezone.now() <= window_end

    def mark_as_paid(self, tx_reference: str) -> None:
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

            # Generate codes with proper code values BEFORE bulk_create
            codes = []
            for number in range(purchase.quantity):
                code_obj = TicketCode(
                    purchase=purchase,
                    current_owner=purchase.member,
                )
                # Generate code explicitly
                code_obj.code = code_obj._generate_unique_code()
                codes.append(code_obj)

            TicketCode.objects.bulk_create(codes)
            for code in codes:
                code.generate_and_upload_qr_code()

            PartnerTicketSale.create_from_purchases([purchase])


class TicketOrder(models.Model):
    """
    Represents a single checkout/payment transaction that may contain
    multiple ticket types (cart system).
    """

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
        """
        from django.db import transaction

        with transaction.atomic():
            # Lock the order for update
            order = TicketOrder.objects.select_for_update().get(pk=self.pk)

            # Get all pending purchases for this order
            purchases = TicketPurchase.objects.select_for_update().filter(
                order=order, status=TicketPurchase.Status.PENDING
            )

            if not purchases.exists():
                if order.status == TicketOrder.Status.PENDING:
                    order.status = TicketOrder.Status.FAILED
                    order.save(update_fields=["status"])
                raise ValueError("No pending purchases found for this order")

            # Process each purchase
            failed_purchases = []
            for purchase in purchases:
                # Reserve slots on the ticket
                if not purchase.ticket.reserve_slots(purchase.quantity):
                    failed_purchases.append(purchase)

            if failed_purchases:
                # Mark order as failed
                order.status = TicketOrder.Status.FAILED
                order.save(update_fields=["status", "updated_at"])

                # Mark affected purchases as failed
                for purchase in failed_purchases:
                    purchase.status = TicketPurchase.Status.FAILED
                    purchase.save(update_fields=["status", "updated_at"])

                raise ValueError(
                    f"Insufficient slots available for tickets: {', '.join(p.ticket.name for p in failed_purchases)}"
                )

            # Update all purchases
            for purchase in purchases:
                purchase.status = TicketPurchase.Status.PAID
                purchase.payment_reference = tx_reference
                purchase.save(
                    update_fields=["status", "payment_reference", "updated_at"]
                )

                # Generate ticket codes with proper code values BEFORE bulk_create
                codes = []
                for number in range(purchase.quantity):
                    code_obj = TicketCode(
                        purchase=purchase,
                        current_owner=order.member,
                    )
                    # Generate code explicitly
                    code_obj.code = code_obj._generate_unique_code()
                    codes.append(code_obj)

                TicketCode.objects.bulk_create(codes)

            # Update order status
            order.status = TicketOrder.Status.PAID
            order.payment_reference = tx_reference
            order.save(update_fields=["status", "payment_reference", "updated_at"])

            # Create partner sale records
            PartnerTicketSale.create_from_purchases(purchases)


# ── QR Code Helpers ─────────────────────────────────────────────────────────


def _make_ticket_code_prefix(purchase_id: str) -> str:
    """Generate a short code prefix for ticket codes, e.g. 'TKT-A3X9K2'."""
    alphabet = string.ascii_uppercase + string.digits
    # Remove confusing characters
    alphabet = (
        alphabet.replace("O", "").replace("0", "").replace("I", "").replace("1", "")
    )
    suffix = "".join(secrets.choice(alphabet) for _ in range(6))
    return f"TKT-{suffix}"


def _make_unique_ticket_code() -> str:
    """Generate a guaranteed-unique ticket code."""
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
    """
    Generate a QR code PNG for the given token, upload to Cloudinary,
    and return the secure URL.
    """
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
    """
    An individual, scannable ticket instance issued against a purchase.
    """

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
            # Generate unique code without relying on self.id
            self.code = self._generate_unique_code()

        super().save(*args, **kwargs)

        if is_new and not self.qr_image_url:
            self.generate_and_upload_qr_code()

    def _generate_unique_code(self) -> str:
        """Generate a guaranteed unique ticket code."""
        import secrets
        import string

        alphabet = string.ascii_uppercase + string.digits
        # Remove confusing characters
        alphabet = (
            alphabet.replace("O", "").replace("0", "").replace("I", "").replace("1", "")
        )

        # Use a combination of purchase ID (if available) and random suffix
        purchase_prefix = str(self.purchase_id)[:4] if self.purchase_id else "TKT"

        for number in range(10):
            suffix = "".join(secrets.choice(alphabet) for _ in range(6))
            candidate = f"{purchase_prefix}-{suffix}"
            if not TicketCode.objects.filter(code=candidate).exists():
                return candidate

        # Fallback: use UUID
        return f"TKT-{uuid.uuid4().hex[:8].upper()}"

    def generate_and_upload_qr_code(self) -> None:
        """Generate QR code and upload to Cloudinary."""
        qr_url = generate_ticket_qr_image_and_upload(str(self.token))
        if qr_url:
            self.qr_image_url = qr_url
            self.save(update_fields=["qr_image_url"])
            logger.info("QR code uploaded to Cloudinary for ticket %s", self.id)

    @classmethod
    def verify(
        cls, scanned_value: str, event_id: uuid.UUID | None = None
    ) -> "TicketCode | None":
        """
        Resolve a scanned/entered value to a TicketCode.
        Optionally validate against a specific event.
        """
        if not scanned_value:
            return None

        # Try UUID token first
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

        # Try fallback code
        query = cls.objects.filter(code__iexact=scanned_value)
        if event_id:
            query = query.filter(purchase__event_id=event_id)
        return query.select_related(
            "purchase", "purchase__event", "purchase__ticket", "current_owner"
        ).first()

    def check_in(self, by: User) -> None:
        """Mark this ticket as used at the venue."""
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
    """
    Records a request to move ownership of a single TicketCode.
    """

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
        """Accept transfer and reassign ownership atomically."""
        if self.status != self.Status.PENDING:
            raise ValidationError("Transfer is no longer pending")
        if self.is_invite_expired:
            self.status = self.Status.EXPIRED
            self.save(update_fields=["status", "responded_at"])
            raise ValidationError("Transfer invite has expired")

        self.status = self.Status.ACCEPTED
        self.responded_at = timezone.now()
        self.save(update_fields=["status", "responded_at"])

        # Update ticket owner
        TicketCode.objects.filter(pk=self.ticket_code_id).update(
            current_owner=self.to_user
        )

        # Cancel other pending transfers for this ticket
        TicketTransfer.objects.filter(
            ticket_code_id=self.ticket_code_id, status=self.Status.PENDING
        ).exclude(pk=self.pk).update(
            status=self.Status.CANCELLED, responded_at=timezone.now()
        )

    def decline(self) -> None:
        """Decline transfer."""
        if self.status != self.Status.PENDING:
            raise ValidationError("Transfer is no longer pending")
        self.status = self.Status.DECLINED
        self.responded_at = timezone.now()
        self.save(update_fields=["status", "responded_at"])

    def cancel(self) -> None:
        """Cancel transfer by sender."""
        if self.status != self.Status.PENDING:
            raise ValidationError("Transfer is no longer pending")
        self.status = self.Status.CANCELLED
        self.responded_at = timezone.now()
        self.save(update_fields=["status", "responded_at"])


class TicketConfiguration(models.Model):
    """
    Singleton, admin-editable settings for the ticketing module.
    """

    transfer_window = models.DurationField(
        default=timedelta(hours=48),
        help_text="How long after purchase a member may initiate a ticket ownership transfer",
    )
    transfer_invite_ttl = models.DurationField(
        default=timedelta(hours=24),
        help_text="How long a transfer invite stays open for the recipient to accept/decline",
    )
    max_tickets_per_purchase = models.PositiveIntegerField(default=10)
    platform_fee_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("5.00")
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


class PartnerSaleWindow(models.Model):
    """
    Admin-granted window during which a partner may increase ticket
    slot capacity beyond what was originally approved.
    """

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
        """Check if partner has active window to increase slots."""
        now = timezone.now()
        return (
            cls.objects.filter(partner=partner, starts_at__lte=now, ends_at__gte=now)
            .filter(Q(event=event) | Q(event__isnull=True))
            .exists()
        )


class PartnerTicketSale(models.Model):
    """
    Ledger entry recording a partner's earnings from a single ticket
    purchase, net of the platform fee, and tracking payout settlement.
    """

    class SettlementStatus(models.TextChoices):
        PENDING = "pending", _("Pending")
        SETTLED = "settled", _("Settled")
        ON_HOLD = "on_hold", _("On Hold")
        FAILED = "failed", _("Failed")
        REFUNDED = "refunded", _("Refunded")  # Added

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
        max_digits=5, decimal_places=2, default=Decimal("5.00")
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
    settlement_attempts = models.PositiveIntegerField(default=0)  # Added
    last_settlement_error = models.TextField(blank=True, default="")  # Added

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
        if not self.platform_fee_amount:
            config = TicketConfiguration.get_solo()
            self.platform_fee_percentage = config.platform_fee_percentage
            self.platform_fee_amount = (
                self.gross_amount * self.platform_fee_percentage
            ) / Decimal("100")
        if not self.net_amount:
            self.net_amount = self.gross_amount - self.platform_fee_amount
        super().save(*args, **kwargs)

    @classmethod
    def create_from_purchases(cls, purchases):
        """Create PartnerTicketSale records for a list of purchases."""
        for purchase in purchases:
            if not hasattr(purchase, "sale_record"):
                cls.objects.create(
                    purchase=purchase,
                    partner=purchase.event.user,
                    event=purchase.event,
                    ticket=purchase.ticket,
                    gross_amount=purchase.total_amount,
                )

    @property
    def is_settled(self) -> bool:
        return self.settlement_status == self.SettlementStatus.SETTLED

    def mark_settled(self, payout_reference: str) -> None:
        """Mark sale as settled."""
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
