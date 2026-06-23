import hmac
import hashlib
import logging
from decimal import Decimal

from decouple import config

from django.db import transaction
from django.template.loader import render_to_string

from rest_framework import generics, status
from rest_framework.response import Response

import rest_framework.serializers as s
from drf_spectacular.utils import extend_schema, inline_serializer

from .models import TreasuryAccount, TreasuryNotification, TreasuryCardFunding
from .controllers import Anchor
from .serializers import CardFundingSerializer
from accounts.models import UserNotification, TxModel
from roles.models import ActivityModel
from commons import Messaging
from security import encrypt

logger = logging.getLogger(__name__)

anchor_api_key = config("ANCHOR_API_KEY", default="")
paystack_secret_key = config("PAYSTACK_SECRET_KEY", default="")


@extend_schema(
    summary="Anchor webhook receiver (credit/debit/KYC events)",
    tags=["Treasury"],
    description="Receives and processes Anchor webhook events including account credits, debits, and KYC approval/rejection. Validates the HMAC-SHA512 signature before processing.",
    request=inline_serializer(name="AnchorWebhookRequest", fields={
        "type": s.CharField(),
        "data": s.DictField(),
    }),
    responses={
        200: inline_serializer(name="AnchorWebhookResponse", fields={"status": s.CharField()}),
        400: inline_serializer(name="AnchorWebhookError", fields={"status": s.CharField()}),
    },
)
class AnchorWebhookView(generics.GenericAPIView):
    """
    Handles Anchor webhook events for credit/debit on user sub-accounts.
    Equivalent to InflowsWebhookNotificationView in banking.

    Anchor sends an HMAC-SHA512 signature in X-Anchor-Hmac-Sha512.
    """

    def _verify_signature(self, request):
        signature = request.headers.get("X-Anchor-Hmac-Sha512") or request.headers.get("X-Anchor-Signature")
        if not signature or not anchor_api_key:
            return True  # Skip verification if key not yet configured

        expected = hmac.new(
            anchor_api_key.encode(),
            request.body,
            hashlib.sha512,
        ).hexdigest()

        return hmac.compare_digest(expected, signature)

    def post(self, request, *args, **kwargs):
        if not self._verify_signature(request):
            logger.warning("Invalid Anchor webhook signature")
            return Response(status=status.HTTP_400_BAD_REQUEST)

        payload = request.data
        event_type = payload.get("type") or payload.get("event")
        data = payload.get("data", {})
        attributes = data.get("attributes", {})

        logger.info("Anchor webhook received: event=%s", event_type)

        if event_type in ("deposit_account.credit", "transaction.credit"):
            return self._handle_credit(data, attributes)
        elif event_type in ("deposit_account.debit", "transaction.debit"):
            return self._handle_debit(data, attributes)
        elif event_type == "customer.identification.approved":
            return self._handle_kyc_approved(payload)
        elif event_type == "customer.identification.rejected":
            return self._handle_kyc_rejected(payload)
        elif event_type == "customer.identification.error":
            return self._handle_kyc_error(payload)
        else:
            logger.info("Unhandled Anchor webhook event: %s", event_type)
            return Response({"status": "ignored"}, status=status.HTTP_200_OK)

    def _get_account(self, attributes):
        account_id = attributes.get("depositAccount") or attributes.get("accountId")
        account_number = attributes.get("accountNumber")
        if account_id:
            return TreasuryAccount.objects.filter(anchor_account_id=account_id).first()
        if account_number:
            return TreasuryAccount.objects.filter(account_number=account_number).first()
        return None

    def _handle_credit(self, data, attributes):
        account = self._get_account(attributes)
        if not account:
            logger.warning("Anchor credit webhook: account not found %s", attributes.get("accountNumber"))
            return Response({"status": "ok"}, status=status.HTTP_200_OK)

        user = account.user
        kobo = attributes.get("amount", 0)
        amount = Decimal(str(kobo)) / 100
        reference = attributes.get("reference") or data.get("id")
        narration = attributes.get("narration", "Credit")
        balance_after_kobo = attributes.get("balanceAfter", 0)
        balance_after = Decimal(str(balance_after_kobo)) / 100

        # Idempotency: skip if already recorded for this specific user
        if reference and TxModel.objects.filter(user=user, tx_reference=reference).exists():
            logger.info("Duplicate Anchor credit webhook, reference=%s", reference)
            return Response({"status": "ok"}, status=status.HTTP_200_OK)

        # Update cached balance
        account.balance = balance_after
        account.save(update_fields=["balance"])

        TreasuryNotification.objects.create(
            account=account,
            account_number=account.account_number,
            reference=reference,
            narration=narration,
            amount=amount,
            transaction_type="CREDIT",
            balance_after=balance_after,
        )

        if reference:
            TxModel.objects.get_or_create(
                tx_reference=reference,
                defaults={
                    "user": user,
                    "tx_type": "Wallet Credit",
                    "amount": amount,
                    "description": narration,
                    "status": "SUCCESS",
                },
            )

        UserNotification.objects.create(
            user=user,
            title="Credit Alert",
            message=f"Your account has been credited with ₦{amount}.",
        )
        ActivityModel.objects.create(
            user=user,
            title="Wallet Credit",
            description=f"{user.full_name}'s account credited with ₦{amount}. Balance: ₦{balance_after}.",
        )

        # Send SMS/email alert
        alert_type = getattr(user, "alert_type_choice", None)
        if alert_type in ("SMS", "Both") and user.phone_number:
            sms = (
                f"Credit: Acct {account.account_number} | Amt: ₦{float(amount):,.2f} | "
                f"Bal: ₦{float(balance_after):,.2f} | Narration: {narration} | Ref: {reference}"
            )
            Messaging.send_sms(phone_number=user.phone_number[1:], msg=sms)

        if alert_type in ("Email", "Both") and user.email:
            email_context = {
                "title": "Credit Alert",
                "rows": [
                    {"label": "Amount", "value": f"₦{float(amount):,.2f}"},
                    {"label": "Account Number", "value": account.account_number},
                    {"label": "Narration", "value": narration},
                    {"label": "Reference", "value": reference},
                    {"label": "Balance After", "value": f"₦{float(balance_after):,.2f}"},
                ],
                "support_email": "notifications@picadailys.com",
                "picadailys_phone": "02012271894 02012271895",
            }
            html = render_to_string("picadailys_email.html", email_context)
            Messaging.send_email(
                email=user.email,
                subject="Credit Alert",
                html_content=html,
                sender_email="notifications@picadailys.com",
                body=f"Your account has been credited with ₦{amount}.",
            )

        logger.info("Anchor credit: acct=%s amount=₦%s", account.account_number, amount)
        return Response({"status": "ok"}, status=status.HTTP_200_OK)

    def _get_kyc_customer_id(self, payload):
        """Extract customer ID from Anchor's top-level KYC webhook payload."""
        return (
            payload.get("relationships", {})
                   .get("customer", {})
                   .get("data", {})
                   .get("id")
        )

    def _handle_kyc_approved(self, payload):
        customer_id = self._get_kyc_customer_id(payload)

        account = TreasuryAccount.objects.filter(anchor_customer_id=customer_id).first()
        if not account:
            logger.warning("KYC approved webhook: no account for customer_id=%s", customer_id)
            return Response({"status": "ok"}, status=status.HTTP_200_OK)

        user = account.user

        # Determine which tier was pending — process the lowest pending tier first
        if account.tier2_upgrade_status == "PENDING":
            account.tier_level = 2
            account.tier2_upgrade_status = "APPROVED"
            account.save(update_fields=["tier_level", "tier2_upgrade_status"])
            tier_label = "Tier 2"
        elif account.tier3_upgrade_status == "PENDING":
            account.tier_level = 3
            account.tier3_upgrade_status = "APPROVED"
            account.save(update_fields=["tier_level", "tier3_upgrade_status"])
            tier_label = "Tier 3"
        else:
            logger.info("KYC approved webhook: no pending tier for customer=%s", customer_id)
            return Response({"status": "ok"}, status=status.HTTP_200_OK)

        UserNotification.objects.create(
            user=user,
            title="KYC Approved",
            message=f"Your account has been successfully upgraded to {tier_label}.",
        )
        ActivityModel.objects.create(
            user=user,
            title=f"KYC {tier_label} Approved",
            description=f"{getattr(user, 'full_name', str(user))} KYC approved for {tier_label}.",
        )

        alert_type = getattr(user, "alert_type_choice", None)
        if alert_type in ("SMS", "Both") and user.phone_number:
            Messaging.send_sms(
                phone_number=user.phone_number[1:],
                msg=f"Your Picadailys account has been upgraded to {tier_label}. Enjoy higher limits!",
            )
        if alert_type in ("Email", "Both") and user.email:
            html = render_to_string(
                "empty_email.html",
                {
                    "custom_text": (
                        f"Dear {user.first_name},<br><br>"
                        f"Your KYC verification was successful and your account has been upgraded to <b>{tier_label}</b>."
                    ),
                    "support_email": "notifications@picadailys.com",
                    "picadailys_phone": "02012271894 02012271895",
                },
            )
            Messaging.send_email(
                email=user.email,
                subject=f"Account Upgraded to {tier_label}",
                html_content=html,
                sender_email="notifications@picadailys.com",
                body=f"Your account has been upgraded to {tier_label}.",
            )

        logger.info("KYC approved: customer=%s tier=%s", customer_id, tier_label)
        return Response({"status": "ok"}, status=status.HTTP_200_OK)

    def _handle_kyc_rejected(self, payload):
        customer_id = self._get_kyc_customer_id(payload)
        reason = payload.get("attributes", {}).get("reason") or "Verification failed."

        account = TreasuryAccount.objects.filter(anchor_customer_id=customer_id).first()
        if not account:
            logger.warning("KYC rejected webhook: no account for customer_id=%s", customer_id)
            return Response({"status": "ok"}, status=status.HTTP_200_OK)

        user = account.user

        if account.tier2_upgrade_status == "PENDING":
            account.tier2_upgrade_status = "REJECTED"
            account.save(update_fields=["tier2_upgrade_status"])
            tier_label = "Tier 2"
        elif account.tier3_upgrade_status == "PENDING":
            account.tier3_upgrade_status = "REJECTED"
            account.save(update_fields=["tier3_upgrade_status"])
            tier_label = "Tier 3"
        else:
            logger.info("KYC rejected webhook: no pending tier for customer=%s", customer_id)
            return Response({"status": "ok"}, status=status.HTTP_200_OK)

        UserNotification.objects.create(
            user=user,
            title="KYC Rejected",
            message=f"Your {tier_label} KYC verification was rejected. {reason}",
        )
        ActivityModel.objects.create(
            user=user,
            title=f"KYC {tier_label} Rejected",
            description=f"{getattr(user, 'full_name', str(user))} KYC rejected for {tier_label}: {reason}",
        )

        logger.warning("KYC rejected: customer=%s tier=%s reason=%s", customer_id, tier_label, reason)
        return Response({"status": "ok"}, status=status.HTTP_200_OK)

    def _handle_kyc_error(self, payload):
        customer_id = self._get_kyc_customer_id(payload)
        logger.error("KYC error webhook: customer=%s payload=%s", customer_id, payload)
        return Response({"status": "ok"}, status=status.HTTP_200_OK)

    def _handle_debit(self, data, attributes):
        account = self._get_account(attributes)
        if not account:
            logger.warning("Anchor debit webhook: account not found %s", attributes.get("accountNumber"))
            return Response({"status": "ok"}, status=status.HTTP_200_OK)

        user = account.user
        kobo = attributes.get("amount", 0)
        amount = Decimal(str(kobo)) / 100
        reference = attributes.get("reference") or data.get("id")
        narration = attributes.get("narration", "Debit")
        balance_after_kobo = attributes.get("balanceAfter", 0)
        balance_after = Decimal(str(balance_after_kobo)) / 100

        account.balance = balance_after
        account.save(update_fields=["balance"])

        TreasuryNotification.objects.create(
            account=account,
            account_number=account.account_number,
            reference=reference,
            narration=narration,
            amount=amount,
            transaction_type="DEBIT",
            balance_after=balance_after,
        )

        logger.info("Anchor debit: acct=%s amount=₦%s", account.account_number, amount)
        return Response({"status": "ok"}, status=status.HTTP_200_OK)


