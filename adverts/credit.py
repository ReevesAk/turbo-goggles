"""
Shared brand credit ledger. A single BrandAdCreditWallet per brand accrues
credit from any expired, unsettled campaign with unfilled slots — currently
CreateAd (paid ads) and UserGeneratedContent (paid UGC tasks) — and that
credit can be applied against the cost of creating a new item of either type.

reconcile_credit() and apply_credit() are written against a small duck-typed
contract rather than a single model. Both CreateAd and UserGeneratedContent
must implement:
    - .user, .slot_cap, .slots_filled, .amount
    - .credit_settled, .ads_credit, .expiry_date
    - .campaign_name or .task_name

Adding a third billable model later means: add it to _SWEEPABLE_MODELS,
add a branch in _source_kwargs(), and add a source_<x> FK on
BrandAdCreditLedger.
"""

from decimal import Decimal
from typing import Tuple

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


def _sweep_model(model, user, wallet, now) -> None:
    """
    Sweep one model's expired, unsettled, unfilled-slot rows into wallet
    credit. Mutates `wallet.balance` in place; the caller saves the wallet
    once after all models have been swept.

    Args:
        model: CreateAd or UserGeneratedContent
        user: the brand whose rows to sweep
        wallet: the brand's BrandAdCreditWallet, already select_for_update()'d
        now: timezone.now(), passed in so all models sweep against the
             same instant within one reconcile_credit() call
    """
    expired_unsettled = (
        model.objects.select_for_update()
        .filter(
            user=user,
            credit_settled=False,
            slot_cap__isnull=False,
            expiry_date__lte=now,
        )
        .exclude(slot_cap=0)
    )

    for item in expired_unsettled:
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


def reconcile_credit(user) -> Decimal:
    """
    Called inside an atomic block at the start of ad/UGC creation views.

    Sweeps every expired, unsettled campaign — both CreateAd and
    UserGeneratedContent — with unfilled slots into the brand's
    BrandAdCreditWallet, writing an immutable CREDIT ledger entry per
    source item.

    Returns the total credit now available in the wallet (balance after sweep).
    """
    now = timezone.now()

    wallet, _ = BrandAdCreditWallet.objects.select_for_update().get_or_create(user=user)

    for model in _SWEEPABLE_MODELS:
        _sweep_model(model, user, wallet, now)

    wallet.save(update_fields=["balance"])
    return wallet.balance


def apply_credit(user, new_item, charge: Decimal) -> Tuple[Decimal, Decimal]:
    """
    Deducts available wallet credit from a new ad's or UGC task's charge.

    Args:
        user: the brand
        new_item: the CreateAd or UserGeneratedContent instance just created
        charge: full amount being charged for new_item

    Returns (credit_applied, effective_charge):
      - credit_applied: how much was taken from the wallet
      - effective_charge: what the brand still needs to pay (charge - credit_applied)

    Writes a DEBIT ledger entry if any credit is consumed. Must be called
    inside an atomic block after reconcile_credit.
    """
    wallet, _ = BrandAdCreditWallet.objects.select_for_update().get_or_create(user=user)

    credit_applied = min(wallet.balance, charge)
    effective_charge = charge - credit_applied

    if credit_applied > 0:
        wallet.balance -= credit_applied
        wallet.save(update_fields=["balance"])

        BrandAdCreditLedger.objects.create(
            user=user,
            transaction_type=BrandAdCreditLedger.DEBIT,
            amount=credit_applied,
            balance_after=wallet.balance,
            reason=f"Credit applied to new item '{_label(new_item)}'",
            **_source_kwargs(new_item),
        )

    return credit_applied, effective_charge
