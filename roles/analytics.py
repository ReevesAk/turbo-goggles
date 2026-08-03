"""
Shared helpers for admin dashboard analytics: resolving a selected period
(daily/weekly/monthly/quarterly/yearly or a custom date range) and computing
the period-over-period trend badge every KPI tile needs.

Spec (agreed with product):
- Prior period is the immediately preceding period of equal length to
  whatever's selected - not a fixed calendar unit. E.g. selecting "monthly"
  9 days into the month compares against the 9 days before that, not the
  full previous calendar month.
- Trend is purely literal: current > prior -> up/green, current < prior ->
  down/red.
- prior == 0 -> no percentage is computed; the tile is labelled "New".
"""

from datetime import datetime, time, timedelta

from django.db.models import Avg, Count, Q, Sum, F, Window
from django.db.models.functions import ExtractHour, TruncDate, Lag
from django.utils import timezone

from accounts.models import TxModel, User
from adverts.models import CreateAd, TASK_TYPE_CHOICES
from banking.models import TransferModel, FundWithCard, Cashback, WalletModel
from vas.models import ValueAddedServices
from fmcg.models import FmcgOrder
from self_service.models import (
    RestaurantBooking,
    GymSubcription,
    CinemaBooking,
    CourierService,
    ConsumableService,
    LandTravels,
    Hotels,
)
from gamification.models import PointTransaction, Points, UserStreak
from tasks.models import BrandTaskSubmission, TaskSubmission
from support.models import Ticket
from user_profile.models import MemberSurvey
from partners.models import PartnerPurchase

GRANULARITY_CHOICES = ("daily", "weekly", "monthly", "quarterly", "yearly")

# tx_type values written by self-service bookings and partner-service
# purchases (both ride the same TxModel row - see self_service/views.py and
# partners/commission_service.py).
SELF_SERVICE_AND_PARTNER_TX_TYPES = [
    "Food",
    "Gym",
    "Cinema",
    "Courier",
    "Consumables",
    "Travel",
    "Hotel",
]

SELF_SERVICE_BOOKING_MODELS = [
    RestaurantBooking,
    GymSubcription,
    CinemaBooking,
    CourierService,
    ConsumableService,
    LandTravels,
    Hotels,
]

# tx_type values written by BrandChargeMixin (modules/billing_mixings.py) for
# ad-campaign creation and UGC task funding - see adverts/views.py and
# gamification/views.py.
BRAND_ADS_TX_TYPES = ["Brand Promotion", "UGC Task Funding"]

# CashbackRule.SERVICE_TYPE choices (banking/models.py) - the only category
# with an actual cashback mechanism today. Self Services, Partners, and Brand
# Ads have no cashback concept yet.
VAS_CASHBACK_SERVICE_TYPES = ["airtime", "data", "electricity", "cable"]

# VAS sub-category -> TxModel.tx_type, for the Services dashboard's VAS tab
# dropdown (Airtime Recharge / Data Top-Up / Bill Payments / Betting &
# Lottery). Bill Payments covers both electricity and cable - BillPaymentView
# (vas/views.py) writes both under the single tx_type "Bill Payment". Betting
# & Lottery has no purchase flow built yet, so it's always 0 - see
# get_vas_snapshot.
VAS_CATEGORY_TX_TYPES = {
    "airtime": "Airtime",
    "data": "Data",
    "bill_payments": "Bill Payment",
    "betting": None,
}

# VAS sub-category -> Cashback.service_type values that fund it.
# banking/cashback_service.py is only ever called with service="airtime"/
# "data" (vas/views.py) - electricity/cable purchases don't reward cashback
# at all today, so bill_payments nets to 0 in practice; kept explicit here
# for when that changes.
VAS_CATEGORY_CASHBACK_TYPES = {
    "airtime": ["airtime"],
    "data": ["data"],
    "bill_payments": ["electricity", "cable"],
    "betting": [],
}

# All tx_types that represent a real VAS purchase. TxModel is the actual
# purchase ledger (every VAS view writes a TxModel row on success);
# ValueAddedServices is only written by BillPaymentView as a
# provider-response audit log, so filtering VAS revenue through it
# undercounts - it misses Airtime/Data purchases entirely (see
# get_vas_snapshot).
VAS_TX_TYPES = [tx_type for tx_type in VAS_CATEGORY_TX_TYPES.values() if tx_type]


def get_transfer_sum(start, end, direction=None):
    qs = TransferModel.objects.filter(created_at__gte=start, created_at__lt=end)
    if direction == "inbound":
        qs = qs.filter(
            Q(transaction_type__in=["INBOUND", "CREDIT"])
            | Q(
                transaction_type="INTRA_BANK",
                beneficiary_account_number__isnull=False,
                sender_account_number__isnull=True,
            )
        )
    elif direction == "outbound":
        qs = qs.filter(
            Q(transaction_type__in=["OUTBOUND", "DEBIT"])
            | Q(transaction_type="INTRA_BANK", sender_account_number__isnull=False)
        )
    return float(qs.aggregate(total=Sum("amount")).get("total") or 0)


def get_card_deposit_sum(start, end):
    return float(
        FundWithCard.objects.filter(
            created_at__gte=start, created_at__lt=end, amount__isnull=False
        )
        .aggregate(total=Sum("amount"))
        .get("total")
        or 0
    )


def get_bill_payment_sum(start, end):
    """
    Despite the name (kept for get_cashflow_snapshot()'s existing
    "bill_payments" field), this is all VAS spend (Airtime + Data + Bill
    Payment) for [start, end) - see VAS_TX_TYPES/get_vas_snapshot.
    """
    return float(
        TxModel.objects.filter(
            date__gte=start,
            date__lt=end,
            status="SUCCESS",
            tx_type__in=VAS_TX_TYPES,
        )
        .aggregate(total=Sum("amount"))
        .get("total")
        or 0
    )


def get_self_service_and_partner_sum(start, end):
    return float(
        TxModel.objects.filter(
            date__gte=start,
            date__lt=end,
            status="SUCCESS",
            tx_type__in=SELF_SERVICE_AND_PARTNER_TX_TYPES,
        )
        .aggregate(total=Sum("amount"))
        .get("total")
        or 0
    )


def get_cashflow_snapshot(start, end):
    """Cash inflow/outflow/self-service+partner revenue for [start, end)."""
    inbound = get_transfer_sum(start, end, direction="inbound")
    outbound = get_transfer_sum(start, end, direction="outbound")
    card_deposit = get_card_deposit_sum(start, end)
    bill_payments = get_bill_payment_sum(start, end)
    self_service_and_partner = get_self_service_and_partner_sum(start, end)
    return {
        "inbound": inbound,
        "outbound": outbound,
        "card_deposit": card_deposit,
        "bill_payments": bill_payments,
        "self_service_and_partner_revenue": self_service_and_partner,
        # self-service/partner revenue isn't folded in here - "net cashflow"
        # and "revenue" aren't the same concept, and "Total Revenue" isn't
        # pinned down yet (see dashboard build notes).
        "net": inbound + card_deposit - outbound - bill_payments,
    }