@extend_schema(
    summary="Paystack webhook for treasury card deposits",
    tags=["Treasury"],
    description="Receives Paystack charge.success webhook events and updates the corresponding treasury card funding record. Validates the Paystack signature before processing.",
    request=inline_serializer(name="PaystackWebhookRequest", fields={
        "event": s.CharField(),
        "data": s.DictField(),
    }),
    responses={
        200: inline_serializer(name="PaystackWebhookResponse", fields={"status": s.CharField()}),
        400: inline_serializer(name="PaystackWebhookError", fields={"status": s.CharField()}),
    },
)
class CardDepositPaystackWebhook(generics.CreateAPIView):
    """
    Handles Paystack webhook events for card deposits into treasury account.
    Equivalent to CardDepositPaystackWebhook in banking.
    """

    def post(self, request, *args, **kwargs):
        paystack_signature = request.headers.get("x-paystack-signature")
        if not paystack_signature:
            return Response(status=status.HTTP_400_BAD_REQUEST)

        computed = hmac.new(
            paystack_secret_key.encode(),
            request.body,
            hashlib.sha512,
        ).hexdigest()

        if not hmac.compare_digest(computed, paystack_signature):
            logger.warning("Invalid Paystack signature on treasury webhook")
            return Response(status=status.HTTP_400_BAD_REQUEST)

        event_type = request.data.get("event")
        if event_type == "charge.success":
            return self._handle_charge_success(request.data)
        return Response({"status": "ignored"}, status=status.HTTP_200_OK)

    def _handle_charge_success(self, webhook_data):
        data = webhook_data.get("data", {})
        reference = data.get("reference")
        email = data.get("customer", {}).get("email")
        tx_status = data.get("status")
        amount = data.get("amount")

        funding = TreasuryCardFunding.objects.filter(txn_reference=reference).first()
        if funding:
            funding.status = tx_status
            funding.email = email
            funding.amount = amount
            funding.save()
            logger.info("Treasury card funding updated: ref=%s status=%s", reference, tx_status)
            return Response({"status": "success"}, status=status.HTTP_200_OK)

        logger.warning("No TreasuryCardFunding found for reference: %s", reference)
        return Response({"status": "not found"}, status=status.HTTP_404_NOT_FOUND)


