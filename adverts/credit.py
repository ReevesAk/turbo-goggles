"""
Handles what happens when a billable campaign (CreateAd paid ads, or
UserGeneratedContent paid UGC tasks) expires without having reached its
slot_cap completion target (see commons.is_slot_target_reached):
  - target reached  -> settle normally, marked credit_settled, no credit.
  - target not reached -> not closed out; expiry_date is pushed forward by
    a month instead, giving it another window to reach the target. This
    repeats indefinitely until the target is reached.

There is no more wallet-credit generation from unfilled slots — brands are
no longer refunded for expired campaigns, they're given more time instead.

reserve_credit()/finalize_credit()/release_credit() remain as the generic
"apply a brand's existing BrandAdCreditWallet balance toward a new charge"
mechanism (used by billing_mixings.py for every wallet/card charge), for
any wallet balance already on the books — but expiry no longer feeds it.

Both CreateAd and UserGeneratedContent must implement:
    - .user, .slot_cap, .slots_filled, .amount
    - .credit_settled, .expiry_date
    - .campaign_name or .task_name

Adding a third billable model later means: add it to _SWEEPABLE_MODELS,
add a branch in _source_kwargs(), and add a source_<x> FK on
BrandAdCreditLedger.

Call order for charging a new item (see billing/mixins.py):
    1. reconcile_credit(user)                              — sweep expired items
    2. credit_reserved, net_charge = reserve_credit(user, full_charge)
    3. ... perform the real, external debit for net_charge ...
    4a. on success: item = save_fn(); finalize_credit(user, item, credit_reserved)
    4b. on failure after reserve_credit but before finalize_credit:
        release_credit(user, credit_reserved)
"""

from datetime import timedelta
from decimal import Decimal
from typing import Tuple

from django.db.models import F
from django.utils import timezone

from commons import is_slot_target_reached
from .models import BrandAdCreditLedger, BrandAdCreditWallet, CreateAd
from gamification.models import UserGeneratedContent

# Every model type whose expired campaigns should be swept (settled or
# auto-extended). Order is arbitrary — each is processed independently.
_SWEEPABLE_MODELS = (CreateAd, UserGeneratedContent)

_AUTO_EXTEND = timedelta(days=30)


def _label(item) -> str:
    """Human-readable name for ledger 'reason' text, works across billable models."""
    return (
        getattr(item, "campaign_name", None)
        or getattr(item, "task_name", None)
        or "item"
    )


def _source_kwargs(item) -> dict:
    """Return the correct BrandAdCreditLedger FK kwarg for this item's type."""
    if isinstance(item, CreateAd):
        return {"source_ad": item}
    if isinstance(item, UserGeneratedContent):
        return {"source_ugc_task": item}
    raise TypeError(f"Unsupported credit source type: {type(item)!r}")


def _pending_queryset(model, user, now):
    """Unlocked queryset used only for the cheap existence check in reconcile_credit()."""
    return model.objects.filter(
        user=user,
        credit_settled=False,
        slot_cap__isnull=False,
        expiry_date__lte=now,
    ).exclude(slot_cap=0)


def _sweep_model(model, user, now) -> None:
    """
    Settle or auto-extend one model's expired, unsettled rows for this user.

    A row that already reached its slot_cap completion target is closed out
    (credit_settled=True, no credit generated). A row that hasn't gets
    another window: expiry_date moves forward by _AUTO_EXTEND, and it stays
    unsettled so it's picked up again next time it expires.
    """
    expired_unsettled = model.objects.select_for_update().filter(
        pk__in=_pending_queryset(model, user, now).values("pk")
    )

    for item in expired_unsettled:
        if is_slot_target_reached(item.slot_cap, item.slots_filled):
            item.credit_settled = True
            item.save(update_fields=["credit_settled"])
        else:
            item.expiry_date = item.expiry_date + _AUTO_EXTEND
            item.save(update_fields=["expiry_date"])


def reconcile_credit(user) -> None:
    """
    Called inside an atomic block at the start of ad/UGC creation views.

    Fast path: if nothing is actually pending sweep, does a plain unlocked
    existence check and returns without taking any row locks or issuing a
    write. This is the path hit by nearly every call, since most requests
    aren't the one that happens to coincide with an item expiring — only
    brands with something genuinely expired pay for the lock + UPDATE.

    The unlocked existence check can race with another concurrent sweep,
    but that's harmless: _sweep_model's actual locked queryset re-filters
    on credit_settled=False, so a row already swept by another request
    simply won't appear.
    """
    now = timezone.now()

    has_pending = any(
        _pending_queryset(model, user, now).exists() for model in _SWEEPABLE_MODELS
    )
    if not has_pending:
        return

    for model in _SWEEPABLE_MODELS:
        _sweep_model(model, user, now)


def reserve_credit(user, charge: Decimal) -> Tuple[Decimal, Decimal]:
    """
    Locks the wallet and immediately deducts credit against `charge`,
    returning (credit_reserved, net_charge).

    Must be called AFTER reconcile_credit and BEFORE any external debit
    call. `net_charge` is what should actually be charged externally.
    Deducting here, under lock, before the external call closes the race
    where two concurrent requests could both compute net_charge from the
    same unconsumed balance.

    No ledger entry is written yet, since the item being charged for may
    not exist as a row until save_fn() runs. Caller must follow up with
    exactly one of:
      - finalize_credit(user, new_item, credit_reserved) on success
      - release_credit(user, credit_reserved) on failure
    """
    wallet, _ = BrandAdCreditWallet.objects.select_for_update().get_or_create(user=user)
    credit_reserved = min(wallet.balance, charge)
    net_charge = charge - credit_reserved
    if credit_reserved > 0:
        wallet.balance -= credit_reserved
        wallet.save(update_fields=["balance"])
    return credit_reserved, net_charge


def finalize_credit(user, new_item, credit_reserved: Decimal) -> None:
    """
    Writes the immutable DEBIT ledger entry for credit already deducted by
    reserve_credit(). Call once new_item has been successfully persisted.
    """
    if credit_reserved <= 0:
        return

    wallet, _ = BrandAdCreditWallet.objects.select_for_update().get_or_create(user=user)
    BrandAdCreditLedger.objects.create(
        user=user,
        transaction_type=BrandAdCreditLedger.DEBIT,
        amount=credit_reserved,
        balance_after=wallet.balance,
        reason=f"Credit applied to new item '{_label(new_item)}'",
        **_source_kwargs(new_item),
    )


def release_credit(user, amount: Decimal) -> None:
    """
    Compensating restore of credit reserved by reserve_credit() that was
    never consumed — e.g. the external debit failed, or the item failed
    to persist afterward. Uses F() to avoid re-reading a stale in-memory
    balance from the caller's earlier, now-released, wallet lock.
    """
    if amount <= 0:
        return
    BrandAdCreditWallet.objects.filter(user=user).update(balance=F("balance") + amount)