def _daily_transfer_totals(start, end, direction):
    qs = TransferModel.objects.filter(created_at__gte=start, created_at__lt=end)
    if direction == "inbound":
        qs = qs.filter(
            Q(transaction_type__in=["INBOUND", "CREDIT"])
            | Q(
                transaction_type="INTRA_BANK",
                beneficiary_account_number__isnull=False,
                sender_account_number__isnull=True,
            )
        )
    else:
        qs = qs.filter(
            Q(transaction_type__in=["OUTBOUND", "DEBIT"])
            | Q(transaction_type="INTRA_BANK", sender_account_number__isnull=False)
        )
    rows = (
        qs.annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(total=Sum("amount"))
    )
    return {row["day"]: float(row["total"] or 0) for row in rows}


def _daily_bill_payment_totals(start, end):
    """Day-bucketed version of get_bill_payment_sum - see its docstring."""
    rows = (
        TxModel.objects.filter(
            date__gte=start,
            date__lt=end,
            status="SUCCESS",
            tx_type__in=VAS_TX_TYPES,
        )
        .annotate(day=TruncDate("date"))
        .values("day")
        .annotate(total=Sum("amount"))
    )
    return {row["day"]: float(row["total"] or 0) for row in rows}


def _daily_self_service_and_partner_totals(start, end):
    rows = (
        TxModel.objects.filter(
            date__gte=start,
            date__lt=end,
            status="SUCCESS",
            tx_type__in=SELF_SERVICE_AND_PARTNER_TX_TYPES,
        )
        .annotate(day=TruncDate("date"))
        .values("day")
        .annotate(total=Sum("amount"))
    )
    return {row["day"]: float(row["total"] or 0) for row in rows}


def get_daily_cashflow_series(start, end):
    """
    Cash In vs Cash Out, bucketed by calendar day, for every day in
    [start, end) - regardless of how wide the range is. Uses grouped
    aggregate queries (a handful total) rather than one query per day, so a
    yearly range doesn't turn into hundreds of round trips.

    cash_in = inbound transfers + card deposits.
    cash_out = outbound transfers + VAS bill payments + self-service/partner
    spend (all of these debit a user's wallet).
    """
    inbound_by_day = _daily_transfer_totals(start, end, direction="inbound")
    outbound_by_day = _daily_transfer_totals(start, end, direction="outbound")
    card_deposit_by_day = {
        row["day"]: float(row["total"] or 0)
        for row in (
            FundWithCard.objects.filter(
                created_at__gte=start, created_at__lt=end, amount__isnull=False
            )
            .annotate(day=TruncDate("created_at"))
            .values("day")
            .annotate(total=Sum("amount"))
        )
    }
    bill_payments_by_day = _daily_bill_payment_totals(start, end)
    self_service_by_day = _daily_self_service_and_partner_totals(start, end)

    series = []
    day = start.date()
    end_date = end.date()
    while day <= end_date:
        cash_in = inbound_by_day.get(day, 0) + card_deposit_by_day.get(day, 0)
        cash_out = (
            outbound_by_day.get(day, 0)
            + bill_payments_by_day.get(day, 0)
            + self_service_by_day.get(day, 0)
        )
        series.append(
            {
                "date": day.isoformat(),
                "day": day.strftime("%A"),
                "cash_in": cash_in,
                "cash_out": cash_out,
            }
        )
        day += timedelta(days=1)

    return series


def get_vas_snapshot(start, end, service_type=None):
    """
    VAS revenue + cashback for [start, end), sourced from TxModel (the
    actual purchase ledger - see VAS_TX_TYPES for why this isn't
    ValueAddedServices).

    service_type: one of VAS_CATEGORY_TX_TYPES's keys ("airtime", "data",
    "bill_payments", "betting") to scope to a single VAS sub-category, for
    the Services dashboard's VAS tab dropdown. None (default) sums all VAS
    sub-categories combined. "betting" has no purchase flow built yet, so
    it always contributes 0.
    """
    if service_type is not None:
        tx_type = VAS_CATEGORY_TX_TYPES[service_type]
        tx_types = [tx_type] if tx_type else []
        cashback_types = VAS_CATEGORY_CASHBACK_TYPES[service_type]
    else:
        tx_types = VAS_TX_TYPES
        cashback_types = VAS_CASHBACK_SERVICE_TYPES

    revenue = 0.0
    if tx_types:
        revenue = float(
            TxModel.objects.filter(
                date__gte=start,
                date__lt=end,
                status="SUCCESS",
                tx_type__in=tx_types,
            )
            .aggregate(total=Sum("amount"))
            .get("total")
            or 0
        )

    cashback = 0.0
    if cashback_types:
        cashback = float(
            Cashback.objects.filter(
                service_type__in=cashback_types,
                created_at__gte=start,
                created_at__lt=end,
            )
            .aggregate(total=Sum("amount"))
            .get("total")
            or 0
        )

    return {"revenue": revenue, "cashback": cashback}


def get_self_service_and_partner_split(start, end):
    """
    Splits self-service TxModel revenue by whether each booking is linked to
    a specific PartnerServices listing - mutually exclusive, so the two
    together equal get_self_service_and_partner_sum(start, end).
    """
    self_service_tx_ids = []
    partner_tx_ids = []
    for model in SELF_SERVICE_BOOKING_MODELS:
        self_service_tx_ids += list(
            model.objects.filter(
                tx__isnull=False, partner_service__isnull=True
            ).values_list("tx_id", flat=True)
        )
        partner_tx_ids += list(
            model.objects.filter(
                tx__isnull=False, partner_service__isnull=False
            ).values_list("tx_id", flat=True)
        )

    base_qs = TxModel.objects.filter(date__gte=start, date__lt=end, status="SUCCESS")

    self_service_total = float(
        base_qs.filter(id__in=self_service_tx_ids)
        .aggregate(total=Sum("amount"))
        .get("total")
        or 0
    )
    partner_total = float(
        base_qs.filter(id__in=partner_tx_ids)
        .aggregate(total=Sum("amount"))
        .get("total")
        or 0
    )
    return {"self_services": self_service_total, "partners": partner_total}


def get_brand_ads_sum(start, end):
    return float(
        TxModel.objects.filter(
            date__gte=start,
            date__lt=end,
            status="SUCCESS",
            tx_type__in=BRAND_ADS_TX_TYPES,
        )
        .aggregate(total=Sum("amount"))
        .get("total")
        or 0
    )


def get_services_snapshot(start, end):
    """
    Revenue for each Services-donut category for [start, end): vas,
    self_services, brand_ads, partners - plus vas_cashback (the only category
    with a real cashback mechanism today).
    """
    vas = get_vas_snapshot(start, end)
    split = get_self_service_and_partner_split(start, end)
    brand_ads = get_brand_ads_sum(start, end)

    return {
        "vas": vas["revenue"],
        "vas_cashback": vas["cashback"],
        "self_services": split["self_services"],
        "brand_ads": brand_ads,
        "partners": split["partners"],
    }


# ── Services dashboard tabs (All Services / VAS / Self Services / Brand
# Adverts) ────────────────────────────────────────────────────────────────
SERVICES_TAB_CHOICES = ("all", "vas", "self_services", "brand_ads")

