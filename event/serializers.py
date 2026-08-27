"""
event/serializers.py

Serializers for the event module, grouped by role.
"""

from django.utils import timezone
from rest_framework import serializers
from django.db.models import F, Q

from .models import (
    Event,
    PartnerSaleWindow,
    PartnerTicketSale,
    Ticket,
    TicketCode,
    TicketConfiguration,
    TicketOrder,
    TicketPurchase,
    TicketTransfer,
)

# ======
# Event
# ======


class EventPublicSerializer(serializers.ModelSerializer):
    """Read-only, member-facing view of an event."""

    tickets_available = serializers.SerializerMethodField()

    class Meta:
        model = Event
        fields = [
            "id",
            "business_name",
            "event_name",
            "slug",
            "description",
            "category",
            "tags",
            "mode",
            "link",
            "address",
            "media",
            "status",
            "start_date",
            "end_date",
            "view_count",
            "tickets_available",
        ]
        read_only_fields = fields

    def get_tickets_available(self, obj):
        """Return count of available ticket types."""
        now = timezone.now()
        return (
            obj.create_ticket.filter(
                is_active=True,
                event__status=Event.Status.ON_SALE,
            )
            .filter(
                Q(sales_start_date__isnull=True) | Q(sales_start_date__lte=now),
                Q(sales_end_date__isnull=True) | Q(sales_end_date__gte=now),
            )
            .exclude(Q(unlimited_slots=False) & Q(slot_cap__lte=F("slots_filled")))
            .count()
        )


class EventPartnerSerializer(serializers.ModelSerializer):
    """Create/update an event as its owning partner."""

    tickets_count = serializers.SerializerMethodField()
    total_sales = serializers.SerializerMethodField()

    class Meta:
        model = Event
        fields = [
            "id",
            "business_name",
            "business_type",
            "event_name",
            "slug",
            "description",
            "category",
            "tags",
            "mode",
            "link",
            "address",
            "media",
            "status",
            "rejection_reason",
            "start_date",
            "end_date",
            "view_count",
            "tickets_count",
            "total_sales",
        ]
        read_only_fields = [
            "id",
            "status",
            "rejection_reason",
            "view_count",
            "tickets_count",
            "total_sales",
        ]

    def get_tickets_count(self, obj):
        return obj.create_ticket.count()

    def get_total_sales(self, obj):
        from django.db.models import Sum

        total = obj.sales_records.filter(
            settlement_status__in=["pending", "settled"]
        ).aggregate(total=Sum("gross_amount"))["total"]
        return str(total or "0")

    def validate(self, attrs):
        start = attrs.get("start_date", getattr(self.instance, "start_date", None))
        end = attrs.get("end_date", getattr(self.instance, "end_date", None))
        if start and end and end <= start:
            raise serializers.ValidationError("end_date must be after start_date")

        # Validate start date is in future for new events
        if self.instance is None and start and start < timezone.now():
            raise serializers.ValidationError("start_date must be in the future")

        # Validate mode
        mode = attrs.get("mode", getattr(self.instance, "mode", "Physical"))
        link = attrs.get("link", getattr(self.instance, "link", None))
        address = attrs.get("address", getattr(self.instance, "address", None))

        if mode in ["Online", "Hybrid"] and not link:
            raise serializers.ValidationError(
                {"link": "Link is required for online or hybrid events."}
            )

        if mode in ["Physical", "Hybrid"] and not address:
            raise serializers.ValidationError(
                {"address": "Address is required for physical or hybrid events."}
            )

        return attrs

    def create(self, validated_data):
        validated_data["user"] = self.context["request"].user
        validated_data["status"] = Event.Status.IN_REVIEW
        return super().create(validated_data)


