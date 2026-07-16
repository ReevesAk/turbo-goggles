import logging
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from rest_framework import status
from rest_framework.response import Response
from adverts.credit import (
    reconcile_credit,
    reserve_credit,
    finalize_credit,
    release_credit,
)
from banking.models import WalletModel, TxModel
from accounts.models import UserNotification
from banking.controllers import Wallet
from roles.models import ActivityModel
from security import encrypt

logger = logging.getLogger(__name__)


def _round_money(amount: Decimal) -> Decimal:
    """
    Round to 2 decimal places (kobo) using standard half-up rounding.
    """
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class _ChargeCopy:
    __slots__ = (
        "tx_type",
        "tx_description",
        "notification_title",
        "notification_phrase",
        "activity_description",
    )

    def __init__(
        self,
        tx_type,
        tx_description,
        notification_title,
        notification_phrase,
        activity_description,
    ):
        self.tx_type = tx_type
        self.tx_description = tx_description
        self.notification_title = notification_title
        self.notification_phrase = notification_phrase
        self.activity_description = activity_description


class BrandChargeMixin:
    """
    Wallet/card charging shared by brand-facing money flows (ad promotion,
    UGC task funding, and anything else that debits a BrandAd wallet or
    card).

    Ordering is deliberate and load-bearing:
      1. reconcile_credit()     —   sweep expired credit (cheap no-op if nothing pending)
      2. reserve_credit()       —   lock + deduct BEFORE any external call, closes the
                                    read/compute/debit race
      3. live balance check
      4. write PENDING TxModel  —   BEFORE the external debit, so a crash after a
                                    successful debit leaves a retry-detectable record
      5. Wallet.Debit()         —   the real, irreversible external call
      6. save_fn() + notifications, inside one atomic block
      7. success > finalize_credit(), TxModel > SUCCESS

    failure after step 5 compensates Wallet.Credit refund + release_credit(),
    logs FAILED status to the TxModel. If the refund itself fails,
    this logs CRITICAL for manual reconciliation as that failure mode can't be fully automated away.
    """

    def charge_and_create(
        self,
        *,
        user,
        payment_option,
        amount,
        tx_reference,
        tx_type,
        tx_description,
        notification_title,
        notification_phrase,
        activity_description,
        debit_reason,
        save_fn,
    ):
        full_charge = _round_money(Decimal(str(amount)))
        copy = _ChargeCopy(
            tx_type,
            tx_description,
            notification_title,
            notification_phrase,
            activity_description,
        )

        if payment_option == "WALLET":
            return self._charge_wallet(
                user, full_charge, tx_reference, copy, debit_reason, save_fn
            )
        if payment_option == "CARD":
            return self._charge_card(user, full_charge, tx_reference, copy, save_fn)

        return None, self._fail("Invalid payment option")

    # =================
    # WALLET
    # =================

    def _charge_wallet(
        self, user, full_charge, tx_reference, copy, debit_reason, save_fn
    ):
        with transaction.atomic():
            reconcile_credit(user)

        # Reserve credit BEFORE computing net_charge or touching Wallet.Debit.
        # net_charge is now derived from a locked, already-decremented balance.
        with transaction.atomic():
            credit_reserved, net_charge = reserve_credit(user, full_charge)
            net_charge = _round_money(net_charge)

        account = WalletModel.objects.get(user=user)
        if self._live_balance(account) < net_charge:
            release_credit(user, credit_reserved)
            return None, self._fail("Insufficient balance.")

        # Idempotency marker BEFORE the irreversible external call. If the
        # process dies after Wallet.Debit succeeds, a retry with the same
        # tx_reference finds this row instead of re-running the whole flow.
        tx = TxModel.objects.create(
            user=user,
            tx_reference=tx_reference,
            tx_type=copy.tx_type,
            amount=float(net_charge),
            description=copy.tx_description,
            status="PENDING",
        )

        if net_charge > 0:
            try:
                debit_response = Wallet.Debit(
                    debitAccount=account.account_number,
                    amount=float(net_charge),
                    reason=debit_reason,
                    merchantFeeAmount="0.00",
                )
            except Exception:
                logger.exception(
                    "Wallet.Debit raised unexpectedly for tx_reference=%s", tx_reference
                )
                debit_response = None

            if debit_response is None or debit_response.status_code != 200:
                release_credit(user, credit_reserved)
                tx.status = "FAILED"
                tx.save(update_fields=["status"])
                return None, self._fail("Debit failed. Please try again.")

        # Debit is now real and irreversible. Anything past this point that
        # fails must be compensated, not just logged and swallowed.
        try:
            with transaction.atomic():
                obj = save_fn()
                finalize_credit(user, obj, credit_reserved)
                self._log_notification_and_activity(
                    user, copy, int(net_charge), credit_reserved
                )

            tx.status = "SUCCESS"
            tx.save(update_fields=["status"])

            logger.info(
                "%s payment successful for user %s (charged: %s, credit applied: %s)",
                copy.tx_type,
                user.email,
                net_charge,
                credit_reserved,
            )

            # Best-effort refresh. A stale cached balance isn't worth
            # failing an already-successful debit over.
            self._resync_balance(account)

            return obj, None

        except Exception:
            logger.exception(
                "%s: debit succeeded but item creation failed — issuing compensating "
                "refund for tx_reference=%s",
                copy.tx_type,
                tx_reference,
            )
            refund_response = None
            if net_charge > 0:
                try:
                    refund_response = Wallet.Credit(
                        acct_no=account.account_number,
                        amount=float(net_charge),
                        reason=f"Refund: {debit_reason} (creation failed)",
                    )
                except Exception:
                    logger.exception(
                        "Wallet.Credit refund raised unexpectedly for tx_reference=%s",
                        tx_reference,
                    )

            release_credit(user, credit_reserved)
            tx.status = "FAILED"
            tx.save(update_fields=["status"])

            if net_charge > 0 and (
                refund_response is None or refund_response.status_code != 200
            ):
                logger.critical(
                    "REFUND FAILED after debit succeeded — manual reconciliation required. "
                    "user=%s tx_reference=%s amount=%s",
                    user.email,
                    tx_reference,
                    net_charge,
                )

            return None, self._fail(
                "Task creation failed. Your payment has been reversed — please try again.",
                code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # ==========
    # CARD
    # ==========

    def _charge_card(self, user, full_charge, tx_reference, copy, save_fn):
        with transaction.atomic():
            reconcile_credit(user)

        with transaction.atomic():
            credit_reserved, effective_charge = reserve_credit(user, full_charge)
            effective_charge = _round_money(effective_charge)

        try:
            with transaction.atomic():
                obj = save_fn()
                finalize_credit(user, obj, credit_reserved)
                self._log_notification_and_activity(
                    user, copy, int(effective_charge), credit_reserved
                )

            TxModel.objects.create(
                user=user,
                tx_reference=tx_reference,
                tx_type=copy.tx_type,
                amount=float(effective_charge),
                description=copy.tx_description,
                status="SUCCESS",
            )

            logger.info(
                "%s payment successful for user %s (charged: %s, credit applied: %s)",
                copy.tx_type,
                user.email,
                effective_charge,
                credit_reserved,
            )
            return obj, None

        except Exception:
            # Card charge itself is assumed to happen via the card processor
            # at serializer/save_fn time in this branch's current design;
            # if item creation fails here, no card debit has actually
            # settled yet, so only the reserved credit needs releasing.
            logger.exception(
                "%s: item creation failed on CARD path for tx_reference=%s",
                copy.tx_type,
                tx_reference,
            )
            release_credit(user, credit_reserved)
            return None, self._fail(
                "Task creation failed. Please try again.",
                code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # ==============
    # Shared helpers
    # ==============

    @staticmethod
    def _live_balance(account):
        enquiry = Wallet.getWalletDetails(account.account_number)
        if enquiry and hasattr(enquiry, "json"):
            data = enquiry.json()
            return Decimal(str(data.get("data", {}).get("availableBalance", 0)))
        return Decimal(str(account.balance))

    @staticmethod
    def _resync_balance(account):
        post_debit = Wallet.getWalletDetails(account.account_number)
        if post_debit and hasattr(post_debit, "json"):
            data = post_debit.json()
            if data.get("status") == "SUCCESS":
                account.balance = data["data"]["availableBalance"]
                account.save(update_fields=["balance"])

    @staticmethod
    def _log_notification_and_activity(user, copy, amount, credit_applied):
        credit_msg = (
            f" (₦{credit_applied} credit applied)" if credit_applied > 0 else ""
        )
        UserNotification.objects.create(
            user=user,
            title=copy.notification_title,
            message=f"Your payment of ₦{amount} for {copy.notification_phrase} was successful.{credit_msg}",
        )
        ActivityModel.objects.create(
            user=user,
            title=copy.notification_title,
            description=f"{user} {copy.activity_description}.{credit_msg}",
        )

    @staticmethod
    def _fail(message, code=status.HTTP_400_BAD_REQUEST):
        return Response(
            data=encrypt({"status": "fail", "message": message}), status=code
        )