# Self Services sub-category -> TxModel.tx_type(s), for the Services
# dashboard's Self Services tab dropdown. Travels and Leisure bundles Travel
# + Hotel - the Figma dropdown doesn't split them out separately. The
# dropdown/table mockup also showed an "Embassies" row that matches nothing
# in the schema - dropped as Figma placeholder noise, not a real category.
SELF_SERVICE_CATEGORY_TX_TYPES = {
    "travels_and_leisure": ["Travel", "Hotel"],
    "food_and_drinks": ["Food"],
    "delivery_services": ["Courier"],
    "consumables_services": ["Consumables"],
    "gym": ["Gym"],
    "cinema": ["Cinema"],
}

# category -> valid service_type keys, for query-param validation in views.py.
SERVICE_TYPE_CHOICES_BY_CATEGORY = {
    "vas": VAS_CATEGORY_TX_TYPES,
    "self_services": SELF_SERVICE_CATEGORY_TX_TYPES,
}


def _daily_tx_totals(start, end, tx_types, statuses):
    """Day-bucketed TxModel amount totals for the given tx_types/statuses."""
    if not tx_types:
        return {}
    rows = (
        TxModel.objects.filter(
            date__gte=start, date__lt=end, tx_type__in=tx_types, status__in=statuses
        )
        .annotate(day=TruncDate("date"))
        .values("day")
        .annotate(total=Sum("amount"))
    )
    return {row["day"]: float(row["total"] or 0) for row in rows}


def _daily_cashback_totals(start, end, service_types):
    if not service_types:
        return {}
    rows = (
        Cashback.objects.filter(
            created_at__gte=start, created_at__lt=end, service_type__in=service_types
        )
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(total=Sum("amount"))
    )
    return {row["day"]: float(row["total"] or 0) for row in rows}


def _category_tx_types(category, service_type=None):
    """tx_type list for a Services-dashboard category, plus the matching
    Cashback.service_type list (only VAS has one today)."""
    if category == "vas":
        if service_type is not None:
            tx_type = VAS_CATEGORY_TX_TYPES[service_type]
            return ([tx_type] if tx_type else []), VAS_CATEGORY_CASHBACK_TYPES[
                service_type
            ]
        return VAS_TX_TYPES, VAS_CASHBACK_SERVICE_TYPES
    if category == "self_services":
        if service_type is not None:
            return SELF_SERVICE_CATEGORY_TX_TYPES[service_type], []
        return SELF_SERVICE_AND_PARTNER_TX_TYPES, []
    if category == "brand_ads":
        return BRAND_ADS_TX_TYPES, []
    raise ValueError(
        f"Unknown category '{category}'. Expected one of {SERVICES_TAB_CHOICES}."
    )


def get_daily_income_expenditure_series(start, end, category="all", service_type=None):
    """
    Day-bucketed {date, day, cash_in, cash_out, cashback} for the Services
    dashboard's Cash Flow graph / Income vs Expenditure table (the
    frontend labels these Credit/Debit/Cash Back).

    category="all" (default) is the whole-platform figure: cash_in/cash_out
    keep get_daily_cashflow_series's existing wallet-transfer definition
    unchanged, with a "cashback" series (VAS cashback, the only category
    with a real mechanism) added on top.

    category in {"vas", "self_services", "brand_ads"}: a single service
    category has no natural wallet-in/wallet-out pair (a purchase is just
    revenue coming in), so cash_in = that category's successful revenue
    that day and cash_out = that category's failed/reversed amount that
    day. cashback is 0 for self_services/brand_ads - no mechanism exists.

    service_type only applies when category="vas" - see
    VAS_CATEGORY_TX_TYPES.
    """
    if category == "all":
        cashback_by_day = _daily_cashback_totals(start, end, VAS_CASHBACK_SERVICE_TYPES)
        series = []
        for row in get_daily_cashflow_series(start, end):
            day = datetime.strptime(row["date"], "%Y-%m-%d").date()
            series.append({**row, "cashback": cashback_by_day.get(day, 0)})
        return series

    tx_types, cashback_types = _category_tx_types(category, service_type)
    credit_by_day = _daily_tx_totals(start, end, tx_types, ["SUCCESS"])
    debit_by_day = _daily_tx_totals(start, end, tx_types, ["FAILED"])
    cashback_by_day = _daily_cashback_totals(start, end, cashback_types)

    series = []
    day = start.date()
    end_date = end.date()
    while day <= end_date:
        series.append(
            {
                "date": day.isoformat(),
                "day": day.strftime("%A"),
                "cash_in": credit_by_day.get(day, 0),
                "cash_out": debit_by_day.get(day, 0),
                "cashback": cashback_by_day.get(day, 0),
            }
        )
        day += timedelta(days=1)
    return series


def get_transaction_overview_snapshot(start, end, category="all", service_type=None):
    """
    Successful/duplicate/failed transaction counts + support ticket count
    for [start, end), optionally scoped to a Services-dashboard category.

    Support Contact is the total support.Ticket count created in the
    period - tickets aren't tagged by service category anywhere in the
    schema, so this figure is the same across every tab, not actually
    category-scoped (a real gap, not an oversight - there's nothing to
    scope it by today).

    Duplicate detection only covers TxModel-backed categories - VAS
    purchases live in a separate table with no duplicate-window logic
    built for it, so category="vas" always reports 0 duplicates.
    """
    if category == "all":
        tx_qs = TxModel.objects.filter(date__gte=start, date__lt=end)
        duplicate_count = get_duplicate_transaction_count(start, end)
    else:
        tx_types, _ = _category_tx_types(category, service_type)
        tx_qs = (
            TxModel.objects.filter(date__gte=start, date__lt=end, tx_type__in=tx_types)
            if tx_types
            else TxModel.objects.none()
        )
        duplicate_count = (
            0
            if category == "vas"
            else get_duplicate_transaction_count(start, end, tx_types=tx_types)
        )

    return {
        "successful_transactions": tx_qs.filter(status="SUCCESS").count(),
        "duplicate_transactions": duplicate_count,
        "failed_transactions": tx_qs.filter(status="FAILED").count(),
        "support_contact": Ticket.objects.filter(
            created_at__gte=start, created_at__lt=end
        ).count(),
    }


def _peak_hour_label(start, end, tx_types):
    """Busiest hour-of-day (by transaction count) among successful
    transactions of the given tx_types in [start, end), as a "H:00 AM/PM -
    H:00 AM/PM" one-hour window label. None if there's no data."""
    if not tx_types:
        return None
    row = (
        TxModel.objects.filter(
            date__gte=start, date__lt=end, status="SUCCESS", tx_type__in=tx_types
        )
        .annotate(hour=ExtractHour("date"))
        .values("hour")
        .annotate(total=Count("id"))
        .order_by("-total")
        .first()
    )
    if not row:
        return None
    hour = row["hour"]

    def fmt(h):
        period = "AM" if h < 12 else "PM"
        display_hour = h % 12 or 12
        return f"{display_hour}:00{period}"

    return f"{fmt(hour)} - {fmt((hour + 1) % 24)}"


