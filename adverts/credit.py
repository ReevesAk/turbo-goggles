"""
Shared brand credit ledger. A single BrandAdCreditWallet per brand accrues
credit from any expired, unsettled campaign with unfilled slots — currently
CreateAd (paid ads) and UserGeneratedContent (paid UGC tasks) — and that
credit can be applied against the cost of creating a new item of either type.

reconcile_credit() and reserve_credit()/finalize_credit()/release_credit()
are written against a small duck-typed contract rather than a single model.
Both CreateAd and UserGeneratedContent must implement:
    - .user, .slot_cap, .slots_filled, .amount
    - .credit_settled, .ads_credit, .expiry_date
    - .campaign_name or .task_name

Adding a third billable model later means: add it to _SWEEPABLE_MODELS,
add a branch in _source_kwargs(), and add a source_<x> FK on
BrandAdCreditLedger.

Call order for charging a new item (see billing/mixins.py):
    1. reconcile_credit(user)                              — sweep expired credit
    2. credit_reserved, net_charge = reserve_credit(user, full_charge)
    3. ... perform the real, external debit for net_charge ...
    4a. on success: item = save_fn(); finalize_credit(user, item, credit_reserved)
    4b. on failure after reserve_credit but before finalize_credit:
        release_credit(user, credit_reserved)
"""

from decimal import Decimal
from typing import Tuple

from django.db.models import F
from django.utils import timezone

from .models import BrandAdCreditLedger, BrandAdCreditWallet, CreateAd
from gamification.models import UserGeneratedContent

# Every model type whose expired, unfilled-slot campaigns should be swept
# into wallet credit. Order is arbitrary — each is processed independently.
_SWEEPABLE_MODELS = (CreateAd, UserGeneratedContent)


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


def _sweep_model(model, user, wallet, now) -> bool:
    """
    Sweep one model's expired, unsettled, unfilled-slot rows into wallet
    credit. Mutates `wallet.balance` in place; the caller saves the wallet
    once after all models have been swept.

    Returns True if any row was processed (regardless of whether it carried
    positive credit), so the caller knows whether a wallet save is needed.
    """
    expired_unsettled = model.objects.select_for_update().filter(
        pk__in=_pending_queryset(model, user, now).values("pk")
    )

    swept_any = False
    for item in expired_unsettled:
        swept_any = True
        credit = item.unused_credit
        item.credit_settled = True
        item.ads_credit = credit
        item.save(update_fields=["credit_settled", "ads_credit"])

        if credit <= 0:
            continue

        wallet.balance += credit

        unused_slots = (item.slot_cap or 0) - (item.slots_filled or 0)
        BrandAdCreditLedger.objects.create(
            user=user,
            transaction_type=BrandAdCreditLedger.CREDIT,
            amount=credit,
            balance_after=wallet.balance,
            reason=(
                f"Unused slots refund: {unused_slots}/{item.slot_cap} "
                f"slots unfilled on '{_label(item)}'"
            ),
            **_source_kwargs(item),
        )

    return swept_any


def reconcile_credit(user) -> Decimal:
    """
    Called inside an atomic block at the start of ad/UGC creation views
    (and read-only cost-preview views).

    Fast path: if nothing is actually pending sweep, does a plain unlocked
    existence check and returns without taking the wallet lock or issuing
    a write. This is the path hit by nearly every call, since most requests
    aren't the one that happens to coincide with an item expiring — only
    brands with something genuinely to sweep pay for the lock + UPDATE.

    Does NOT create a wallet row on this fast path, so a read-only view
    (e.g. AdCostPreviewView) never provisions a wallet as a side effect of
    being viewed.

    The unlocked existence check can race with another concurrent sweep,
    but that's harmless: _sweep_model's actual locked queryset re-filters
    on credit_settled=False, so a row already swept by another request
    simply won't appear and swept_any stays False for it.
    """
    now = timezone.now()

    has_pending = any(
        _pending_queryset(model, user, now).exists() for model in _SWEEPABLE_MODELS
    )
    if not has_pending:
        wallet = BrandAdCreditWallet.objects.filter(user=user).first()
        return wallet.balance if wallet else Decimal("0.00")

    wallet, _ = BrandAdCreditWallet.objects.select_for_update().get_or_create(user=user)

    swept_any = False
    for model in _SWEEPABLE_MODELS:
        if _sweep_model(model, user, wallet, now):
            swept_any = True

    if swept_any:
        wallet.save(update_fields=["balance"])

    return wallet.balance


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
