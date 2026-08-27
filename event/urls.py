"""
ticket/urls.py

URL configuration for the ticket/event module.

URL Structure:
- / - Public event endpoints (member-facing)
- /tickets/ - Ticket purchase and management endpoints
- /partner/ - Partner-facing endpoints
- /admin/ - Admin-facing endpoints
"""

from django.urls import path

from . import views

app_name = "ticket"

urlpatterns = [
    # ==================
    # MEMBER ENDPOINTS
    # ==================
    # Event browsing
    path("", views.EventPublicListView.as_view(), name="events_list"),
    # Ticket purchase and management
    path(
        "tickets/purchase/",
        views.TicketPurchaseView.as_view(),
        name="ticket_purchase",
    ),
    path(
        "tickets/purchases/",
        views.MemberPurchaseListView.as_view(),
        name="member_purchases",
    ),
    # Cart-based purchase
    path(
        "tickets/cart-purchase/",
        views.TicketCartPurchaseView.as_view(),
        name="ticket_cart_purchase",
    ),
    # Member orders
    path(
        "tickets/orders/",
        views.MemberOrderListView.as_view(),
        name="member_orders",
    ),
    path(
        "tickets/my-codes/",
        views.MemberTicketCodesView.as_view(),
        name="member_ticket_codes",
    ),
    # Ticket transfers
    path(
        "tickets/transfer/request/",
        views.TicketTransferRequestView.as_view(),
        name="transfer_request",
    ),
    path(
        "tickets/transfer/pending/",
        views.PendingTransferRequestsView.as_view(),
        name="pending_transfers",
    ),
    path(
        "tickets/transfer/<uuid:id>/respond/",
        views.TicketTransferRespondView.as_view(),
        name="transfer_respond",
    ),
    path(
        "tickets/transfer/<uuid:id>/cancel/",
        views.TicketTransferCancelView.as_view(),
        name="transfer_cancel",
    ),
    # ==================
    # PARTNER ENDPOINTS
    # ==================
    # Event management
    path(
        "partner/",
        views.PartnerEventListView.as_view(),
        name="partner_event_list",
    ),
    path(
        "partner/<uuid:id>/",
        views.PartnerEventDetailView.as_view(),
        name="partner_event_detail",
    ),
    path(
        "partner/<uuid:id>/check-ins/",
        views.PartnerEventCheckInStatsView.as_view(),
        name="partner_event_check_ins",
    ),
    path(
        "partner/<uuid:event_id>/tickets/",
        views.PartnerEventTicketsView.as_view(),
        name="partner_event_tickets",
    ),
    # Ticket verification and management
    path(
        "partner/tickets/verify/",
        views.TicketVerifyView.as_view(),
        name="ticket_verify",
    ),
    path(
        "partner/tickets/verify/<uuid:event_id>/",
        views.TicketVerifyView.as_view(),
        name="ticket_verify_event",
    ),
    # Ticket management
    path(
        "partner/tickets/<uuid:id>/",
        views.PartnerTicketDetailView.as_view(),
        name="partner_ticket_detail",
    ),
    # Sales
    path(
        "partner/sales/",
        views.PartnerSalesLedgerView.as_view(),
        name="partner_sales",
    ),
    path(
        "partner/<uuid:id>/detailed-stats/",
        views.EventDetailedStatsView.as_view(),
        name="partner_event_detailed_stats",
    ),
    # =================
    # ADMIN ENDPOINTS
    # =================
    # Event management
    path(
        "admin/<uuid:id>/detailed-stats/",
        views.EventDetailedStatsView.as_view(),
        name="admin_event_detailed_stats",
    ),
    path(
        "admin/",
        views.AdminEventListView.as_view(),
        name="admin_events",
    ),
    path(
        "admin/<uuid:id>/review/",
        views.AdminEventReviewView.as_view(),
        name="admin_event_review",
    ),
    path(
        "admin/tickets/stats/",
        views.AdminTicketStatsView.as_view(),
        name="admin_ticket_stats",
    ),
    # Purchase management
    path(
        "admin/purchases/<uuid:id>/refund/",
        views.AdminRefundPurchaseView.as_view(),
        name="admin_refund_purchase",
    ),
    # Sale windows
    path(
        "admin/sale-windows/",
        views.AdminSaleWindowListView.as_view(),
        name="admin_sale_windows",
    ),
    path(
        "admin/sale-windows/create/",
        views.AdminPartnerSaleWindowView.as_view(),
        name="admin_create_sale_window",
    ),
    # Configuration
    path(
        "admin/ticket-config/",
        views.AdminTicketConfigurationView.as_view(),
        name="admin_ticket_config",
    ),
    path("<str:slug>/", views.EventPublicDetailView.as_view(), name="event_detail"),
    path(
        "<str:slug>/tickets/",
        views.EventTicketsListView.as_view(),
        name="event_tickets",
    ),
]