class EventAdminReviewSerializer(serializers.ModelSerializer):
    """Admin moves an event through Status (approve/reject)."""

    class Meta:
        model = Event
        fields = ["id", "status", "rejection_reason", "reviewed_by"]
        read_only_fields = ["id", "reviewed_by"]

    def validate_status(self, value):
        allowed = {
            Event.Status.ON_SALE,
            Event.Status.REJECTED,
            Event.Status.EXPIRED,
            Event.Status.CANCELLED,
        }
        if value not in allowed:
            raise serializers.ValidationError(
                f"Admin may only set status to one of {allowed}"
            )
        return value

    def validate(self, attrs):
        status = attrs.get("status")
        reason = attrs.get("rejection_reason", "")

        if status == Event.Status.REJECTED and not reason:
            raise serializers.ValidationError(
                {
                    "rejection_reason": "Rejection reason is required when rejecting an event."
                }
            )

        if status == Event.Status.ON_SALE:
            event = self.instance
            if event.start_date < timezone.now():
                raise serializers.ValidationError(
                    "Cannot approve event with past start date"
                )

        return attrs

    def update(self, instance, validated_data):
        validated_data["reviewed_by"] = self.context["request"].user
        return super().update(instance, validated_data)


# ========
# Ticket
# ========


class TicketPublicSerializer(serializers.ModelSerializer):
    """Read-only, member-facing view of a ticket type."""

    available_slots = serializers.SerializerMethodField()
    is_on_sale = serializers.BooleanField(read_only=True)
    event_name = serializers.CharField(source="event.event_name", read_only=True)

    class Meta:
        model = Ticket
        fields = [
            "id",
            "event",
            "event_name",
            "name",
            "description",
            "price",
            "available_slots",
            "is_on_sale",
            "sales_start_date",
            "sales_end_date",
            "min_purchase",
            "max_purchase",
        ]
        read_only_fields = fields

    def get_available_slots(self, obj):
        return obj.available_slots


class TicketPartnerSerializer(serializers.ModelSerializer):
    """Create/update a ticket type as the owning partner."""

    sold_count = serializers.SerializerMethodField()
    revenue = serializers.SerializerMethodField()

    class Meta:
        model = Ticket
        fields = [
            "id",
            "event",
            "name",
            "description",
            "price",
            "slot_cap",
            "slots_filled",
            "unlimited_slots",
            "sales_start_date",
            "sales_end_date",
            "is_active",
            "min_purchase",
            "max_purchase",
            "sold_count",
            "revenue",
        ]
        read_only_fields = ["id", "slots_filled", "sold_count", "revenue"]

    def get_sold_count(self, obj):
        return obj.slots_filled

    def get_revenue(self, obj):
        from django.db.models import Sum

        total = obj.sales_records.filter(
            settlement_status__in=["pending", "settled"]
        ).aggregate(total=Sum("gross_amount"))["total"]
        return str(total or "0")

    def validate_event(self, event):
        request = self.context["request"]
        if event.user_id != request.user.id:
            raise serializers.ValidationError("You do not own this event")
        return event

    def validate(self, attrs):
        instance = self.instance
        new_cap = attrs.get("slot_cap")
        is_increase = (
            instance is not None and new_cap is not None and new_cap > instance.slot_cap
        )
        if is_increase:
            partner = self.context["request"].user
            event = attrs.get("event", instance.event)
            if not PartnerSaleWindow.partner_can_increase_slots(partner, event):
                raise serializers.ValidationError(
                    {
                        "slot_cap": "No active grant permits increasing capacity on this ticket right now."
                    }
                )

        # Validate purchase limits
        min_purchase = attrs.get(
            "min_purchase", instance.min_purchase if instance else 1
        )
        max_purchase = attrs.get(
            "max_purchase", instance.max_purchase if instance else 10
        )
        if min_purchase > max_purchase:
            raise serializers.ValidationError(
                {"min_purchase": "Minimum purchase cannot exceed maximum purchase"}
            )

        # Validate sales dates
        sales_start = attrs.get(
            "sales_start_date", instance.sales_start_date if instance else None
        )
        sales_end = attrs.get(
            "sales_end_date", instance.sales_end_date if instance else None
        )
        if sales_start and sales_end and sales_end <= sales_start:
            raise serializers.ValidationError(
                {"sales_end_date": "Sales end date must be after start date"}
            )

        return attrs


# ==========
# Purchase
# ==========


class TicketPurchaseReadSerializer(serializers.ModelSerializer):
    """Member/partner-facing read view of a purchase."""

    ticket_name = serializers.CharField(source="ticket.name", read_only=True)
    event_name = serializers.CharField(source="event.event_name", read_only=True)
    ticket_codes = serializers.SerializerMethodField()
    order_id = serializers.UUIDField(source="order.id", read_only=True, default=None)

    class Meta:
        model = TicketPurchase
        fields = [
            "id",
            "order_id",
            "ticket",
            "ticket_name",
            "event",
            "event_name",
            "quantity",
            "unit_price",
            "total_amount",
            "status",
            "payment_reference",
            "purchased_at",
            "ticket_codes",
        ]
        read_only_fields = fields

    def get_ticket_codes(self, obj):
        if obj.status == TicketPurchase.Status.PAID:
            codes = obj.codes.all()
            return TicketCodeSerializer(codes, many=True, context=self.context).data
        return []


