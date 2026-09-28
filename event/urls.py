"""
event/urls.py

URL configuration for the event/ticketing module.

URL Structure:
- /v1/events/ - Public event endpoints (member-facing)
- /v1/events/tickets/ - Ticket purchase and management endpoints
- /v1/events/partner/ - Partner-facing endpoints
- /v1/events/admin/ - Admin-facing endpoints
"""

from django.urls import path

from . import views

app_name = "events"


urlpatterns = [
    # ==================
    # PARTNER ENDPOINTS
    # ==================
    path("partner/", views.PartnerEventListView.as_view(), name="partner_list"),
    path(
        "partner/<uuid:id>/",
        views.PartnerEventDetailView.as_view(),
        name="partner_detail",
    ),
    path(
        "partner/<uuid:id>/check-ins/",
        views.PartnerEventCheckInStatsView.as_view(),
        name="partner_check_ins",
    ),
    path(
        "partner/<uuid:event_id>/tickets/",
        views.PartnerEventTicketsView.as_view(),
        name="partner_tickets",
    ),
    path(
        "partner/tickets/<uuid:id>/",
        views.PartnerTicketDetailView.as_view(),
        name="partner_ticket_detail",
    ),
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
    path(
        "partner/sales/", views.PartnerSalesLedgerView.as_view(), name="partner_sales"
    ),
    path(
        "partner/<uuid:id>/detailed-stats/",
        views.EventDetailedStatsView.as_view(),
        name="partner_detailed_stats",
    ),
    path(
        "partner/verification/submit/",
        views.EventPartnerVerificationSubmitView.as_view(),
        name="partner_verification_submit",
    ),
    path(
        "partner/verification/status/",
        views.EventPartnerVerificationStatusView.as_view(),
        name="partner_verification_status",
    ),
    # ==================
    # ADMIN ENDPOINTS
    # ==================
    path("admin/", views.AdminEventListView.as_view(), name="admin_list"),
    path(
        "admin/<uuid:id>/review/",
        views.AdminEventReviewView.as_view(),
        name="admin_review",
    ),
    path(
        "admin/<uuid:id>/detailed-stats/",
        views.EventDetailedStatsView.as_view(),
        name="admin_detailed_stats",
    ),
    path(
        "admin/tickets/stats/", views.AdminTicketStatsView.as_view(), name="admin_stats"
    ),
    path(
        "admin/purchases/<uuid:id>/refund/",
        views.AdminRefundPurchaseView.as_view(),
        name="admin_refund",
    ),
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
    path(
        "admin/ticket-config/",
        views.AdminTicketConfigurationView.as_view(),
        name="admin_ticket_config",
    ),
    path(
        "admin/partner-verifications/",
        views.AdminEventPartnerVerificationListView.as_view(),
        name="admin_partner_verifications",
    ),
    path(
        "admin/partner-verifications/<uuid:id>/review/",
        views.AdminEventPartnerVerificationReviewView.as_view(),
        name="admin_partner_verification_review",
    ),
    # ==================
    # TICKET ENDPOINTS
    # ==================
    path("tickets/purchase/", views.TicketPurchaseView.as_view(), name="purchase"),
    path(
        "tickets/cart-purchase/",
        views.TicketCartPurchaseView.as_view(),
        name="cart_purchase",
    ),
    path(
        "tickets/purchases/", views.MemberPurchaseListView.as_view(), name="purchases"
    ),
    path("tickets/orders/", views.MemberOrderListView.as_view(), name="orders"),
    path("tickets/my-codes/", views.MemberTicketCodesView.as_view(), name="my_codes"),
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
    # PUBLIC ENDPOINTS
    # ==================
    path("", views.EventPublicListView.as_view(), name="list"),
    path("<str:slug>/", views.EventPublicDetailView.as_view(), name="detail"),
    path("<str:slug>/tickets/", views.EventTicketsListView.as_view(), name="tickets"),
]
