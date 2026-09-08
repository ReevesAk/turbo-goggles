import re
import logging
import base64
import hmac
import hashlib
from decouple import config

from banking.controllers import Wallet

from django.http import HttpResponse
from django.views import View
from django.template.loader import render_to_string

from rest_framework.response import Response
from rest_framework import generics
from rest_framework import status

from drf_spectacular.utils import extend_schema, OpenApiParameter, inline_serializer
from drf_spectacular.types import OpenApiTypes
import rest_framework.serializers as s

from .models import FundWithCard, WalletModel, AddressVerificationModel
from .controllers import Transfers, Paystack
from .serializers import (
    WebhookSerializer,
    TransferNotificationWebhookSerializer,
    UpgradeNotificationWebhookSerializer,
)
from accounts.models import UserNotification, User, TxModel
from roles.models import ActivityModel
from security import encrypt
from permissions import IsAuthenticatedOrGuestWithValidId
from decimal import Decimal
from django.db import transaction
from accounts.models import WelcomeBonusAward, WelcomeBonusCounter
from banking.helpers import generate_transaction_sms
from commons import Messaging
from user_profile.fcm import send_push_to_user

logger = logging.getLogger(__name__)

secret_key = config("PAYSTACK_SECRET_KEY")


@extend_schema(
    summary="9PSB webhook dispatcher",
    tags=["Webhooks"],
    description="Entry-point webhook called by 9PSB. Dispatches to the appropriate handler based on the `event` query parameter (transfer or account_upgrade).",
    exclude=True,
)
class WebhookDispatcherView(generics.GenericAPIView):
    def post(self, request, *args, **kwargs):
        logger.info("Receiving a webhook from 9PSB.....")
        event = request.query_params.get("event")

        if not event:
            return Response(
                {"success": False, "message": "Missing event query parameter"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 9PSB sends "account-upgrade" (hyphen) in production, not
        # "account_upgrade" (underscore) - confirmed from real request URLs
        # in the server logs. Normalizing here since we can't get an
        # external provider to change what they send; this exact mismatch
        # silently dropped every account-upgrade webhook call for months
        # with no error/log trail (a clean 400 doesn't get logged).
        normalized_event = event.replace("-", "_")

        if normalized_event == "transfer":
            return InflowsWebhookNotificationView.as_view()(request._request)

        if normalized_event == "account_upgrade":
            return AccountUpgradeWebhookNotificationView.as_view()(request._request)

        logger.warning(f"Unsupported webhook event type received: {event!r}")
        return Response(
            {"success": False, "message": f"Unsupported event type: {event}"},
            status=status.HTTP_400_BAD_REQUEST,
        )


@extend_schema(
    summary="9PSB inflow (credit) webhook",
    tags=["Webhooks"],
    description="Called by 9PSB when a credit arrives on a Picadailys wallet. Verifies Basic Auth, re-queries the transaction via NIP session ID, updates the wallet balance, and notifies the user.",
    exclude=True,
)
class InflowsWebhookNotificationView(generics.CreateAPIView):
    serializer_class = TransferNotificationWebhookSerializer

    # Credentials you registered with 9PSB
    EXPECTED_USERNAME = config("NINE_PSB_WEBHOOK_USERNAME")
    EXPECTED_PASSWORD = config("NINE_PSB_WEBHOOK_PASSWORD")

    def verify_basic_auth(self, request):
        """Validate Basic Auth header."""
        auth_header = request.headers.get("Authorization")

        if not auth_header or not auth_header.startswith("Basic "):
            return Response(
                {
                    "success": False,
                    "code": "401",
                    "status": "FAILED",
                    "message": "Missing or invalid Authorization header",
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )

        try:
            encoded_credentials = auth_header.split(" ")[1]
            decoded_credentials = base64.b64decode(encoded_credentials).decode("utf-8")
            username, password = decoded_credentials.split(":", 1)
        except Exception:
            return Response(
                {
                    "success": False,
                    "code": "400",
                    "status": "FAILED",
                    "message": "Invalid Basic Auth format or encoding",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if username != self.EXPECTED_USERNAME or password != self.EXPECTED_PASSWORD:
            return Response(
                {
                    "success": False,
                    "code": "401",
                    "status": "FAILED",
                    "message": "Invalid username or password",
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )

        return None  # Auth passed

    def post(self, request, *args, **kwargs):
        # Step 1: Validate Basic Auth
        auth_error = self.verify_basic_auth(request)
        if auth_error:
            return auth_error

        # Step 2: Validate payload
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        webhook_data = serializer.validated_data

        logger.info(f"Received 9PSB inflow webhook: {webhook_data}")

        user = None
        wallet = None

        # Step 3: Extract key details (adjust to your serializer’s fields)
        merchant = webhook_data.get("merchant")
        account_number = webhook_data.get("accountnumber")
        amount = webhook_data.get("amount")
        sender_name = webhook_data.get("sendername")
        nipsessionid = webhook_data.get("nipsessionid")
        source_bank = webhook_data.get("sourcebank")
        description = webhook_data.get("narration")
        source_account = webhook_data.get("sourceaccount")

        requery_request = Transfers.tx_requery(
            sessionID=nipsessionid, accountNumber=account_number
        )

        status_msg = requery_request.json().get("status")
        if not status_msg == "SUCCESS":
            return Response(
                {
                    "success": False,
                    "code": "400",
                    "status": "FAILED",
                    "message": f"Got a {status_msg} status message.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if merchant == "PICADAILYS":
            wallet = WalletModel.objects.filter(account_number=account_number).first()
            user = wallet.user if wallet else None

            logger.info(
                f"Received 9PSB inflow webhook for user: {user.first_name} {user.last_name}"
            )

            # Idempotency guard — if we already processed this session ID, ack and stop
            if wallet and TxModel.objects.filter(tx_reference=nipsessionid).exists():
                logger.info(
                    f"Duplicate webhook for nipsessionid={nipsessionid}, skipping."
                )
                return Response(
                    {"success": True, "message": "Already processed."},
                    status=status.HTTP_200_OK,
                )

            # Send SMS and Email notification for wallet credit
            if (
                wallet
                and user
                and getattr(user, "alert_type_choice", None) in ("SMS", "Both")
            ):
                # Add source bank and account to the SMS description
                inflow_desc = f"{description} (From: {source_bank} - {source_account})"
                # Fetch latest balance using wallet enquiry
                latest_balance = wallet.balance
                if wallet.account_number:
                    enquiry_resp = Wallet.getWalletDetails(wallet.account_number)
                    if enquiry_resp and hasattr(enquiry_resp, "json"):
                        enquiry_data = enquiry_resp.json()
                        if isinstance(enquiry_data, dict):
                            bal = enquiry_data.get("data", {}).get("availableBalance")
                            if bal is not None:
                                latest_balance = bal
                sms_msg = generate_transaction_sms(
                    transaction_type="CREDIT",
                    account_number=wallet.account_number,
                    amount=amount,
                    balance=latest_balance,
                    description=inflow_desc,
                    reference=nipsessionid,
                )
                logger.info(f"SMS MSG TYPE: {sms_msg}")
                logger.info(
                    f"Sending SMS to {wallet.user.phone_number} with message: {sms_msg}"
                )
                Messaging.send_sms(
                    phone_number=wallet.user.phone_number[1:],
                    msg=sms_msg,
                )
            if (
                wallet
                and user
                and getattr(user, "alert_type_choice", None) in ("Email", "Both")
            ):
                # Send email notification using picadailys_email.html
                email_subject = "Credit Alert"
                email_context = {
                    "title": "Credit Alert",
                    "rows": [
                        {"label": "Amount", "value": f"₦{amount}"},
                        {"label": "Account Number", "value": wallet.account_number},
                        {"label": "Sender", "value": sender_name},
                        {"label": "Source Bank", "value": source_bank},
                        {"label": "Source Account", "value": source_account},
                        {"label": "Narration", "value": description},
                        {"label": "Reference", "value": nipsessionid},
                        {"label": "Transaction Type", "value": "Credit"},
                    ],
                    "support_email": "notifications@picadailys.com",
                    "picadailys_phone": "02012271894 02012271895",
                }
                email_body = render_to_string("picadailys_email.html", email_context)
                if getattr(user, "email", None):
                    Messaging.send_email(
                        email=user.email,
                        subject=email_subject,
                        html_content=email_body,
                        sender_email="notifications@picadailys.com",
                        body=email_body,
                    )

            if wallet:
                TxModel.objects.create(
                    tx_reference=nipsessionid,
                    user=wallet.user,
                    tx_type="Wallet Credit",
                    amount=amount,
                    description=f"Credit from {sender_name} ({source_bank}): {description}",
                    status="SUCCESS",
                )

                # This same webhook fires for every inbound transfer,
                # including the internal one Wallet.Credit triggers to
                # settle a card funding (see FundWallet) - recognizable by
                # its narration, which is literally the reason string we
                # passed to Wallet.Credit. This is the first point where the
                # real, net-of-9PSB-fee amount is known, so it's where the
                # one card-funding notification is sent; genuine third-party
                # transfers get their usual notification instead.
                is_card_funding_settlement = (description or "").startswith(
                    "You funded your wallet with"
                )

                if is_card_funding_settlement:
                    UserNotification.objects.create(
                        user=wallet.user,
                        title="Wallet Funded",
                        message=f"You have successfully funded your wallet with ₦{amount} via card.",
                    )

                    send_push_to_user(
                        user=wallet.user,
                        title="Wallet Funded 💳",
                        body=f"You have successfully funded your wallet with ₦{amount} via card.",
                        data={
                            "type": "card_deposit",
                            "amount": str(amount),
                            "reference": nipsessionid,
                        },
                    )
                else:
                    UserNotification.objects.create(
                        user=wallet.user,
                        title="Wallet Credit",
                        message=f"Your wallet has been credited with ₦{amount} from {sender_name}.",
                    )

                    send_push_to_user(
                        user=wallet.user,
                        title="INCOMING TRANSFER 💰",
                        body=f"₦{amount} from {sender_name} ({source_bank}) has been credited to your wallet.",
                        data={
                            "type": "wallet_credit",
                            "amount": str(amount),
                            "reference": nipsessionid,
                        },
                    )

                ActivityModel.objects.create(
                    user=wallet.user,
                    title="Wallet Credit",
                    description=f"{wallet.user.full_name}'s wallet credited with ₦{amount}.",
                )

                logger.info(
                    f"Wallet {account_number} successfully credited with ₦{amount}."
                )

                # Attempt to award welcome bonus if eligibility met
                try:
                    try:
                        credited_amount = Decimal(str(amount))
                    except Exception:
                        credited_amount = Decimal("0.00")

                    if credited_amount >= Decimal("2000.00"):
                        try:
                            with transaction.atomic():
                                counter, _ = WelcomeBonusCounter.objects.get_or_create(
                                    id=1
                                )
                                counter = (
                                    WelcomeBonusCounter.objects.select_for_update().get(
                                        id=counter.id
                                    )
                                )

                                # user is already set above
                                if (
                                    not user.has_received_welcome_bonus
                                ) and counter.awarded_count < 1000:
                                    WelcomeBonusAward.objects.create(
                                        user=user, amount=Decimal("500.00")
                                    )
                                    counter.awarded_count = counter.awarded_count + 1
                                    counter.save()

                                    try:
                                        individual_wallet = WalletModel.objects.get(
                                            user=user, walletType="INDIVIDUAL"
                                        )
                                        individual_wallet.cashback_balance += Decimal(
                                            "500.00"
                                        )
                                        individual_wallet.save(
                                            update_fields=["cashback_balance"]
                                        )
                                        user.has_received_welcome_bonus = True
                                        user.save(
                                            update_fields=["has_received_welcome_bonus"]
                                        )
                                    except Exception:
                                        logger.exception(
                                            "Failed to set user flags after welcome award"
                                        )

                                    UserNotification.objects.create(
                                        user=user,
                                        title="Welcome Bonus",
                                        message="You have been credited with a ₦500 cashback welcome bonus. Use it for purchases.",
                                    )
                                    send_push_to_user(
                                        user=user,
                                        title="Welcome Bonus! 🎁",
                                        body="You've been credited with a ₦500 cashback welcome bonus. Start shopping!",
                                        data={"type": "welcome_bonus", "amount": "500"},
                                    )
                                    ActivityModel.objects.create(
                                        user=user,
                                        title="Welcome Bonus",
                                        description=f"{user.first_name} {user.last_name} was awarded a ₦500 cashback welcome bonus.",
                                    )
                        except Exception:
                            logger.exception(
                                "Error awarding welcome bonus inside transaction"
                            )
                except Exception:
                    logger.exception(
                        "Unexpected error while attempting to award welcome bonus"
                    )

        return Response(
            {
                "success": True,
                "code": "00",
                "status": "SUCCESS",
                "message": "Acknowledged",
            },
            status=status.HTTP_200_OK,
        )


@extend_schema(
    summary="9PSB account upgrade webhook",
    tags=["Webhooks"],
    description="Called by 9PSB when a Tier 2 upgrade request is approved or rejected. Verifies Basic Auth, updates the wallet tier level (or marks it DECLINED with a reason on any non-'Completed' status), and sends an SMS/email/in-app alert to the account holder either way.",
    exclude=True,
)
class AccountUpgradeWebhookNotificationView(generics.CreateAPIView):
    serializer_class = UpgradeNotificationWebhookSerializer

    # Credentials you registered with 9PSB
    EXPECTED_USERNAME = config("NINE_PSB_WEBHOOK_USERNAME")
    EXPECTED_PASSWORD = config("NINE_PSB_WEBHOOK_PASSWORD")

    def verify_basic_auth(self, request):
        """Validate Basic Auth header."""
        auth_header = request.headers.get("Authorization")

        if not auth_header or not auth_header.startswith("Basic "):
            return Response(
                {
                    "success": False,
                    "code": "401",
                    "status": "FAILED",
                    "message": "Missing or invalid Authorization header",
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )

        try:
            encoded_credentials = auth_header.split(" ")[1]
            decoded_credentials = base64.b64decode(encoded_credentials).decode("utf-8")
            username, password = decoded_credentials.split(":", 1)
        except Exception:
            return Response(
                {
                    "success": False,
                    "code": "400",
                    "status": "FAILED",
                    "message": "Invalid Basic Auth format or encoding",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if username != self.EXPECTED_USERNAME or password != self.EXPECTED_PASSWORD:
            return Response(
                {
                    "success": False,
                    "code": "401",
                    "status": "FAILED",
                    "message": "Invalid username or password",
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )

        return None  # Auth passed

    def post(self, request, *args, **kwargs):
        # Step 1: Validate Basic Auth
        auth_error = self.verify_basic_auth(request)
        if auth_error:
            return auth_error

        # Step 2: Validate payload
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        webhook_data = serializer.validated_data

        logger.info(f"Received 9PSB account upgrade webhook: {webhook_data}")

        # Step 3: Extract key details (adjust to your serializer’s fields)
        # Named upgrade_status, not status - "status" is also the imported
        # rest_framework module this method needs for status.HTTP_200_OK
        # below; a local var of the same name silently shadowed it and
        # crashed every single call to this endpoint with "AttributeError:
        # 'str' object has no attribute 'HTTP_200_OK'" right after the
        # wallet was already updated - found via testing, not previously
        # caught since the only existing test only exercises the
        # auth/validation failure path.
        account_number = webhook_data.get("accountNumber")
        upgrade_status = webhook_data.get("status")
        message = webhook_data.get("message")

        if upgrade_status == "Completed":
            wallet = WalletModel.objects.filter(account_number=account_number).first()
            user = wallet.user if wallet else None

            if wallet and user:
                tier = self.extract_tier(message)
                alert_type = getattr(user, "alert_type_choice", None)

                if alert_type in ("SMS", "Both"):
                    sms_msg = f"Dear {user.first_name}, your account with number {account_number} has been upgraded. Your new tier level is {tier}. Enjoy enhanced features and benefits with your upgraded account."
                    logger.info(
                        f"Sending SMS to {user.phone_number} with message: {sms_msg}"
                    )
                    Messaging.send_sms(
                        phone_number=user.phone_number[1:],
                        msg=sms_msg,
                    )

                if alert_type in ("Email", "Both"):
                    try:
                        email_body = f"Dear {user.full_name},<br><br>Your account with number <strong>{account_number}</strong> has been successfully upgraded to <strong>{tier}</strong>.<br><br>You can now enjoy enhanced features and benefits with your upgraded account."
                        text_content = render_to_string(
                            template_name="empty_email.html",
                            context={
                                "custom_text": email_body,
                                "support_email": "support@picadailys.com",
                                "picadailys_phone": "02012271894  02012271895",
                            },
                        )
                        Messaging.send_email(
                            email=user.email,
                            html_content=text_content,
                            subject="Your Picadailys Account Has Been Upgraded",
                            sender_email="notifications@picadailys.com",
                            body=f"Dear {user.full_name}, your account {account_number} has been upgraded to {tier}.",
                        )
                        logger.info(f"Account upgrade email sent to {user.email}")
                    except Exception as e:
                        logger.error(
                            f"Failed to send account upgrade email to {user.email}: {e}"
                        )

            if wallet:
                # Record notification
                UserNotification.objects.create(
                    user=user,
                    title="Account Upgrade",
                    message=message,
                )
                send_push_to_user(
                    user=user,
                    title="Account Upgraded! 🚀",
                    body=f"Your wallet has been upgraded to {self.extract_tier(message)} tier. Enjoy enhanced benefits.",
                    data={"type": "account_upgrade", "account_number": account_number},
                )

                tier = self.extract_tier(message)
                ActivityModel.objects.create(
                    user=user,
                    title="Account Upgrade",
                    description=f"{user.full_name}'s account has been upgraded to {tier}.",
                )
                wallet.tier_level = tier
                wallet.tier2_upgrade_status = "APPROVED"
                wallet.save(update_fields=["tier_level", "tier2_upgrade_status"])

                logger.info(f"Wallet: {account_number} successfully upgraded.")

        else:
            logger.warning(
                f"9PSB account upgrade not completed: status={upgrade_status!r} "
                f"account={account_number} message={message!r}"
            )
            wallet = WalletModel.objects.filter(account_number=account_number).first()
            user = wallet.user if wallet else None
            reason = message or "No reason was provided by the provider."

            if wallet and user:
                alert_type = getattr(user, "alert_type_choice", None)

                if alert_type in ("SMS", "Both"):
                    sms_msg = f"Dear {user.first_name}, your account upgrade request for {account_number} was not approved. Reason: {reason}"
                    Messaging.send_sms(
                        phone_number=user.phone_number[1:],
                        msg=sms_msg,
                    )

                if alert_type in ("Email", "Both"):
                    try:
                        email_body = f"Dear {user.full_name},<br><br>Your account upgrade request for <strong>{account_number}</strong> was not approved.<br><br>Reason: {reason}<br><br>You're welcome to correct the issue and submit a new upgrade request."
                        text_content = render_to_string(
                            template_name="empty_email.html",
                            context={
                                "custom_text": email_body,
                                "support_email": "support@picadailys.com",
                                "picadailys_phone": "02012271894  02012271895",
                            },
                        )
                        Messaging.send_email(
                            email=user.email,
                            html_content=text_content,
                            subject="Your Picadailys Account Upgrade Was Not Approved",
                            sender_email="notifications@picadailys.com",
                            body=f"Dear {user.full_name}, your account {account_number} upgrade request was not approved. Reason: {reason}.",
                        )
                        logger.info(
                            f"Account upgrade rejection email sent to {user.email}"
                        )
                    except Exception as e:
                        logger.error(
                            f"Failed to send account upgrade rejection email to {user.email}: {e}"
                        )

            if wallet:
                UserNotification.objects.create(
                    user=user,
                    title="Account Upgrade Not Approved",
                    message=reason,
                )
                send_push_to_user(
                    user=user,
                    title="Account Upgrade Not Approved",
                    body=reason,
                    data={
                        "type": "account_upgrade_declined",
                        "account_number": account_number,
                    },
                )
                ActivityModel.objects.create(
                    user=user,
                    title="Account Upgrade Declined",
                    description=f"{user.full_name}'s account upgrade request for {account_number} was declined. Reason: {reason}.",
                )
                wallet.tier2_upgrade_status = "DECLINED"
                wallet.save(update_fields=["tier2_upgrade_status"])

                logger.info(
                    f"Wallet: {account_number} upgrade declined. Reason: {reason}"
                )

        return Response(
            {
                "success": True,
                "code": "00",
                "status": "success",
                "message": "Acknowledged",
            },
            status=status.HTTP_200_OK,
        )

    def extract_tier(self, message: str):
        match = re.search(
            r"upgraded\s+to\s+(?:tier\s*)?\(?([23])\)?",
            message or "",
            re.IGNORECASE,
        )
        return match.group(1) if match else None


@extend_schema(
    summary="Paystack card deposit webhook",
    tags=["Webhooks"],
    description="Called by Paystack when a card charge event fires. Validates the HMAC-SHA512 signature, handles charge.success events, and updates the FundWithCard record accordingly.",
    exclude=True,
)
class CardDepositPaystackWebhook(generics.CreateAPIView):
    def post(self, request, *args, **kwargs):
        paystack_signature = request.headers.get("x-paystack-signature")
        if not paystack_signature:
            logger.warning("Missing Paystack signature")
            return Response(status=status.HTTP_400_BAD_REQUEST)

        computed_signature = hmac.new(
            secret_key.encode(),
            request.body,
            hashlib.sha512,
        ).hexdigest()

        if not hmac.compare_digest(computed_signature, paystack_signature):
            logger.warning("Invalid Paystack signature")
            return Response(status=status.HTTP_400_BAD_REQUEST)

        # Validate the incoming data using the serializer
        serializer = WebhookSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)  # Raise an error if validation fails

        webhook_data = serializer.validated_data  # Get validated data

        # Handle different events
        event_type = webhook_data.get("event")
        if event_type == "charge.success":
            return self.handle_charge_success(webhook_data)
        elif event_type == "hook":
            return self.handle_hook_event(webhook_data)
        else:
            logger.error(f"Unhandled event type: {event_type}")
            return Response(
                data={"status": "event not handled"}, status=status.HTTP_400_BAD_REQUEST
            )

    def handle_charge_success(self, webhook_data):
        transaction_id = webhook_data["data"]["id"]
        reference = webhook_data["data"]["reference"]
        email = webhook_data["data"]["customer"]["email"]
        tx_status = webhook_data["data"]["status"]
        # Paystack sends amount in kobo.
        amount = (Decimal(str(webhook_data["data"]["amount"])) / 100).quantize(
            Decimal("0.01")
        )

        user_obj = FundWithCard.objects.filter(txn_reference=reference).first()
        if user_obj:
            user_obj.status = tx_status
            user_obj.email = email
            user_obj.amount = amount
            user_obj.save()

            # No notification here: the real net amount (after 9PSB's own
            # transfer fee) isn't known yet at this point - only Paystack's
            # charge has been confirmed, the internal wallet settlement
            # hasn't happened. The one notification for a card funding is
            # sent from InflowsWebhookNotificationView once that settlement
            # lands and the true credited amount is known.

            logger.info(
                f"Transaction {transaction_id} was successful. Updated user: {email}"
            )
            return Response(data={"status": "success"}, status=status.HTTP_200_OK)
        else:
            logger.warning(f"No FundWithCard entry found for reference: {reference}")
            return Response(data={"status": "received"}, status=status.HTTP_200_OK)

    def handle_hook_event(self, webhook_data):
        logger.info("Hook event received.")
        return Response(
            data={"status": "hook event processed"}, status=status.HTTP_200_OK
        )


@extend_schema(
    summary="Verify card payment transaction status",
    tags=["Banking"],
    description="Look up the status of a Paystack card payment by transaction reference. Accessible by both authenticated users and guest users (via X-Guest-ID header).",
    parameters=[
        OpenApiParameter(
            name="txn_reference",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.PATH,
            required=True,
            description="The Paystack transaction reference to check.",
        ),
        OpenApiParameter(
            name="X-Guest-ID",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.HEADER,
            required=False,
            description="Guest identifier; required when the caller is not an authenticated user.",
        ),
    ],
    responses={
        200: inline_serializer(
            name="BankingVerifyCardPaymentResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "transaction": inline_serializer(
                    name="CardPaymentTransactionData",
                    fields={
                        "txn_reference": s.CharField(),
                        "amount": s.CharField(),
                        "email": s.EmailField(),
                        "status": s.CharField(),
                    },
                ),
            },
        ),
        404: inline_serializer(
            name="VerifyCardPaymentNotFoundResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        400: inline_serializer(
            name="VerifyCardPaymentFailedResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class VerifyCardPaymentTransaction(generics.GenericAPIView):
    """
    VerifyCardPaymentTransaction is the GET request handler that validates
    the supplied single transaction reference and returns the current
    status of the transaction.
    """

    permission_classes = [IsAuthenticatedOrGuestWithValidId]

    def get(self, request, *args, **kwargs):
        user = request.user
        guest_id = request.headers.get("X-Guest-ID")
        tx_ref = kwargs.get("txn_reference")

        transaction = FundWithCard.objects.filter(txn_reference=tx_ref).first()

        if not transaction:
            return Response(
                data={
                    "status": "fail",
                    "message": "No transaction found for this reference.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # The webhook may not have landed yet — ask Paystack directly rather
        # than making the caller wait on webhook delivery.
        if transaction.status != "success":
            try:
                live_data = Paystack.verify_transaction(tx_ref).get("data", {})
            except Exception:
                logger.exception(
                    "Paystack verify_transaction failed for reference=%s", tx_ref
                )
                live_data = {}

            live_status = live_data.get("status")
            if live_status == "success":
                transaction.status = "success"
                if "amount" in live_data:
                    # Paystack sends amount in kobo.
                    transaction.amount = (
                        Decimal(str(live_data["amount"])) / 100
                    ).quantize(Decimal("0.01"))
                transaction.email = live_data.get("customer", {}).get(
                    "email", transaction.email
                )
                transaction.save(update_fields=["status", "amount", "email"])
            elif live_status in ("failed", "abandoned"):
                transaction.status = live_status
                transaction.save(update_fields=["status"])
            # else: still pending on Paystack's side too — leave as-is,
            # don't fire a false "unsuccessful" notification below.

        transaction_data = {
            "txn_reference": transaction.txn_reference,
            "amount": str(transaction.amount),
            "email": transaction.email,
            "status": transaction.status,
        }

        if transaction.status == "success":
            resp = {
                "status": "success",
                "message": "Transaction was successful.",
                "transaction": transaction_data,
            }

            encrypted_resp = encrypt(resp)
            if user.is_authenticated:
                UserNotification.objects.create(
                    user=user,
                    title="Card Payment",
                    message=f"Your card payment of {transaction.amount}, was successful.",
                )

                ActivityModel.objects.create(
                    user=user,
                    title="Card Payment",
                    description=f"{user.first_name} {user.last_name} has successfully paid {transaction.amount} from their card.",
                )
            elif guest_id:
                ActivityModel.objects.create(
                    user=None,
                    title="Card Payment",
                    description=f"Guest user: {guest_id} has successfully paid {transaction.amount} from their card.",
                )

            return Response(data=encrypted_resp, status=status.HTTP_200_OK)
        elif transaction.status in ("failed", "abandoned"):
            resp = {
                "status": "fail",
                "message": f"Transaction is not successful. Current status: {transaction.status}.",
                "transaction": transaction_data,
            }
            if user.is_authenticated:
                UserNotification.objects.create(
                    user=user,
                    title="Card Payment",
                    message=f"Your card payment of {transaction.amount}, was unsuccessful.",
                )

                ActivityModel.objects.create(
                    user=user,
                    title="Card Payment",
                    description=f"Card payment of {transaction.amount} by {user.first_name} {user.last_name} was unsuccessful.",
                )
            elif guest_id:
                ActivityModel.objects.create(
                    user=None,
                    title="Card Payment",
                    description=f"Card payment of {transaction.amount} by guest user: {guest_id} was unsuccessful.",
                )
            encrypted_resp = encrypt(resp)
            return Response(data=encrypted_resp, status=status.HTTP_400_BAD_REQUEST)
        else:
            # Neither our webhook nor a live Paystack check has resolved this
            # yet — genuinely still pending, not a failure. No notification;
            # the caller is expected to poll again shortly.
            resp = {
                "status": "pending",
                "message": "Transaction is still processing. Please check again shortly.",
                "transaction": transaction_data,
            }
            return Response(data=encrypt(resp), status=status.HTTP_202_ACCEPTED)


class RedirectingPageView(View):
    def get(self, request, *args, **kwargs):
        return HttpResponse("Redirecting...")


class DojahRedirectingPageView(View):
    def get(self, request, *args, **kwargs):
        return HttpResponse("Address verification done, redirecting page...")


@extend_schema(
    summary="Dojah address verification webhook",
    tags=["Webhooks"],
    description="Called by Dojah when an address verification widget session completes. Updates the AddressVerificationModel status and triggers the Tier 3 wallet upgrade pipeline.",
    exclude=True,
)
class AddressVerificationWebhookView(generics.GenericAPIView):
    """
    AddressVerificationWebhookView handles POST webhooks from the address verification service.
    It looks up the user by the third-party reference_id, validates the webhook,
    and updates their address verification status.
    """

    def post(self, request, *args, **kwargs):
        try:
            webhook_data = request.data
            logger.info(f"Received address verification webhook: {webhook_data}")

            # Extract verification details from webhook
            entity = webhook_data.get("entity", {})
            verification_status = entity.get(
                "status"
            )  # e.g., "pending", "approved", "rejected"
            data = entity.get("data", {})
            user_id = entity.get("reference_id")
            applicant = data.get("applicant", {})

            if user_id:
                # Direct match by user_id in metadata
                try:
                    address_verification = AddressVerificationModel.objects.filter(
                        reference_id=str(user_id)
                    ).first()
                except Exception as e:
                    logger.warning(f"Error looking up by user_id {user_id}: {e}")
                    address_verification = None
            else:
                address_verification = None

            # Fallback: if metadata user_id didn't work,
            if not address_verification:
                intended_user = User.objects.get(id=user_id)
                if intended_user.first_name != applicant.get(
                    "first_name"
                ) or intended_user.last_name != applicant.get("last_name"):
                    logger.warning(f"User name mismatch for user_id {user_id}")
                    logger.warning(
                        f"No address verification found for user_id {user_id} or by applicant data"
                    )
                    return Response(
                        {
                            "success": False,
                            "message": "Address verification request not found",
                        },
                        status=status.HTTP_404_NOT_FOUND,
                    )

            user = address_verification.user
            if not user:
                logger.warning(f"Address verification {user_id} has no associated user")
                return Response(
                    {
                        "success": False,
                        "message": "User not found for verification request",
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Update address verification record based on webhook status
            if verification_status == "approved" or verification_status == "success":
                address_verification.status = "Success"
                address_verification.has_verified_address = True
                address_verification.save()

                logger.info(f"Address verification approved for user {user.id}")

                return Response(
                    {
                        "success": True,
                        "message": "Address verification approved successfully.",
                        "status": "success",
                    },
                    status=status.HTTP_200_OK,
                )

            elif verification_status == "rejected" or verification_status == "failure":
                address_verification.status = "Failure"
                address_verification.has_verified_address = False
                address_verification.save()

                # Notify user of failed verification
                UserNotification.objects.create(
                    user=user,
                    title="Address Verification Failed",
                    message="Your address verification failed. Please try again or contact support.",
                )

                ActivityModel.objects.create(
                    user=user,
                    title="Address Verification Failed",
                    description=f"{user.first_name} {user.last_name}'s address verification was rejected.",
                )

                logger.warning(f"Address verification failed for user {user.id}")

                return Response(
                    {
                        "success": True,
                        "message": "Address verification status updated (failed).",
                        "status": "failure",
                    },
                    status=status.HTTP_200_OK,
                )

            elif verification_status == "pending":
                # Webhook indicates verification is still pending; no action needed yet
                logger.info(f"Address verification still pending for user {user.id}")
                return Response(
                    {
                        "success": True,
                        "message": "Address verification status is still pending.",
                        "status": "pending",
                    },
                    status=status.HTTP_200_OK,
                )

            else:
                logger.warning(f"Unknown verification status: {verification_status}")
                return Response(
                    {
                        "success": False,
                        "message": f"Unknown verification status: {verification_status}",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        except Exception as e:
            logger.exception(f"Error processing address verification webhook: {e}")
            return Response(
                {
                    "success": False,
                    "message": "Internal server error processing webhook",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