# ==========================================
# TicketCode (QR + fallback code, check-in)
# ==========================================


class TicketCodeSerializer(serializers.ModelSerializer):
    """A member's own ticket instance — QR image URL plus fallback code."""

    event_name = serializers.SerializerMethodField()
    ticket_name = serializers.SerializerMethodField()
    owner_name = serializers.SerializerMethodField()
    qr_code_url = serializers.SerializerMethodField()

    class Meta:
        model = TicketCode
        fields = [
            "id",
            "purchase",
            "current_owner",
            "token",
            "qr_code_url",
            "code",
            "is_checked_in",
            "checked_in_at",
            "event_name",
            "ticket_name",
            "owner_name",
        ]
        read_only_fields = fields

    def get_event_name(self, obj):
        return obj.purchase.event.event_name

    def get_ticket_name(self, obj):
        return obj.purchase.ticket.name

    def get_owner_name(self, obj):
        if hasattr(obj.current_owner, "full_name"):
            return obj.current_owner.full_name
        return f"{obj.current_owner.first_name} {obj.current_owner.last_name}".strip()

    def get_qr_code_url(self, obj):
        return obj.qr_image_url


class TicketVerifySerializer(serializers.Serializer):
    """
    Partner/door-staff input for checking a ticket in.
    Accepts either a scanned QR payload or the manually typed fallback code.
    """

    scanned_value = serializers.CharField(
        help_text="Raw QR payload (preferred) or the ticket's fallback code"
    )

    def validate_scanned_value(self, value):
        event_id = self.context.get("event_id")

        # Verify ticket exists
        code = TicketCode.verify(value, event_id)
        if code is None:
            raise serializers.ValidationError("No ticket matches this code.")

        request = self.context.get("request")
        if request and request.user.active_role == "Partner":
            event = code.purchase.event
            if event.user_id != request.user.id:
                raise serializers.ValidationError(
                    "You can only verify tickets for your own events."
                )
        # Check if already checked in
        if code.is_checked_in:
            raise serializers.ValidationError(
                f"Already checked in at {code.checked_in_at:%Y-%m-%d %H:%M}."
            )

        # Check if ticket is paid
        if not code.purchase.is_paid:
            raise serializers.ValidationError("This ticket has not been paid for.")

        # Check if event has ended
        if code.purchase.event.end_date < timezone.now():
            raise serializers.ValidationError("This event has already ended.")

        # Store in context
        self.context["ticket_code"] = code
        return value

    def save(self, **kwargs):
        code = self.context["ticket_code"]
        code.check_in(by=self.context["request"].user)
        return code


# ================
# TicketTransfer
# ================


class TicketTransferRequestSerializer(serializers.ModelSerializer):
    """Member requests to transfer one of their ticket codes to another member."""

    ticket_details = serializers.SerializerMethodField()

    class Meta:
        model = TicketTransfer
        fields = [
            "id",
            "ticket_code",
            "ticket_details",
            "to_user",
            "status",
            "requested_at",
            "invite_expires_at",
        ]
        read_only_fields = [
            "id",
            "status",
            "requested_at",
            "invite_expires_at",
            "ticket_details",
        ]

    def get_ticket_details(self, obj):
        return {
            "event_name": obj.ticket_code.purchase.event.event_name,
            "ticket_name": obj.ticket_code.purchase.ticket.name,
        }

    def validate_ticket_code(self, ticket_code):
        request = self.context["request"]
        if ticket_code.current_owner_id != request.user.id:
            raise serializers.ValidationError("You do not own this ticket.")
        if ticket_code.is_checked_in:
            raise serializers.ValidationError("This ticket has already been used.")
        if not ticket_code.purchase.is_within_transfer_window:
            raise serializers.ValidationError(
                "The transfer window for this ticket has closed."
            )
        if ticket_code.transfers.filter(status=TicketTransfer.Status.PENDING).exists():
            raise serializers.ValidationError(
                "A transfer is already pending for this ticket."
            )
        return ticket_code

    def validate_to_user(self, to_user):
        request = self.context["request"]
        if to_user == request.user:
            raise serializers.ValidationError("You cannot transfer to yourself.")
        return to_user

    def create(self, validated_data):
        validated_data["from_user"] = self.context["request"].user
        return super().create(validated_data)


