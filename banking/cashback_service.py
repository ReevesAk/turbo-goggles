from decimal import Decimal
from datetime import timedelta

from django.utils import timezone
from django.db import transaction


from .models import WalletModel, CashbackRule, Cashback


class CashbackService:

    CASHBACK_PERCENT = Decimal("0.01")  # 1%

    @classmethod
    @transaction.atomic
    def reward_cashback(user, amount, service, tx_ref):

        try:
            rule = CashbackRule.objects.get(service_type=service, is_active=True)
        except CashbackRule.DoesNotExist:
            return

        cashback = Decimal(amount) * (rule.percentage / 100)

        wallet = WalletModel.objects.get(user=user)
        wallet.cashback_balance += cashback
        wallet.save(update_fields=["cashback_balance"])

        Cashback.objects.create(
            user=user,
            amount=cashback,
            service_type=service,
            transaction_reference=tx_ref,
            expires_at=timezone.now() + timedelta(days=30),
        )

    @classmethod
    @transaction.atomic
    def apply_cashback_payment(cls, user, amount):

        wallet = WalletModel.objects.select_for_update().get(user=user)

        cashback_balance = wallet.cashback_balance
        amount = Decimal(amount)

        if cashback_balance >= amount:
            cashback_used = amount
            wallet.cashback_balance -= amount
            wallet.save(update_fields=["cashback_balance"])

            return {"wallet_amount": Decimal("0"), "cashback_used": cashback_used}

        cashback_used = cashback_balance
        wallet.cashback_balance = Decimal("0")

        remaining_amount = amount - cashback_used

        wallet.save(update_fields=["cashback_balance"])

        return {"wallet_amount": remaining_amount, "cashback_used": cashback_used}

    @classmethod
    def add_cashback_to_bundles(self, data):

        for category, bundles in data.items():

            if isinstance(bundles, list):

                for bundle in bundles:

                    amount = Decimal(str(bundle.get("amount", "0")))

                    cashback = amount * Decimal("0.01")

                    bundle["cashback"] = str(round(cashback, 2))

        return data
