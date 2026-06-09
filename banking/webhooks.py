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
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework import status

from drf_spectacular.utils import extend_schema

from .models import FundWithCard, WalletModel, AddressVerificationModel
from .controllers import Transfers
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
from accounts.models import WelcomeBonusAward, WelcomeBonusCounter, Rewards
from banking.helpers import generate_transaction_sms
from commons import Messaging

logger = logging.getLogger(__name__)

secret_key = config("PAYSTACK_SECRET_KEY")


@extend_schema(summary="9PSB webhook dispatcher", tags=["Webhooks"])
class WebhookDispatcherView(generics.GenericAPIView):
    def post(self, request, *args, **kwargs):
        logger.info("Receiving a webhook from 9PSB.....")
        event = request.query_params.get("event")

        if not event:
            return Response(
                {"success": False, "message": "Missing event query parameter"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if event == "transfer":
            return InflowsWebhookNotificationView.as_view()(request._request)

        if event == "account_upgrade":
            return AccountUpgradeWebhookNotificationView.as_view()(request._request)

        return Response(
            {"success": False, "message": f"Unsupported event type: {event}"},
            status=status.HTTP_400_BAD_REQUEST,
        )


@extend_schema(summary="9PSB inflow (credit) webhook", tags=["Webhooks"])
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
                TxModel.objects.get_or_create(
                    tx_reference=nipsessionid,
                    defaults={
                        "user": wallet.user,
                        "tx_type": "Wallet Credit",
                        "amount": amount,
                        "description": f"Credit from {sender_name} ({source_bank}): {description}",
                        "status": "SUCCESS",
                    },
                )

                UserNotification.objects.create(
                    user=wallet.user,
                    title="Wallet Credit",
                    message=f"Your wallet has been credited with ₦{amount} from {sender_name}.",
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
                                already_awarded = WelcomeBonusAward.objects.filter(
                                    user=user
                                ).exists()
                                if (
                                    not already_awarded
                                ) and counter.awarded_count < 1000:
                                    WelcomeBonusAward.objects.create(
                                        user=user, amount=Decimal("500.00")
                                    )
                                    counter.awarded_count = counter.awarded_count + 1
                                    counter.save()

                                    rewards, _ = Rewards.objects.get_or_create(
                                        user=user
                                    )
                                    try:
                                        current = Decimal(str(rewards.balance))
                                    except Exception:
                                        current = Decimal("0.00")
                                    rewards.balance = current + Decimal("500.00")
                                    rewards.save()

                                    try:
                                        user.welcome_bonus = 500
                                        user.has_bonus = True
                                        user.save()
                                    except Exception:
                                        logger.exception(
                                            "Failed to set user flags after welcome award"
                                        )

                                    UserNotification.objects.create(
                                        user=user,
                                        title="Welcome Bonus",
                                        message="You have been credited with a ₦500 welcome bonus. Use it for purchases.",
                                    )
                                    ActivityModel.objects.create(
                                        user=user,
                                        title="Welcome Bonus",
                                        description=f"{user.first_name} {user.last_name} was awarded a ₦500 welcome bonus.",
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


@extend_schema(summary="9PSB account upgrade webhook", tags=["Webhooks"])
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
        account_number = webhook_data.get("accountnumber")
        status = webhook_data.get("status")
        message = webhook_data.get("message")

        if status == "Completed":
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

        return Response(
            {
                "success": True,
                "code": "00",
                "status": "SUCCESS",
                "message": "Acknowledged",
            },
            status=status.HTTP_200_OK,
        )

    def extract_tier(self, message: str):
        match = re.search(r"upgraded to\s+(\w+)", message, re.IGNORECASE)
        return match.group(1) if match else None


@extend_schema(summary="Paystack card deposit webhook", tags=["Webhooks"])
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
        amount = webhook_data["data"]["amount"]  # Convert kobo to naira

        user_obj = FundWithCard.objects.filter(txn_reference=reference).first()
        if user_obj:
            user_obj.status = tx_status
            user_obj.email = email
            user_obj.amount = amount
            user_obj.save()

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


@extend_schema(summary="Verify card payment transaction status", tags=["Banking"])
class VerifyCardPaymentTransaction(generics.GenericAPIView):
    """
    VerifyCardPaymentTransaction is the GET request handler that validates
    the supplied single transaction reference and returns the current
    status of the transaction.
    """

    authentication_classes = [JWTAuthentication]
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
        else:
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


class RedirectingPageView(View):
    def get(self, request, *args, **kwargs):
        return HttpResponse("Redirecting...")


class DojahRedirectingPageView(View):
    def get(self, request, *args, **kwargs):
        return HttpResponse("Address verification done, redirecting page...")


@extend_schema(summary="Dojah address verification webhook", tags=["Webhooks"])
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
