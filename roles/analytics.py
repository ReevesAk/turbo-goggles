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

from django.db.models import Avg, Q, Sum, F, FloatField, Window
from django.db.models.functions import Cast, TruncDate, Lag
from django.utils import timezone

from accounts.models import TxModel, User
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

VAS_SUCCESS_STATUSES = ["successful", "paid", "success", "pending"]


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
    bills = ValueAddedServices.objects.filter(
        created_at__gte=start,
        created_at__lt=end,
        status__in=["successful", "paid", "success", "pending"],
    )
    return float(
        bills.annotate(amount_float=Cast("amount", FloatField()))
        .aggregate(total=Sum("amount_float"))
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
    rows = (
        ValueAddedServices.objects.filter(
            created_at__gte=start,
            created_at__lt=end,
            status__in=["successful", "paid", "success", "pending"],
        )
        .annotate(
            day=TruncDate("created_at"), amount_float=Cast("amount", FloatField())
        )
        .values("day")
        .annotate(total=Sum("amount_float"))
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


def get_vas_snapshot(start, end):
    """VAS (airtime/data/electricity/cable) revenue + the cashback paid out on it."""
    revenue = float(
        ValueAddedServices.objects.filter(
            created_at__gte=start,
            created_at__lt=end,
            status__in=VAS_SUCCESS_STATUSES,
        )
        .annotate(amount_float=Cast("amount", FloatField()))
        .aggregate(total=Sum("amount_float"))
        .get("total")
        or 0
    )
    cashback = float(
        Cashback.objects.filter(
            service_type__in=VAS_CASHBACK_SERVICE_TYPES,
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


def get_duplicate_transaction_pairs(start, end):
    """
    Returns (duplicate_tx, original_tx) TxModel object pairs for
    [start, end) - same heuristic as before (same user + tx_type + amount
    within DUPLICATE_TRANSACTION_WINDOW_MINUTES of each other), but
    materializes the actual rows instead of just counting, so the
    Duplicate Transactions drill-down (list + two-sided detail) can be
    built from it. Uses a window function (partition by user/tx_type/
    amount, ordered by date) to find each row's previous same-group
    timestamp and id in one query, then bulk-fetches the objects.
    """
    window = timedelta(minutes=DUPLICATE_TRANSACTION_WINDOW_MINUTES)
    rows = (
        TxModel.objects.filter(date__gte=start, date__lt=end)
        .annotate(
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
        )
        .values("id", "date", "prev_date", "prev_id")
    )

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


def get_duplicate_transaction_count(start, end):
    """
    Counts transactions in [start, end) that look like an accidental repeat
    of an immediately preceding one from the same user. See
    get_duplicate_transaction_pairs for the actual heuristic.
    """
    return len(get_duplicate_transaction_pairs(start, end))


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
    ServicesBreakdownView: vas + self_services + brand_ads + partners.
    Merged in Python across ValueAddedServices and TxModel since they don't
    share a schema. Returns {user_id: total_revenue}.
    """
    revenue_by_user = {}

    vas_rows = (
        ValueAddedServices.objects.filter(
            created_at__gte=start,
            created_at__lt=end,
            status__in=VAS_SUCCESS_STATUSES,
        )
        .annotate(amount_float=Cast("amount", FloatField()))
        .values("user_id")
        .annotate(total=Sum("amount_float"))
    )
    for row in vas_rows:
        if row["user_id"]:
            revenue_by_user[row["user_id"]] = revenue_by_user.get(
                row["user_id"], 0
            ) + float(row["total"] or 0)

    tx_rows = (
        TxModel.objects.filter(
            date__gte=start,
            date__lt=end,
            status="SUCCESS",
            tx_type__in=SELF_SERVICE_AND_PARTNER_TX_TYPES + BRAND_ADS_TX_TYPES,
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