def _top_customer_by_spend(start, end, tx_types):
    """Highest-spending user for the given tx_types in [start, end), with
    their transaction count. None if there's no data."""
    if not tx_types:
        return None
    row = (
        TxModel.objects.filter(
            date__gte=start, date__lt=end, status="SUCCESS", tx_type__in=tx_types
        )
        .values("user_id")
        .annotate(total_spend=Sum("amount"), transaction_count=Count("id"))
        .order_by("-total_spend")
        .first()
    )
    if not row or not row["user_id"]:
        return None
    user = User.objects.filter(id=row["user_id"]).first()
    return {
        "user_id": row["user_id"],
        "name": (
            f"{user.first_name or ''} {user.last_name or ''}".strip() if user else None
        ),
        "total_spend": float(row["total_spend"] or 0),
        "transaction_count": row["transaction_count"],
    }


def _top_vas_service(start, end):
    """VAS sub-category with the highest revenue in [start, end). None if
    there's no revenue at all in the period."""
    best = None
    for key, tx_type in VAS_CATEGORY_TX_TYPES.items():
        if not tx_type:
            continue
        revenue = float(
            TxModel.objects.filter(
                date__gte=start, date__lt=end, status="SUCCESS", tx_type=tx_type
            )
            .aggregate(total=Sum("amount"))
            .get("total")
            or 0
        )
        if revenue and (best is None or revenue > best["revenue"]):
            best = {"service": key, "revenue": revenue}
    return best


# Only these self-service booking models have a venue/business name field
# (RestaurantBooking.name/GymSubcription.name/CinemaBooking.name) -
# CourierService/ConsumableService/LandTravels/Hotels don't store one at
# all, so they can never win "Top Service" on the Self Services tab.
NAMED_SELF_SERVICE_MODELS = {
    "Food": RestaurantBooking,
    "Gym": GymSubcription,
    "Cinema": CinemaBooking,
}


def _top_named_self_service_venue(start, end):
    """Best-selling named venue (Restaurant/Gym/Cinema booking) by revenue
    in [start, end). None if none of these three categories had any
    successful, named bookings in the period."""
    best = None
    for model in NAMED_SELF_SERVICE_MODELS.values():
        row = (
            model.objects.filter(
                tx__date__gte=start,
                tx__date__lt=end,
                tx__status="SUCCESS",
                name__isnull=False,
            )
            .exclude(name="")
            .values("name")
            .annotate(total=Sum("tx__amount"))
            .order_by("-total")
            .first()
        )
        if row and row["total"] and (best is None or row["total"] > best["revenue"]):
            best = {"name": row["name"], "revenue": float(row["total"])}
    return best


def get_customer_insight_extended(start, end, prior_start, prior_end, category="all"):
    """
    Customer Insight for the Services dashboard tabs - a different shape
    per tab (distinct from get_customer_insight_snapshot, which powers the
    separate top-level Customer Insight panel).

    category="all": Users/Brands are running totals (as of `end`, trended
    against the same totals as of `prior_end`) of AccountType.user_type
    "Member"/"BrandAd" accounts.

    category in {"vas", "self_services", "brand_ads"}: active_users
    (distinct users with a successful transaction in the period), peak_time
    (busiest one-hour window), plus a category-specific "what" metric:
    top_customer/top_service for vas and self_services (top_service is a
    VAS sub-category for vas, but a specific venue name for self_services -
    see _top_named_self_service_venue), top_task_type/top_ad for brand_ads.
    """
    if category == "all":
        users_now = (
            User.objects.filter(
                is_deleted=False,
                account_types__user_type="Member",
                date_joined__lt=end,
            )
            .distinct()
            .count()
        )
        users_prior = (
            User.objects.filter(
                is_deleted=False,
                account_types__user_type="Member",
                date_joined__lt=prior_end,
            )
            .distinct()
            .count()
        )
        brands_now = (
            User.objects.filter(
                is_deleted=False,
                account_types__user_type="BrandAd",
                date_joined__lt=end,
            )
            .distinct()
            .count()
        )
        brands_prior = (
            User.objects.filter(
                is_deleted=False,
                account_types__user_type="BrandAd",
                date_joined__lt=prior_end,
            )
            .distinct()
            .count()
        )
        return {
            "users": compute_trend(users_now, users_prior),
            "brands": compute_trend(brands_now, brands_prior),
        }

    if category == "vas":
        tx_types = VAS_TX_TYPES
        active_users = (
            TxModel.objects.filter(
                date__gte=start, date__lt=end, status="SUCCESS", tx_type__in=tx_types
            )
            .values("user_id")
            .distinct()
            .count()
        )
        return {
            "active_users": active_users,
            "peak_time": _peak_hour_label(start, end, tx_types),
            "top_customer": _top_customer_by_spend(start, end, tx_types),
            "top_service": _top_vas_service(start, end),
        }

    if category == "self_services":
        tx_types = SELF_SERVICE_AND_PARTNER_TX_TYPES
        active_users = (
            TxModel.objects.filter(
                date__gte=start, date__lt=end, status="SUCCESS", tx_type__in=tx_types
            )
            .values("user_id")
            .distinct()
            .count()
        )
        return {
            "active_users": active_users,
            "peak_time": _peak_hour_label(start, end, tx_types),
            "top_customer": _top_customer_by_spend(start, end, tx_types),
            "top_service": _top_named_self_service_venue(start, end),
        }

    if category == "brand_ads":
        tx_types = BRAND_ADS_TX_TYPES
        active_users = (
            TxModel.objects.filter(
                date__gte=start, date__lt=end, status="SUCCESS", tx_type__in=tx_types
            )
            .values("user_id")
            .distinct()
            .count()
        )
        top_task = (
            CreateAd.objects.filter(created_at__gte=start, created_at__lt=end)
            .values("task_type")
            .annotate(engagement=Sum("slots_filled"))
            .order_by("-engagement")
            .first()
        )
        top_ad = (
            CreateAd.objects.filter(created_at__gte=start, created_at__lt=end)
            .order_by("-slots_filled")
            .first()
        )
        task_type_labels = dict(TASK_TYPE_CHOICES)
        return {
            "active_users": active_users,
            "peak_time": _peak_hour_label(start, end, tx_types),
            "top_task_type": (
                {
                    "task_type": top_task["task_type"],
                    "label": task_type_labels.get(
                        top_task["task_type"], top_task["task_type"]
                    ),
                    "engagement": top_task["engagement"] or 0,
                }
                if top_task and top_task["task_type"]
                else None
            ),
            "top_ad": (
                {
                    "campaign_name": top_ad.campaign_name,
                    "engagement": top_ad.slots_filled or 0,
                }
                if top_ad
                else None
            ),
        }

    raise ValueError(
        f"Unknown category '{category}'. Expected one of {SERVICES_TAB_CHOICES}."
    )


# Ads never actually reward cashback anywhere in the codebase - stubbed at
# 0, same treatment as fraud_alerts/reconciliation_differences before those
# were built out.
ADS_CASH_BACKS = 0


def get_ads_insight_snapshot(start, end):
    """
    Brand Adverts tab's Ads Insight donut: Created (ads created this
    period), Ongoing (currently active as of `end`), Expired (no longer
    running as of `end`), Cash Backs (always 0 - no mechanism exists).
    Not a strict partition - an ad created this period can also be
    ongoing - each is its own independent count, not a mutually exclusive
    slice; percentage is only a rough proportion for the donut, not a
    precise "share of all ads" figure.
    """
    created = CreateAd.objects.filter(created_at__gte=start, created_at__lt=end).count()
    ongoing = CreateAd.objects.filter(is_active=True, expiry_date__gt=end).count()
    expired = CreateAd.objects.filter(
        Q(is_active=False) | Q(expiry_date__lte=end), created_at__lt=end
    ).count()

    counts = {
        "created": created,
        "ongoing": ongoing,
        "expired": expired,
        "cash_backs": ADS_CASH_BACKS,
    }
    total = sum(counts.values())
    return {
        key: {
            "value": value,
            "percentage": round(value / total * 100, 2) if total else 0,
        }
        for key, value in counts.items()
    }