class TicketTransferRespondSerializer(serializers.Serializer):
    """Recipient accepts or declines a pending transfer."""

    action = serializers.ChoiceField(choices=["accept", "decline"])

    def validate(self, attrs):
        transfer = self.context["transfer"]
        request = self.context["request"]

        if transfer.to_user_id != request.user.id:
            raise serializers.ValidationError("This transfer wasn't sent to you.")
        if transfer.status != TicketTransfer.Status.PENDING:
            raise serializers.ValidationError("This transfer is no longer pending.")
        if transfer.is_invite_expired:
            transfer.status = TicketTransfer.Status.EXPIRED
            transfer.responded_at = timezone.now()
            transfer.save(update_fields=["status", "responded_at"])
            raise serializers.ValidationError("This transfer invite has expired.")
        return attrs

    def save(self, **kwargs):
        transfer = self.context["transfer"]
        if self.validated_data["action"] == "accept":
            transfer.accept()
        else:
            transfer.decline()
        return transfer


# ================================================
# PartnerSaleWindow / TicketConfiguration (admin)
# ================================================


class PartnerSaleWindowSerializer(serializers.ModelSerializer):
    """Admin grants a partner a time-boxed window to increase slot capacity."""

    partner_name = serializers.CharField(source="partner.get_full_name", read_only=True)
    event_name = serializers.CharField(source="event.event_name", read_only=True)

    class Meta:
        model = PartnerSaleWindow
        fields = [
            "id",
            "partner",
            "partner_name",
            "event",
            "event_name",
            "starts_at",
            "ends_at",
            "note",
            "is_active",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "partner_name",
            "event_name",
            "is_active",
        ]

    def validate(self, attrs):
        if attrs["ends_at"] <= attrs["starts_at"]:
            raise serializers.ValidationError("ends_at must be after starts_at")

        if attrs["starts_at"] < timezone.now():
            raise serializers.ValidationError("starts_at must be in the future")

        event = attrs.get("event")
        partner = attrs.get("partner")
        if event and partner and event.user_id != partner.id:
            raise serializers.ValidationError(
                {"event": "Event does not belong to this partner."}
            )
        return attrs

    def create(self, validated_data):
        validated_data["granted_by"] = self.context["request"].user
        return super().create(validated_data)


class TicketConfigurationSerializer(serializers.ModelSerializer):
    """Admin reads/updates the singleton transfer-window settings."""

    class Meta:
        model = TicketConfiguration
        fields = [
            "transfer_window",
            "transfer_invite_ttl",
            "max_tickets_per_purchase",
            "platform_fee_percentage",
            "updated_by",
            "updated_at",
        ]
        read_only_fields = ["updated_by", "updated_at"]

    def validate_max_tickets_per_purchase(self, value):
        if value < 1:
            raise serializers.ValidationError("Must be at least 1")
        if value > 100:
            raise serializers.ValidationError("Cannot exceed 100 tickets per purchase")
        return value

    def validate_platform_fee_percentage(self, value):
        if value < 0 or value > 100:
            raise serializers.ValidationError("Must be between 0 and 100")
        return value

    def update(self, instance, validated_data):
        validated_data["updated_by"] = self.context["request"].user
        return super().update(instance, validated_data)


# ====================
# PartnerTicketSale
# ====================


class PartnerTicketSaleSerializer(serializers.ModelSerializer):
    """Read-only sales ledger row, for the owning partner or admin."""

    event_name = serializers.CharField(source="event.event_name", read_only=True)
    ticket_name = serializers.CharField(source="ticket.name", read_only=True)
    member_name = serializers.CharField(
        source="purchase.member.get_full_name", read_only=True
    )

    class Meta:
        model = PartnerTicketSale
        fields = [
            "id",
            "event",
            "event_name",
            "ticket",
            "ticket_name",
            "purchase",
            "member_name",
            "gross_amount",
            "platform_fee_amount",
            "net_amount",
            "settlement_status",
            "settled_at",
            "payout_reference",
            "created_at",
        ]
        read_only_fields = fields


