import logging
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction, IntegrityError
from rest_framework import status
from rest_framework.response import Response
from banking.models import WalletModel, TxModel
from accounts.models import UserNotification
from banking.controllers import Wallet
from banking.helpers import verify_card_payment
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

    Idempotency is owned here, not by individual views, so both callers get
    identical behavior:
      - existing TxModel row with status SUCCESS -> short-circuit success
      - existing row with status PENDING         -> reject, still processing
      - existing row with status FAILED          -> reuse that row, retry
      - no existing row                          -> proceed normally

    Ordering for a fresh WALLET charge is deliberate and load-bearing:
      1. live balance check
      2. write/reuse PENDING TxModel  -     BEFORE the external debit, so a crash after a
                                            successful debit leaves a retry-detectable record.
                                            Wrapped against IntegrityError in case a concurrent
                                            request won the same tx_reference between our
                                            idempotency check and this write.
      3. Wallet.Debit()         -   the real, irreversible external call
      4. save_fn(), inside an atomic block. Only THIS step (and its
                                    immediate contents) is wrapped in the
                                    compensating try/except — once it
                                    commits, the charge is real and nothing
                                    after it should trigger a refund.
      5. success -> TxModel -> SUCCESS (best-effort, not compensated)

    failure inside step 4 compensates with a Wallet.Credit refund and marks the
    TxModel FAILED. If the refund itself fails, this logs CRITICAL for manual
    reconciliation, since that failure mode can't be fully automated away.

    CARD charges skip straight to verify_card_payment() against a confirmed,
    unspent, user-owned FundWithCard reference — there's no wallet balance or
    debit call involved.
    """

    def charge_and_create(
        self,
        *,
        user,
        payment_option,
        card_reference,
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
        copy = _ChargeCopy(
            tx_type,
            tx_description,
            notification_title,
            notification_phrase,
            activity_description,
        )

        existing_tx, guard_response = self._check_idempotency(tx_reference, tx_type)
        if guard_response is not None:
            return None, guard_response

        full_charge = _round_money(Decimal(str(amount)))

        if payment_option == "WALLET":
            return self._charge_wallet(
                user,
                full_charge,
                tx_reference,
                copy,
                debit_reason,
                save_fn,
                existing_tx,
            )
        if payment_option == "CARD":
            return self._charge_card(
                user,
                full_charge,
                card_reference,
                tx_reference,
                copy,
                save_fn,
                existing_tx,
            )

        return None, self._fail("Invalid payment option")

    # ====================
    # Idempotency
    # ====================

    @staticmethod
    def _check_idempotency(tx_reference, tx_type):
        """
        Returns (existing_tx_or_None, short_circuit_response_or_None).

        A short_circuit_response means the caller should return immediately
        without charging anything. existing_tx being non-None with no
        short_circuit_response means "reuse this FAILED row, don't insert
        a new one" — handled by the WALLET/CARD paths.
        """
        if not tx_reference:
            return None, None

        existing_tx = TxModel.objects.filter(
            tx_reference=tx_reference, tx_type=tx_type
        ).first()
        if existing_tx is None:
            return None, None

        if existing_tx.status == "SUCCESS":
            return existing_tx, Response(
                data=encrypt(
                    {"status": "success", "message": "This request was already processed."}
                ),
                status=status.HTTP_200_OK,
            )

        if existing_tx.status == "PENDING":
            # Returns a response asking the client wait for some time
            # till the transaction status leaves pending state, in order to avoid double charges.
            return existing_tx, Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "A previous request for this payment is still processing. Please try again shortly.",
                    }
                ),
                status=status.HTTP_409_CONFLICT,
            )

        # FAILED: safe to retry. Caller reuses this row instead of
        # inserting a new one, since tx_reference is unique.
        return existing_tx, None

    # ====================
    # WALLET
    # ====================

    def _charge_wallet(
        self, user, full_charge, tx_reference, copy, debit_reason, save_fn, existing_tx
    ):
        net_charge = full_charge

        try:
            account = WalletModel.objects.get(user=user, walletType="INDIVIDUAL")
        except WalletModel.DoesNotExist:
            return None, self._fail("Wallet not found.", code=status.HTTP_404_NOT_FOUND)

        if self._live_balance(account) < net_charge:
            return None, self._fail("Insufficient balance.")

        tx, guard_response = self._get_or_init_pending_tx(
            user, tx_reference, copy, net_charge, existing_tx
        )
        if guard_response is not None:
            return None, guard_response

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
                tx.status = "FAILED"
                tx.save(update_fields=["status"])
                return None, self._fail("Debit failed. Please try again.")

        # Debit is now real and irreversible. ONLY this block — persisting
        # the item — is compensated on failure. Anything after it
        # succeeding is best-effort bookkeeping and must never trigger a
        # refund of an already-successful charge.
        try:
            with transaction.atomic():
                obj = save_fn()
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

        # Past this point the task genuinely exists. Nothing below should
        # ever trigger a refund — these are best-effort steps on an
        # already-successful charge.
        try:
            self._log_notification_and_activity(user, copy, net_charge)
        except Exception:
            logger.exception(
                "%s: item created successfully but notification/activity logging "
                "failed for tx_reference=%s — non-critical, not compensated.",
                copy.tx_type,
                tx_reference,
            )

        try:
            tx.status = "SUCCESS"
            tx.save(update_fields=["status"])
        except Exception:
            logger.exception(
                "%s: item created successfully but TxModel status update to SUCCESS "
                "failed for tx_reference=%s — needs manual correction, not a refund.",
                copy.tx_type,
                tx_reference,
            )

        logger.info(
            "%s payment successful for user %s (charged: %s)",
            copy.tx_type,
            user.email,
            net_charge,
        )

        self._resync_balance(account)

        return obj, None

    def _get_or_init_pending_tx(
        self, user, tx_reference, copy, net_charge, existing_tx
    ):
        """
        Writes the PENDING marker before the external debit call. Reuses a
        FAILED row from a prior attempt rather than inserting a duplicate
        (tx_reference is unique). Guards against a concurrent request
        winning the same tx_reference between our idempotency pre-check
        and this write.

        Returns (tx, None) on success, or (None, response) if this attempt
        should not proceed.
        """
        try:
            if existing_tx is not None:
                existing_tx.amount = float(net_charge)
                existing_tx.status = "PENDING"
                existing_tx.save(update_fields=["amount", "status"])
                return existing_tx, None

            tx = TxModel.objects.create(
                user=user,
                tx_reference=tx_reference,
                tx_type=copy.tx_type,
                amount=float(net_charge),
                description=copy.tx_description,
                status="PENDING",
            )
            return tx, None

        except IntegrityError:
            # A concurrent request created this row between our idempotency
            # pre-check and this write.
            winner = TxModel.objects.filter(
                tx_reference=tx_reference, tx_type=copy.tx_type
            ).first()
            if winner is not None and winner.status == "SUCCESS":
                return None, Response(
                    data=encrypt(
                        {"status": "success", "message": "This request was already processed."}
                    ),
                    status=status.HTTP_200_OK,
                )
            return None, self._fail(
                "A payment for this request is already being processed. Please try again shortly.",
                code=status.HTTP_409_CONFLICT,
            )

    # ====================
    # CARD
    # ====================

    def _charge_card(
        self,
        user,
        full_charge,
        card_reference,
        tx_reference,
        copy,
        save_fn,
        existing_tx,
    ):
        # First, verify the card payment actually happened, and that it
        # belongs to this user.
        _funding, card_error_response = verify_card_payment(
            card_reference, full_charge, user
        )
        if card_error_response is not None:
            return None, card_error_response

        # ONLY this block — persisting the item — is compensated on
        # failure. Bookkeeping after it succeeds (TxModel write,
        # notifications, logging) must never trigger anything for an
        # already-successful charge.
        try:
            with transaction.atomic():
                obj = save_fn()
        except Exception:
            logger.exception(
                "%s: item creation failed on CARD path for tx_reference=%s",
                copy.tx_type,
                tx_reference,
            )
            return None, self._fail(
                "Task creation failed. Please try again.",
                code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        try:
            self._log_notification_and_activity(user, copy, full_charge)
        except Exception:
            logger.exception(
                "%s: item created successfully but notification/activity logging "
                "failed for tx_reference=%s — non-critical, not compensated.",
                copy.tx_type,
                tx_reference,
            )

        try:
            if existing_tx is not None:
                existing_tx.amount = float(full_charge)
                existing_tx.status = "SUCCESS"
                existing_tx.save(update_fields=["amount", "status"])
            else:
                TxModel.objects.create(
                    user=user,
                    tx_reference=tx_reference,
                    tx_type=copy.tx_type,
                    amount=float(full_charge),
                    description=copy.tx_description,
                    status="SUCCESS",
                )
        except IntegrityError:
            # The item and card charge already succeeded by this point.
            # A colliding tx_reference here means the bookkeeping row
            # lost a race, not that this request's charge should fail —
            # log it for investigation but still return success.
            logger.warning(
                "TxModel IntegrityError after successful CARD charge for "
                "tx_reference=%s — item was created, bookkeeping row skipped.",
                tx_reference,
            )
        except Exception:
            logger.exception(
                "%s: item created successfully but TxModel write failed for "
                "tx_reference=%s — needs manual correction, not a refund.",
                copy.tx_type,
                tx_reference,
            )

        logger.info(
            "%s payment successful for user %s (charged: %s)",
            copy.tx_type,
            user.email,
            full_charge,
        )
        return obj, None

    # ====================
    # Shared helpers
    # ====================

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
    def _log_notification_and_activity(user, copy, amount):
        UserNotification.objects.create(
            user=user,
            title=copy.notification_title,
            message=f"Your payment of ₦{amount} for {copy.notification_phrase} was successful.",
        )
        ActivityModel.objects.create(
            user=user,
            title=copy.notification_title,
            description=f"{user} {copy.activity_description}.",
        )

    @staticmethod
    def _fail(message, code=status.HTTP_400_BAD_REQUEST):
        return Response(
            data=encrypt({"status": "fail", "message": message}), status=code
        )