# "Active" = logged in within this many days. Below that (or never logged
# in) counts as "Dormant".
ACTIVE_USER_THRESHOLD_DAYS = 90


def get_customer_insight_snapshot(start, end, now=None):
    """
    New/Deleted are period-scoped (date_joined/deleted_at within [start,
    end)) so they're trend-comparable against a prior period. Active/Dormant
    are current-moment snapshots based on last_login and are NOT
    period-scoped: only the single most recent login timestamp is stored (no
    login history), so a past period's active count can't be reconstructed -
    trend badges don't apply to them.
    """
    now = now or timezone.now()
    active_cutoff = now - timedelta(days=ACTIVE_USER_THRESHOLD_DAYS)

    new_users = User.objects.filter(
        date_joined__gte=start, date_joined__lt=end, is_deleted=False
    ).count()
    deleted_users = User.objects.filter(
        deleted_at__gte=start, deleted_at__lt=end
    ).count()
    active_users = User.objects.filter(
        is_deleted=False, last_login__gte=active_cutoff
    ).count()
    dormant_users = (
        User.objects.filter(is_deleted=False)
        .filter(Q(last_login__lt=active_cutoff) | Q(last_login__isnull=True))
        .count()
    )

    return {
        "new_users": new_users,
        "deleted_users": deleted_users,
        "active_users": active_users,
        "dormant_users": dormant_users,
    }


def get_pending_settlement_count():
    """
    Current backlog of transactions stuck in PENDING - a snapshot, not
    period-scoped (a transaction pending since last week is still pending
    now; scoping this to "created within the selected range" would hide it).
    """
    return TxModel.objects.filter(status="PENDING").count()


# Same user + tx_type + amount within this many minutes counts as a
# duplicate. A heuristic, not a real dedup concept - there's no first-class
# "this transaction is a duplicate of that one" tracking in the schema.
DUPLICATE_TRANSACTION_WINDOW_MINUTES = 10


def get_duplicate_transaction_pairs(start, end, tx_types=None):
    """
    Returns (duplicate_tx, original_tx) TxModel object pairs for
    [start, end) - same heuristic as before (same user + tx_type + amount
    within DUPLICATE_TRANSACTION_WINDOW_MINUTES of each other), but
    materializes the actual rows instead of just counting, so the
    Duplicate Transactions drill-down (list + two-sided detail) can be
    built from it. Uses a window function (partition by user/tx_type/
    amount, ordered by date) to find each row's previous same-group
    timestamp and id in one query, then bulk-fetches the objects.

    tx_types: optional list to scope detection to a Services-dashboard
    category (e.g. SELF_SERVICE_AND_PARTNER_TX_TYPES). Note this only
    covers TxModel-backed categories - VAS purchases aren't in this
    window at all yet (see get_transaction_overview_snapshot).
    """
    window = timedelta(minutes=DUPLICATE_TRANSACTION_WINDOW_MINUTES)
    qs = TxModel.objects.filter(date__gte=start, date__lt=end)
    if tx_types is not None:
        qs = qs.filter(tx_type__in=tx_types)
    rows = qs.annotate(
        prev_date=Window(
            expression=Lag("date"),
            partition_by=[F("user_id"), F("tx_type"), F("amount")],
            order_by=F("date").asc(),
        ),
        prev_id=Window(
            expression=Lag("id"),
            partition_by=[F("user_id"), F("tx_type"), F("amount")],
            order_by=F("date").asc(),
        ),
    ).values("id", "date", "prev_date", "prev_id")

    id_pairs = [
        (row["id"], row["prev_id"])
        for row in rows
        if row["prev_date"] and (row["date"] - row["prev_date"]) < window
    ]
    if not id_pairs:
        return []

    all_ids = {tx_id for pair in id_pairs for tx_id in pair}
    tx_by_id = TxModel.objects.select_related("user").in_bulk(all_ids)
    return [
        (tx_by_id[dup_id], tx_by_id[orig_id])
        for dup_id, orig_id in id_pairs
        if dup_id in tx_by_id and orig_id in tx_by_id
    ]


def get_duplicate_transaction_count(start, end, tx_types=None):
    """
    Counts transactions in [start, end) that look like an accidental repeat
    of an immediately preceding one from the same user. See
    get_duplicate_transaction_pairs for the actual heuristic.
    """
    return len(get_duplicate_transaction_pairs(start, end, tx_types=tx_types))


# tx_type -> which side of the wallet it moves money on. Everything not
# listed defaults to Debit (a spend) - Credit is the exception, not the rule.
CREDIT_TX_TYPES = {"Points Redemption to Wallet", "Transfer to Picadailys Account"}

WALLET_CATEGORY_TX_TYPES = {
    "Points Redemption to Wallet",
    "Transfer to Picadailys Account",
    "Transfer to Bank Account",
}


def _get_partner_linked_tx_ids(start, end):
    """tx_ids of self-service bookings that ARE linked to a PartnerServices
    listing - same distinction ServicesBreakdownView uses to split Self
    Services from Partners."""
    ids = set()
    for model in SELF_SERVICE_BOOKING_MODELS:
        ids.update(
            model.objects.filter(
                tx__isnull=False, partner_service__isnull=False
            ).values_list("tx_id", flat=True)
        )
    return ids


def _wallet_info_by_user(user_ids):
    """
    Bulk {user_id: (wallet_name, wallet_number)} lookup - avoids an N+1
    query when building a list of transaction rows that each need the
    transacting user's wallet name/number (the "Transaction Details" modal
    fields on the Alert and Risk drill-downs).
    """
    wallets = WalletModel.objects.filter(
        user_id__in=user_ids, walletType="INDIVIDUAL"
    ).values("user_id", "acct_name", "account_number")
    return {w["user_id"]: (w["acct_name"], w["account_number"]) for w in wallets}