# ====================
# Payment Serializers
# ====================


class TicketPaymentSerializer(serializers.Serializer):
    """Serializer for processing single ticket payments."""

    ticket = serializers.PrimaryKeyRelatedField(
        queryset=Ticket.objects.all(), help_text="UUID of the ticket to purchase"
    )
    quantity = serializers.IntegerField(
        min_value=1, default=1, help_text="Number of tickets to purchase"
    )
    payment_option = serializers.ChoiceField(
        choices=["WALLET", "CARD"], help_text="Payment method: WALLET or CARD"
    )
    pin = serializers.CharField(
        max_length=6,
        required=False,
        allow_blank=True,
        write_only=True,
        help_text="Wallet PIN (required for WALLET payment)",
    )
    use_biometrics = serializers.BooleanField(
        default=False,
        required=False,
        write_only=True,
        help_text="Use biometrics for wallet authentication",
    )
    card_reference = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True,
        write_only=True,
        help_text="Paystack transaction reference (required for CARD payment)",
    )
    idempotency_key = serializers.CharField(
        max_length=255,
        required=False,
        write_only=True,
        help_text="Client-provided unique key to prevent duplicate purchases",
    )

    def validate(self, attrs):
        payment_option = attrs.get("payment_option")
        pin = attrs.get("pin")
        use_biometrics = attrs.get("use_biometrics", False)
        card_reference = attrs.get("card_reference")

        if payment_option == "WALLET":
            if not pin and not use_biometrics:
                raise serializers.ValidationError(
                    {
                        "pin": "PIN is required for wallet payment when biometrics is not used."
                    }
                )
        elif payment_option == "CARD":
            if not card_reference:
                raise serializers.ValidationError(
                    {"card_reference": "Card reference is required for card payment."}
                )

        # Validate ticket availability
        ticket = attrs.get("ticket")
        quantity = attrs.get("quantity", 1)

        if ticket:
            if not ticket.is_on_sale:
                raise serializers.ValidationError(
                    {"ticket": "This ticket is not currently on sale."}
                )

            # Check purchase limits
            if quantity < ticket.min_purchase:
                raise serializers.ValidationError(
                    {
                        "quantity": f"Minimum purchase is {ticket.min_purchase} ticket(s)."
                    }
                )
            if quantity > ticket.max_purchase:
                raise serializers.ValidationError(
                    {"quantity": f"Maximum purchase is {ticket.max_purchase} tickets."}
                )

            # Check slot availability
            if not ticket.unlimited_slots and quantity > ticket.available_slots:
                raise serializers.ValidationError(
                    {"quantity": f"Only {ticket.available_slots} slot(s) remaining."}
                )

        return attrs


class TicketCartItemSerializer(serializers.Serializer):
    """Individual item in a ticket purchase cart."""

    ticket_id = serializers.UUIDField(help_text="UUID of the ticket to purchase")
    quantity = serializers.IntegerField(
        min_value=1, default=1, help_text="Number of tickets to purchase"
    )

    def validate_ticket_id(self, value):
        try:
            ticket = Ticket.objects.get(id=value, is_active=True)
        except Ticket.DoesNotExist:
            raise serializers.ValidationError("Ticket not found.")

        if not ticket.is_on_sale:
            raise serializers.ValidationError(
                f"Ticket '{ticket.name}' is not currently on sale."
            )

        return value

    def validate(self, attrs):
        ticket = Ticket.objects.get(id=attrs["ticket_id"])
        quantity = attrs["quantity"]

        # Check purchase limits
        if quantity < ticket.min_purchase:
            raise serializers.ValidationError(
                {"quantity": f"Minimum purchase is {ticket.min_purchase} ticket(s)."}
            )
        if quantity > ticket.max_purchase:
            raise serializers.ValidationError(
                {"quantity": f"Maximum purchase is {ticket.max_purchase} tickets."}
            )

        # Check slot availability
        if not ticket.unlimited_slots and quantity > ticket.available_slots:
            raise serializers.ValidationError(
                {
                    "quantity": f"Only {ticket.available_slots} slot(s) remaining for {ticket.name}."
                }
            )

        return attrs


