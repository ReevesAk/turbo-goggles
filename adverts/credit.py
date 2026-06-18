from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .models import BrandAdCreditLedger, BrandAdCreditWallet, CreateAd


def reconcile_credit(user) -> Decimal:
    """
    Called inside an atomic block at the start of CreateAdAndOnboardBrandView.

    Scans all of this brand's expired ads that still have unfilled slots and
    haven't been credited yet. For each, computes:

        unused_credit = (slot_cap - slots_filled) × (amount / slot_cap)

    Credits the amount to the brand's BrandAdCreditWallet and writes an
    immutable CREDIT ledger entry per source ad.

    Returns the total credit now available in the wallet (balance after sweep).
    """
    now = timezone.now()

    expired_unsettled = CreateAd.objects.select_for_update().filter(
        user=user,
        credit_settled=False,
        slot_cap__isnull=False,
        expiry_date__lte=now,
    ).exclude(slot_cap=0)

    if not expired_unsettled.exists():
        wallet, _ = BrandAdCreditWallet.objects.get_or_create(user=user)
        return wallet.balance

    wallet, _ = BrandAdCreditWallet.objects.select_for_update().get_or_create(user=user)

    for ad in expired_unsettled:
        credit = ad.unused_credit
        ad.credit_settled = True
        ad.ads_credit = credit
        ad.save(update_fields=["credit_settled", "ads_credit"])

        if credit <= 0:
            continue

        wallet.balance += credit

        unused_slots = (ad.slot_cap or 0) - (ad.slots_filled or 0)
        BrandAdCreditLedger.objects.create(
            user=user,
            transaction_type=BrandAdCreditLedger.CREDIT,
            amount=credit,
            balance_after=wallet.balance,
            source_ad=ad,
            reason=f"Unused slots refund: {unused_slots}/{ad.slot_cap} slots unfilled on '{ad.campaign_name}'",
        )

    wallet.save(update_fields=["balance"])
    return wallet.balance


def apply_credit(user, new_ad, charge: Decimal) -> tuple[Decimal, Decimal]:
    """
    Deducts available wallet credit from the new ad's charge.

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
            source_ad=new_ad,
            reason=f"Credit applied to new ad '{new_ad.campaign_name}'",
        )

    return credit_applied, effective_charge