def get_all_transactions(start, end, status_filter=None, category_filter=None):
    """
    Merges TxModel + ValueAddedServices (VAS) + FmcgOrder into one
    normalized, date-descending transaction list. These are three
    differently-shaped models - this is a Python-side merge, not a DB
    UNION, since the schemas don't line up column-for-column and VAS/FMCG
    don't write to TxModel at all.

    account_type is the transacting user's active_role (Member/Partner/
    BrandAd/etc) - a different concept from category (which service bucket
    the transaction belongs to). Both are returned since the Alert and Risk
    drill-down mockups use "Category" to mean account type, while this
    endpoint's existing `category` filter already means the service bucket.
    """
    partner_linked_tx_ids = _get_partner_linked_tx_ids(start, end)
    rows = []

    tx_qs = TxModel.objects.filter(date__gte=start, date__lt=end).select_related("user")
    vas_qs = ValueAddedServices.objects.filter(
        created_at__gte=start, created_at__lt=end
    ).select_related("user")
    fmcg_qs = FmcgOrder.objects.filter(
        created_at__gte=start, created_at__lt=end
    ).select_related("user")

    user_ids = (
        {tx.user_id for tx in tx_qs if tx.user_id}
        | {vas.user_id for vas in vas_qs if vas.user_id}
        | {order.user_id for order in fmcg_qs if order.user_id}
    )
    wallet_by_user = _wallet_info_by_user(user_ids)

    for tx in tx_qs:
        if tx.tx_type in SELF_SERVICE_AND_PARTNER_TX_TYPES:
            category = "Partners" if tx.id in partner_linked_tx_ids else "Self Services"
        elif tx.tx_type in BRAND_ADS_TX_TYPES:
            category = "Brand Ads"
        elif tx.tx_type in WALLET_CATEGORY_TX_TYPES:
            category = "Wallet"
        else:
            category = "Other"

        wallet_name, wallet_number = wallet_by_user.get(tx.user_id, (None, None))
        rows.append(
            {
                "transaction_id": tx.tx_reference or str(tx.id),
                "user": tx.user.phone_number if tx.user_id else None,
                "service": tx.tx_type,
                "category": category,
                "account_type": tx.user.active_role if tx.user_id else None,
                "amount": float(tx.amount or 0),
                "status": tx.status,
                "date": tx.date,
                "type": "Credit" if tx.tx_type in CREDIT_TX_TYPES else "Debit",
                "wallet_name": wallet_name,
                "wallet_number": wallet_number,
            }
        )

    for vas in vas_qs:
        try:
            amount = float(vas.amount or 0)
        except (TypeError, ValueError):
            amount = 0
        wallet_name, wallet_number = wallet_by_user.get(vas.user_id, (None, None))
        rows.append(
            {
                "transaction_id": str(vas.tx_reference),
                "user": vas.user.phone_number if vas.user_id else None,
                "service": vas.category_name or vas.network or "VAS",
                "category": "VAS",
                "account_type": vas.user.active_role if vas.user_id else None,
                "amount": amount,
                "status": vas.status,
                "date": vas.created_at,
                "type": "Debit",
                "wallet_name": wallet_name,
                "wallet_number": wallet_number,
            }
        )

    for order in fmcg_qs:
        wallet_name, wallet_number = wallet_by_user.get(order.user_id, (None, None))
        rows.append(
            {
                "transaction_id": str(order.tx_reference),
                "user": order.user.phone_number if order.user_id else None,
                "service": order.product or "FMCG",
                "category": "FMCG",
                "account_type": order.user.active_role if order.user_id else None,
                "amount": float(order.total_price or 0),
                "status": order.status,
                "date": order.created_at,
                "type": "Debit",
                "wallet_name": wallet_name,
                "wallet_number": wallet_number,
            }
        )

    if status_filter:
        rows = [
            r
            for r in rows
            if r["status"] and r["status"].lower() == status_filter.lower()
        ]
    if category_filter:
        rows = [r for r in rows if r["category"].lower() == category_filter.lower()]

    min_date = datetime.min.replace(tzinfo=timezone.get_current_timezone())
    rows.sort(key=lambda r: r["date"] or min_date, reverse=True)

    for row in rows:
        row["date"] = row["date"].isoformat() if row["date"] else None

    return rows