@extend_schema(
    summary="Verify treasury card payment transaction status",
    tags=["Treasury"],
    description="Returns the current status of a Paystack card deposit by its transaction reference. Use this to confirm a card funding before crediting the treasury account.",
    responses={
        200: inline_serializer(name="TreasuryVerifyCardPaymentResponse", fields={
            "status": s.CharField(),
            "message": s.CharField(),
            "transaction": inline_serializer(name="VerifyCardPaymentTransaction", fields={
                "txn_reference": s.CharField(),
                "amount": s.CharField(),
                "email": s.EmailField(),
                "status": s.CharField(),
            }),
        }),
        404: inline_serializer(name="VerifyCardPaymentNotFound", fields={"status": s.CharField(), "message": s.CharField()}),
    },
)
class VerifyCardPaymentTransaction(generics.GenericAPIView):
    """
    Verify the status of a Paystack card deposit by reference.
    Equivalent to VerifyCardPaymentTransaction in banking.
    """

    authentication_classes = []
    permission_classes = []

    def get(self, request, txn_reference, *args, **kwargs):
        funding = TreasuryCardFunding.objects.filter(txn_reference=txn_reference).first()

        if not funding:
            return Response(
                data={"status": "fail", "message": "No transaction found for this reference."},
                status=status.HTTP_404_NOT_FOUND,
            )

        tx_data = {
            "txn_reference": funding.txn_reference,
            "amount": str(funding.amount),
            "email": funding.email,
            "status": funding.status,
        }

        if funding.status == "success":
            return Response(
                data=encrypt({"status": "success", "message": "Transaction successful.", "transaction": tx_data}),
                status=status.HTTP_200_OK,
            )
        return Response(
            data=encrypt({
                "status": "fail",
                "message": f"Transaction status: {funding.status}.",
                "transaction": tx_data,
            }),
            status=status.HTTP_400_BAD_REQUEST,
        )
