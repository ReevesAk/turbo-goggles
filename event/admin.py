"""
Django admin configuration for the event/ticketing module.
"""

from django.contrib import admin

from .models import (
    Event,
    Ticket,
    TicketPurchase,
    TicketOrder,
    TicketCode,
    TicketTransfer,
    TicketConfiguration,
    PartnerSaleWindow,
    PartnerTicketSale,
)


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "event_name",
        "user",
        "status",
        "start_date",
        "end_date",
        "is_on_sale_display",
        "created_at",
    )
    list_filter = ("status", "mode", "category", "created_at")
    search_fields = ("event_name", "description", "user__email", "slug")
    readonly_fields = ("id", "slug", "view_count", "created_at", "updated_at")
    ordering = ("-created_at",)
    fieldsets = (
        (
            "Basic Information",
            {
                "fields": (
                    "id",
                    "user",
                    "event_name",
                    "slug",
                    "description",
                    "category",
                    "tags",
                )
            },
        ),
        ("Location", {"fields": ("mode", "link", "address", "location")}),
        (
            "Status",
            {
                "fields": (
                    "status",
                    "rejection_reason",
                    "reviewed_by",
                    "approved_at",
                    "cancelled_at",
                )
            },
        ),
        ("Dates", {"fields": ("start_date", "end_date", "created_at", "updated_at")}),
        ("Media & Stats", {"fields": ("media", "view_count")}),
    )

    def is_on_sale_display(self, obj):
        return obj.is_on_sale

    is_on_sale_display.boolean = True
    is_on_sale_display.short_description = "On Sale"


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "event",
        "price",
        "slot_cap",
        "slots_filled",
        "is_active",
        "is_sold_out_display",
        "created_at",
    )
    list_filter = ("is_active", "unlimited_slots", "event__status", "created_at")
    search_fields = ("name", "description", "event__event_name")
    readonly_fields = ("id", "slots_filled", "created_at", "updated_at")
    ordering = ("-created_at",)

    def is_sold_out_display(self, obj):
        return obj.is_sold_out

    is_sold_out_display.boolean = True
    is_sold_out_display.short_description = "Sold Out"


@admin.register(TicketPurchase)
class TicketPurchaseAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "member",
        "ticket",
        "event",
        "quantity",
        "total_amount",
        "status",
        "purchased_at",
    )
    list_filter = ("status", "purchased_at", "event__status")
    search_fields = (
        "member__email",
        "member__first_name",
        "member__last_name",
        "payment_reference",
    )
    readonly_fields = ("id", "purchased_at", "updated_at")
    ordering = ("-purchased_at",)


@admin.register(TicketOrder)
class TicketOrderAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "member",
        "event",
        "total_amount",
        "status",
        "payment_reference",
        "created_at",
    )
    list_filter = ("status", "created_at")
    search_fields = (
        "member__email",
        "member__first_name",
        "member__last_name",
        "payment_reference",
    )
    readonly_fields = ("id", "created_at", "updated_at")
    ordering = ("-created_at",)


@admin.register(TicketCode)
class TicketCodeAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "code",
        "purchase",
        "current_owner",
        "is_checked_in",
        "checked_in_at",
        "created_at",
    )
    list_filter = ("is_checked_in", "created_at")
    search_fields = ("code", "token", "current_owner__email")
    readonly_fields = ("id", "token", "created_at")
    ordering = ("-created_at",)
    fieldsets = (
        (
            "Ticket Code",
            {"fields": ("id", "code", "token", "purchase", "current_owner")},
        ),
        ("Check-in", {"fields": ("is_checked_in", "checked_in_at", "checked_in_by")}),
        ("Timestamps", {"fields": ("created_at",)}),
    )


@admin.register(TicketTransfer)
class TicketTransferAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "ticket_code",
        "from_user",
        "to_user",
        "status",
        "requested_at",
        "responded_at",
    )
    list_filter = ("status", "requested_at")
    search_fields = ("from_user__email", "to_user__email")
    readonly_fields = ("id", "requested_at")
    ordering = ("-requested_at",)


@admin.register(TicketConfiguration)
class TicketConfigurationAdmin(admin.ModelAdmin):
    """
    Admin configuration for the singleton TicketConfiguration.
    This is the primary way admins edit transfer windows.
    """

    list_display = (
        "id",
        "transfer_window_display",
        "transfer_invite_ttl_display",
        "updated_by",
        "updated_at",
    )
    readonly_fields = ("id", "updated_by", "updated_at")
    fieldsets = (
        ("Transfer Settings", {"fields": ("transfer_window", "transfer_invite_ttl")}),
        ("Audit", {"fields": ("id", "updated_by", "updated_at")}),
    )

    def has_add_permission(self, request):
        # Singleton - prevent adding multiple instances
        return not TicketConfiguration.objects.exists()

    def has_delete_permission(self, request, obj=None):
        # Singleton - prevent deletion
        return False

    def transfer_window_display(self, obj):
        return str(obj.transfer_window)

    transfer_window_display.short_description = "Transfer Window"

    def transfer_invite_ttl_display(self, obj):
        return str(obj.transfer_invite_ttl)

    transfer_invite_ttl_display.short_description = "Transfer Invite TTL"

    def save_model(self, request, obj, form, change):
        """Set updated_by when saving."""
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(PartnerSaleWindow)
class PartnerSaleWindowAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "partner",
        "event",
        "starts_at",
        "ends_at",
        "is_active_display",
        "created_at",
    )
    list_filter = ("created_at",)
    search_fields = ("partner__email", "partner__first_name", "partner__last_name")
    readonly_fields = ("id", "created_at")
    ordering = ("-created_at",)
    fieldsets = (
        ("Partner & Event", {"fields": ("partner", "event", "granted_by")}),
        ("Window", {"fields": ("starts_at", "ends_at", "note")}),
        ("Audit", {"fields": ("id", "created_at")}),
    )

    def is_active_display(self, obj):
        return obj.is_active

    is_active_display.boolean = True
    is_active_display.short_description = "Active"

    def save_model(self, request, obj, form, change):
        """Set granted_by when creating."""
        if not change:
            obj.granted_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(PartnerTicketSale)
class PartnerTicketSaleAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "partner",
        "event",
        "ticket",
        "gross_amount",
        "net_amount",
        "settlement_status",
        "settled_at",
    )
    list_filter = ("settlement_status", "created_at")
    search_fields = ("partner__email", "event__event_name", "payout_reference")
    readonly_fields = ("id", "created_at", "updated_at")
    ordering = ("-created_at",)