def _start_of_granularity(granularity, now):
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    if granularity == "daily":
        return today_start
    if granularity == "weekly":
        return today_start - timezone.timedelta(days=today_start.weekday())
    if granularity == "monthly":
        return today_start.replace(day=1)
    if granularity == "quarterly":
        quarter_start_month = ((today_start.month - 1) // 3) * 3 + 1
        return today_start.replace(month=quarter_start_month, day=1)
    if granularity == "yearly":
        return today_start.replace(month=1, day=1)

    raise ValueError(
        f"Unknown granularity '{granularity}'. Expected one of {GRANULARITY_CHOICES}."
    )


def resolve_period(granularity=None, start_date=None, end_date=None, now=None):
    """
    Returns (current_start, current_end, prior_start, prior_end) - all naive
    datetimes (project runs with USE_TZ = False), end exclusive.

    Pass either `granularity` (one of GRANULARITY_CHOICES) or an explicit
    `start_date`/`end_date` pair (date objects) for a custom range.
    """
    now = now or timezone.now()

    if start_date and end_date:
        current_start = datetime.combine(start_date, time.min)
        current_end = datetime.combine(end_date, time.max)
    elif granularity:
        current_start = _start_of_granularity(granularity, now)
        current_end = now
    else:
        raise ValueError("Must pass either granularity or start_date/end_date.")

    length = current_end - current_start
    prior_end = current_start
    prior_start = current_start - length

    return current_start, current_end, prior_start, prior_end


def compute_trend(current_value, prior_value):
    """
    Returns {"value", "change_pct", "direction", "label"} for a single KPI.
    direction is "up" / "down" / "flat"; label is "New" when prior_value is 0
    (change_pct/direction are None in that case - nothing to compare against).
    """
    current_value = current_value or 0
    prior_value = prior_value or 0

    if prior_value == 0:
        return {
            "value": current_value,
            "change_pct": None,
            "direction": None,
            "label": "New",
        }

    change_pct = (current_value - prior_value) / prior_value * 100
    if current_value > prior_value:
        direction = "up"
    elif current_value < prior_value:
        direction = "down"
    else:
        direction = "flat"

    return {
        "value": current_value,
        "change_pct": round(change_pct, 2),
        "direction": direction,
        "label": None,
    }


def get_picapoints_overview_snapshot(start, end):
    """
    Picapoints Overview: Created is points awarded (PointTransaction.AWARD)
    and Distributed is points redeemed to wallet (PointTransaction.DEDUCT,
    source="points_redemption") in [start, end). auto_boost_points is
    stubbed at None - UserGeneratedContent.auto_boost_points exists as a
    config field on UGC task creation but nothing in the codebase ever reads
    it to actually award points, so there's no real figure to report.
    avg_points_in_circulation is a current-moment snapshot (average
    Points.balance across all users), not period-scoped - same treatment as
    Customer Insight's active/dormant counts.
    """
    created = (
        PointTransaction.objects.filter(
            created_at__gte=start,
            created_at__lt=end,
            transaction_type=PointTransaction.AWARD,
        )
        .aggregate(total=Sum("amount"))
        .get("total")
        or 0
    )
    distributed = (
        PointTransaction.objects.filter(
            created_at__gte=start,
            created_at__lt=end,
            transaction_type=PointTransaction.DEDUCT,
            source="points_redemption",
        )
        .aggregate(total=Sum("amount"))
        .get("total")
        or 0
    )
    avg_points_in_circulation = (
        Points.objects.aggregate(avg=Avg("balance")).get("avg") or 0
    )
    return {
        "created": created,
        "distributed": distributed,
        "auto_boost_points": None,
        "avg_points_in_circulation": round(avg_points_in_circulation, 2),
    }


def get_partner_ecosystem_revenue(start, end):
    """
    Partner Ecosystem: Picadailys's commission cut from one partner buying
    another partner's PartnerServices listing through self-service - the
    buyer is a Partner-type account rather than a Member. Self-service
    booking views (self_service.views.partner_booking_rejection) enforce
    that a Partner can only book partner-linked listings in the first
    place, so every such PartnerPurchase row is, by construction, a
    partner-to-partner engagement.
    """
    return float(
        PartnerPurchase.objects.filter(
            created_at__gte=start,
            created_at__lt=end,
            user__account_types__user_type="Partner",
        )
        .aggregate(total=Sum("commission_amount"))
        .get("total")
        or 0
    )


def get_task_insight_snapshot(start, end):
    """
    Task Insight participant counts - distinct users who engaged in each
    task category during [start, end) - plus partner_ecosystem, which is a
    revenue figure (Picadailys's commission cut), not a participant count.
    See get_partner_ecosystem_revenue.
    """
    brand_task = (
        BrandTaskSubmission.objects.filter(created_at__gte=start, created_at__lt=end)
        .values("user")
        .distinct()
        .count()
    )
    in_app_task = (
        TaskSubmission.objects.filter(created_at__gte=start, created_at__lt=end)
        .values("user")
        .distinct()
        .count()
    )
    streaks = (
        UserStreak.objects.filter(joined_at__gte=start, joined_at__lt=end)
        .values("user")
        .distinct()
        .count()
    )
    return {
        "brand_task": brand_task,
        "in_app_task": in_app_task,
        "streaks": streaks,
        "partner_ecosystem": get_partner_ecosystem_revenue(start, end),
    }


def _get_per_user_revenue(start, end):
    """
    Per-user revenue for [start, end), using the same definition as
    ServicesBreakdownView: vas + self_services + brand_ads + partners - all
    sourced from TxModel. Returns {user_id: total_revenue}.
    """
    revenue_by_user = {}

    tx_rows = (
        TxModel.objects.filter(
            date__gte=start,
            date__lt=end,
            status="SUCCESS",
            tx_type__in=VAS_TX_TYPES
            + SELF_SERVICE_AND_PARTNER_TX_TYPES
            + BRAND_ADS_TX_TYPES,
        )
        .values("user_id")
        .annotate(total=Sum("amount"))
    )
    for row in tx_rows:
        if row["user_id"]:
            revenue_by_user[row["user_id"]] = revenue_by_user.get(
                row["user_id"], 0
            ) + float(row["total"] or 0)

    return revenue_by_user


def _bucket_revenue(revenue_by_user, key_by_user_id):
    """Groups {user_id: revenue} into {bucket_label: total_revenue}, using
    "Unspecified" for any user missing from key_by_user_id (no survey
    completed, no state on file, etc.)."""
    totals = {}
    for user_id, amount in revenue_by_user.items():
        label = key_by_user_id.get(user_id) or "Unspecified"
        totals[label] = totals.get(label, 0) + amount
    return totals


def _totals_to_breakdown(totals):
    grand_total = sum(totals.values())
    rows = [
        {
            "label": label,
            "revenue": amount,
            "percentage": round(amount / grand_total * 100, 2) if grand_total else 0,
        }
        for label, amount in totals.items()
    ]
    rows.sort(key=lambda row: row["revenue"], reverse=True)
    return rows


def get_demographic_breakdown_snapshot(start, end):
    """
    Revenue by Location/Gender/Age for [start, end). Revenue is the same
    combined figure as ServicesBreakdownView (vas + self_services +
    brand_ads + partners), attributed to the transacting user. Location
    comes from User.state (required at registration - good coverage). "
    Gender/Age come from MemberSurvey.sex/age_bracket, which only exists for
    users who completed the survey (has_done_survey=True) - anyone missing
    falls into an "Unspecified" bucket rather than being silently dropped,
    so each breakdown's total still reconciles with the true revenue figure.
    """
    revenue_by_user = _get_per_user_revenue(start, end)
    if not revenue_by_user:
        return {"by_location": [], "by_gender": [], "by_age": []}

    user_ids = list(revenue_by_user.keys())

    state_by_user = dict(
        User.objects.filter(id__in=user_ids).values_list("id", "state")
    )
    survey_rows = MemberSurvey.objects.filter(user_id__in=user_ids).values_list(
        "user_id", "sex", "age_bracket"
    )
    sex_by_user = {}
    age_by_user = {}
    for user_id, sex, age_bracket in survey_rows:
        sex_by_user[user_id] = sex
        age_by_user[user_id] = age_bracket

    return {
        "by_location": _totals_to_breakdown(
            _bucket_revenue(revenue_by_user, state_by_user)
        ),
        "by_gender": _totals_to_breakdown(
            _bucket_revenue(revenue_by_user, sex_by_user)
        ),
        "by_age": _totals_to_breakdown(_bucket_revenue(revenue_by_user, age_by_user)),
    }


# ── Alert and Risk drill-downs ──────────────────────────────────────────
# Shared row shape for the Pending Settlement / Reconciliation Differences /
# Duplicate Transactions tables: Transaction ID, Service, Category (service
# bucket), account_type (the transacting user's Member/Partner/BrandAd/etc
# role - what the Figma calls "Category" in these specific tables), Amount,
# Status, Date/Time, Type, plus Wallet Name/Number for the detail modal.


def _tx_category(tx, partner_linked_tx_ids):
    if tx.tx_type in SELF_SERVICE_AND_PARTNER_TX_TYPES:
        return "Partners" if tx.id in partner_linked_tx_ids else "Self Services"
    if tx.tx_type in BRAND_ADS_TX_TYPES:
        return "Brand Ads"
    if tx.tx_type in WALLET_CATEGORY_TX_TYPES:
        return "Wallet"
    return "Other"


def _build_tx_row(tx, partner_linked_tx_ids, wallet_by_user, status_override=None):
    wallet_name, wallet_number = wallet_by_user.get(tx.user_id, (None, None))
    return {
        "transaction_id": tx.tx_reference or str(tx.id),
        "user": tx.user.phone_number if tx.user_id else None,
        "service": tx.tx_type,
        "category": _tx_category(tx, partner_linked_tx_ids),
        "account_type": tx.user.active_role if tx.user_id else None,
        "amount": float(tx.amount or 0),
        "status": status_override if status_override is not None else tx.status,
        "date": tx.date.isoformat() if tx.date else None,
        "type": "Credit" if tx.tx_type in CREDIT_TX_TYPES else "Debit",
        "wallet_name": wallet_name,
        "wallet_number": wallet_number,
    }


def get_pending_settlement_list():
    """
    Flat rows for every TxModel currently PENDING - the Pending Settlement
    drill-down table. A live backlog snapshot, same framing as
    get_pending_settlement_count - not period-scoped, since a transaction
    pending since last week is still a live risk today.
    """
    tx_list = list(
        TxModel.objects.filter(status="PENDING")
        .select_related("user")
        .order_by("-date")
    )
    if not tx_list:
        return []
    partner_linked_tx_ids = _get_partner_linked_tx_ids(None, None)
    wallet_by_user = _wallet_info_by_user({tx.user_id for tx in tx_list if tx.user_id})
    return [_build_tx_row(tx, partner_linked_tx_ids, wallet_by_user) for tx in tx_list]


def get_transaction_detail_row(transaction_id):
    """
    Single Transaction Details lookup by transaction_id (tx_reference, or
    the numeric TxModel id when tx_reference is null - matches how
    transaction_id is built in _build_tx_row/get_all_transactions). Backs
    the Pending Settlement detail modal.
    """
    query = Q(tx_reference=transaction_id)
    if transaction_id.isdigit():
        query |= Q(id=int(transaction_id))
    tx = TxModel.objects.select_related("user").filter(query).first()
    if not tx:
        return None
    partner_linked_tx_ids = _get_partner_linked_tx_ids(None, None)
    wallet_by_user = _wallet_info_by_user({tx.user_id} if tx.user_id else set())
    return _build_tx_row(tx, partner_linked_tx_ids, wallet_by_user)


# Grace period after a partner-linked purchase before an unsettled payout
# counts as a Reconciliation Difference. Settlement is a slow, currently
# manual process (see PartnerPurchase.settled) - a short window like the
# duplicate-transaction heuristic would flag perfectly normal in-flight
# payouts, not real problems.
RECONCILIATION_GRACE_PERIOD_HOURS = 24


def get_reconciliation_differences_queryset(start, end):
    """
    PartnerPurchase rows where the underlying TxModel succeeded (money left
    the user's wallet) but the partner hasn't been marked settled after
    RECONCILIATION_GRACE_PERIOD_HOURS. Scoped to partner-linked bookings
    only - nothing in the schema tracks "did the provider actually receive
    it" for any other transaction type yet, so a broader reconciliation
    concept isn't buildable today without guessing.
    """
    cutoff = timezone.now() - timedelta(hours=RECONCILIATION_GRACE_PERIOD_HOURS)
    return PartnerPurchase.objects.filter(
        created_at__gte=start,
        created_at__lt=end,
        settled=False,
        tx__status="SUCCESS",
        tx__date__lt=cutoff,
    ).select_related("tx", "tx__user", "service", "service__user")


def get_reconciliation_differences_count(start, end):
    return get_reconciliation_differences_queryset(start, end).count()


def get_reconciliation_differences_list(start, end):
    """
    Flat rows for the Reconciliation Differences drill-down table - one row
    per unsettled partner-linked purchase, from the buying user's side.
    """
    purchases = [p for p in get_reconciliation_differences_queryset(start, end) if p.tx]
    if not purchases:
        return []
    partner_linked_tx_ids = {p.tx_id for p in purchases}
    wallet_by_user = _wallet_info_by_user(
        {p.tx.user_id for p in purchases if p.tx.user_id}
    )
    return [
        _build_tx_row(purchase.tx, partner_linked_tx_ids, wallet_by_user)
        for purchase in purchases
    ]


def get_reconciliation_difference_detail(transaction_id):
    """
    Two-sided Transaction Details for a Reconciliation Difference: the
    user's side (their TxModel row - the wallet debit, already succeeded)
    and the partner's side (the PartnerPurchase payout, still awaiting
    settlement confirmation).
    """
    query = Q(tx__tx_reference=transaction_id)
    if transaction_id.isdigit():
        query |= Q(tx_id=int(transaction_id))
    purchase = (
        PartnerPurchase.objects.select_related(
            "tx", "tx__user", "service", "service__user"
        )
        .filter(query)
        .first()
    )
    if not purchase or not purchase.tx:
        return None

    tx = purchase.tx
    buyer_wallet_by_user = _wallet_info_by_user({tx.user_id} if tx.user_id else set())
    buyer_wallet_name, buyer_wallet_number = buyer_wallet_by_user.get(
        tx.user_id, (None, None)
    )

    partner_user_id = purchase.service.user_id if purchase.service else None
    partner_wallet_by_user = _wallet_info_by_user(
        {partner_user_id} if partner_user_id else set()
    )
    partner_wallet_name, partner_wallet_number = partner_wallet_by_user.get(
        partner_user_id, (None, None)
    )

    return {
        "user_side": {
            "transaction_id": tx.tx_reference or str(tx.id),
            "date": tx.date.isoformat() if tx.date else None,
            "service": tx.tx_type,
            "category": "User",
            "wallet_name": buyer_wallet_name,
            "wallet_number": buyer_wallet_number,
            "amount": float(tx.amount or 0),
            "type": "Debit",
            "status": tx.status,
        },
        "partner_side": {
            "transaction_id": tx.tx_reference or str(tx.id),
            "date": purchase.created_at.isoformat() if purchase.created_at else None,
            "service": tx.tx_type,
            "category": "Partner",
            "wallet_name": partner_wallet_name,
            "wallet_number": partner_wallet_number,
            "amount": float(purchase.payout_amount or 0),
            "type": "Credit",
            "status": "SETTLED" if purchase.settled else "PENDING",
        },
    }


def get_duplicate_transactions_list(start, end):
    """
    Flat rows for the Duplicate Transactions drill-down table - one row per
    detected duplicate (the later of the pair), status overridden to
    "Duplicate" (a display-only label - not a real TxModel.status value).
    """
    pairs = get_duplicate_transaction_pairs(start, end)
    if not pairs:
        return []
    partner_linked_tx_ids = _get_partner_linked_tx_ids(start, end)
    user_ids = {tx.user_id for pair in pairs for tx in pair if tx.user_id}
    wallet_by_user = _wallet_info_by_user(user_ids)
    return [
        _build_tx_row(
            duplicate_tx,
            partner_linked_tx_ids,
            wallet_by_user,
            status_override="Duplicate",
        )
        for duplicate_tx, _original_tx in pairs
    ]


def get_duplicate_transaction_detail(transaction_id):
    """
    Two-sided Transaction Details for a specific duplicate: the flagged
    (later) transaction plus the original it duplicates, each with its
    real status. Searches a wide lookback window since pairing isn't
    period-scoped once you're looking at one specific transaction.
    """
    start = timezone.now() - timedelta(days=365)
    end = timezone.now()
    for duplicate_tx, original_tx in get_duplicate_transaction_pairs(start, end):
        if (duplicate_tx.tx_reference or str(duplicate_tx.id)) == transaction_id:
            partner_linked_tx_ids = _get_partner_linked_tx_ids(start, end)
            wallet_by_user = _wallet_info_by_user(
                {t.user_id for t in (duplicate_tx, original_tx) if t.user_id}
            )
            return {
                "duplicate": _build_tx_row(
                    duplicate_tx, partner_linked_tx_ids, wallet_by_user
                ),
                "original": _build_tx_row(
                    original_tx, partner_linked_tx_ids, wallet_by_user
                ),
            }
    return None


def get_fraud_alerts_list():
    """
    Fraud Alert drill-down - always empty. No fraud ruleset is defined
    anywhere in the codebase yet, so there's nothing real to list; returns
    an empty list rather than fabricating detections.
    """
    return []


def get_alert_and_risk_snapshot(start, end):
    """
    Alert and Risk panel counts. pending_settlement is a current backlog
    snapshot. duplicate_transactions and reconciliation_differences are
    period-scoped and trend-comparable. fraud_alerts is always 0 - no
    ruleset exists to detect anything (see get_fraud_alerts_list).
    """
    return {
        "pending_settlement": get_pending_settlement_count(),
        "duplicate_transactions": get_duplicate_transaction_count(start, end),
        "reconciliation_differences": get_reconciliation_differences_count(start, end),
        "fraud_alerts": 0,
    }
