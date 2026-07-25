from decimal import Decimal

from django.db import transaction

from .models import PartnerPurchase


class PartnerCommissionService:

    @classmethod
    @transaction.atomic
    def record_purchase(cls, user, partner_service, tx, amount):
        """Snapshot a commission/payout split for a partner-service purchase.

        Reads the negotiated commission_rate directly off partner_service -
        set manually by a PartnersAdmin for now. PartnerCommissionRule (a
        per-category default) is reserved for a future formula and isn't
        consulted here.

        No-op when there's no partner_service (booking wasn't tied to a
        partner listing) - kept permissive since the FK is nullable during
        rollout.
        """
        if not partner_service:
            return None

        commission_rate = partner_service.commission_rate or Decimal("0")

        amount = Decimal(str(amount or 0))
        commission_amount = amount * (commission_rate / Decimal("100"))
        payout_amount = amount - commission_amount

        return PartnerPurchase.objects.create(
            user=user,
            service=partner_service,
            tx=tx,
            commission_amount=commission_amount,
            payout_amount=payout_amount,
        )