class TicketCartPaymentSerializer(serializers.Serializer):
    """Serializer for processing cart-based ticket payments."""

    items = serializers.ListField(
        child=TicketCartItemSerializer(),
        min_length=1,
        max_length=20,
        help_text="List of ticket items to purchase",
    )
    payment_option = serializers.ChoiceField(
        choices=["WALLET", "CARD"], help_text="Payment method: WALLET or CARD"
    )
    pin = serializers.CharField(
        max_length=6,
        required=False,
        allow_blank=True,
        write_only=True,
        help_text="Wallet PIN (required for WALLET payment)",
    )
    use_biometrics = serializers.BooleanField(
        default=False,
        required=False,
        write_only=True,
        help_text="Use biometrics for wallet authentication",
    )
    card_reference = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True,
        write_only=True,
        help_text="Paystack transaction reference (required for CARD payment)",
    )
    idempotency_key = serializers.CharField(
        max_length=255,
        required=False,
        write_only=True,
        help_text="Client-provided unique key to prevent duplicate purchases",
    )

    def validate(self, attrs):
        payment_option = attrs.get("payment_option")
        pin = attrs.get("pin")
        use_biometrics = attrs.get("use_biometrics", False)
        card_reference = attrs.get("card_reference")

        if payment_option == "WALLET":
            if not pin and not use_biometrics:
                raise serializers.ValidationError(
                    {
                        "pin": "PIN is required for wallet payment when biometrics is not used."
                    }
                )
        elif payment_option == "CARD":
            if not card_reference:
                raise serializers.ValidationError(
                    {"card_reference": "Card reference is required for card payment."}
                )

        # Validate all items belong to the same event
        items = attrs.get("items", [])
        if items:
            event_ids = set()
            for item_data in items:
                ticket = Ticket.objects.select_related("event").get(
                    id=item_data["ticket_id"]
                )
                event_ids.add(ticket.event_id)

            if len(event_ids) > 1:
                raise serializers.ValidationError(
                    {"items": "All tickets must be from the same event."}
                )

        return attrs


class TicketOrderReadSerializer(serializers.ModelSerializer):
    """Read serializer for ticket orders (cart checkouts)."""

    items = serializers.SerializerMethodField()
    event_name = serializers.CharField(source="event.event_name", read_only=True)
    member_name = serializers.CharField(source="member.get_full_name", read_only=True)

    class Meta:
        model = TicketOrder
        fields = [
            "id",
            "event",
            "event_name",
            "member_name",
            "status",
            "total_amount",
            "payment_reference",
            "items",
            "created_at",
        ]
        read_only_fields = fields

    def get_items(self, obj):
        items = obj.items.all().select_related("ticket")
        return [
            {
                "ticket_id": str(item.ticket_id),
                "ticket_name": item.ticket.name,
                "quantity": item.quantity,
                "unit_price": str(item.unit_price),
                "total_amount": str(item.total_amount),
                "ticket_codes": (
                    TicketCodeSerializer(
                        item.codes.all(), many=True, context=self.context
                    ).data
                    if item.is_paid
                    else []
                ),
            }
            for item in items
        ]


# ==========================================
# Detailed Stats Serializers
# ==========================================


class TicketBuyerSerializer(serializers.Serializer):
    """Serializer for individual ticket buyer details."""

    first_name = serializers.CharField()
    last_name = serializers.CharField()
    email = serializers.CharField()
    quantity = serializers.IntegerField()
    total_amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    purchase_date = serializers.DateTimeField()
    payment_reference = serializers.CharField()


class TicketTypeBreakdownSerializer(serializers.Serializer):
    """Serializer for ticket type breakdown stats."""

    ticket_id = serializers.UUIDField()
    ticket_name = serializers.CharField()
    total_quantity = serializers.IntegerField()
    total_revenue = serializers.DecimalField(max_digits=14, decimal_places=2)
    buyers = TicketBuyerSerializer(many=True)


class EventDetailedStatsSerializer(serializers.Serializer):
    """Serializer for detailed event statistics."""

    event_id = serializers.UUIDField()
    event_name = serializers.CharField()
    total_tickets_sold = serializers.IntegerField()
    total_revenue = serializers.DecimalField(max_digits=14, decimal_places=2)
    total_buyers = serializers.IntegerField()
    ticket_breakdown = TicketTypeBreakdownSerializer(many=True)
