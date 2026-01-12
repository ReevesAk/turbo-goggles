import re
import logging
import base64
import hmac
import hashlib
from decouple import config

from django.http import HttpResponse
from django.views import View

from rest_framework.response import Response
from rest_framework import generics
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework import status

from .models import FundWithCard, WalletModel
from .controllers import Transfers
from .serializers import (
    VerifyCardDepositSerializers,
    WebhookSerializer,
    TransferNotificationWebhookSerializer,
    UpgradeNotificationWebhookSerializer,
)
from accounts.models import UserNotification
from roles.models import ActivityModel
from security import encrypt, decrypt
from permissions import IsAuthenticatedOrGuestWithValidId

logger = logging.getLogger(__name__)

secret_key = config("PAYSTACK_SECRET_KEY")


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

        # Step 3: Extract key details (adjust to your serializer’s fields)
        merchant = webhook_data.get("merchant")
        account_number = webhook_data.get("accountnumber")
        amount = webhook_data.get("amount")
        sender_name = webhook_data.get("sendername")
        nipsessionid = webhook_data.get("nipsessionid")

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

        if merchant == "Picadailys":
            wallet = WalletModel.objects.filter(account_number=account_number).first()

            if wallet:
                # Record notification
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

        return Response(
            {
                "success": True,
                "code": "00",
                "status": "SUCCESS",
                "message": "Acknowledged",
            },
            status=status.HTTP_200_OK,
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
        account_number = webhook_data.get("accountnumber")
        status = webhook_data.get("status")
        message = webhook_data.get("message")

        if status == "Completed":
            wallet = WalletModel.objects.filter(account_number=account_number).first()

            if wallet:
                # Record notification
                UserNotification.objects.create(
                    user=wallet.user,
                    title="Account Upgrade",
                    message=message,
                )

                tier = self.extract_tier(message)
                ActivityModel.objects.create(
                    user=wallet.user,
                    title="Account Upgrade",
                    description=f"{wallet.user.full_name}'s account has been upgraded to {tier}.",
                )

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


class CardDepositPaystackWebhook(generics.CreateAPIView):
    def post(self, request, *args, **kwargs):
        paystack_signature = request.headers.get("x-paystack-signature")
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
            return Response(
                data={"status": "not found"}, status=status.HTTP_404_NOT_FOUND
            )

    def handle_hook_event(self, webhook_data):
        logger.info("Hook event received.")
        return Response(
            data={"status": "hook event processed"}, status=status.HTTP_200_OK
        )


class VerifyCardPaymentTransaction(generics.CreateAPIView):
    """
    VerifyCardPaymentTransaction is the GET request handler that validates
    the supplied single transaction reference and returns the current
    status of the transaction.
    """

    serializer_class = VerifyCardDepositSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticatedOrGuestWithValidId]

    def get(self, request, *args, **kwargs):
        user_data = decrypt(request.data)
        user = request.user
        guest_id = request.headers.get("X-Guest-ID")
        tx_ref = user_data.get("txn_reference")

        user_obj = FundWithCard.objects.filter(
            txn_reference=tx_ref
        ).first()

        if not user_obj:
            return Response(
                data={
                    "status": "fail",
                    "message": "No transaction found for this reference.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if user_obj:
            if user_obj.status == "success":
                resp = {
                    "status": "success",
                    "message": "Transaction was successful.",
                    "transaction": {
                        "txn_reference": user_obj.txn_reference,
                        "amount": str(user_obj.amount),
                        "email": user_obj.email,
                        "status": user_obj.status,
                    },
                }
                encrypted_resp = encrypt(resp)
                if user:
                    UserNotification.objects.create(
                        user=user,
                        title="Card Payment",
                        message=f"Your card payment of {user_obj.amount}, was successful.",
                    )

                    ActivityModel.objects.create(
                        user=user,
                        title="Card Payment",
                        description=f"{user.first_name} {user.last_name} has successfully paid {user_obj.amount} from their card.",
                    )
                elif guest_id:
                    ActivityModel.objects.create(
                        user=guest_id,
                        title="Card Payment",
                        description=f"Guest user: {guest_id} has successfully paid {user_obj.amount} from their card.",
                    )

                return Response(data=encrypted_resp, status=status.HTTP_200_OK)
            else:
                resp = {
                    "status": "fail",
                    "message": f"Transaction is not successful. Current status: {user_obj.status}.",
                    "transaction": {
                        "txn_reference": user_obj.txn_reference,
                        "amount": user_obj.amount,
                        "email": user_obj.email,
                        "status": user_obj.status,
                    },
                }
                if user:
                    UserNotification.objects.create(
                        user=user,
                        title="Card Payment",
                        message=f"Your card payment of {user_obj.amount}, was unsuccessful.",
                    )

                    ActivityModel.objects.create(
                        user=user,
                        title="Card Payment",
                        description=f"Card payment of {user_obj.amount} by {user.first_name} {user.last_name} was unsuccessful.",
                    )
                elif guest_id:
                    ActivityModel.objects.create(
                        user=guest_id,
                        title="Card Payment",
                        description=f"Card payment of {user_obj.amount} by guest user: {guest_id} was unsuccessful.",
                    )
                encrypted_resp = encrypt(resp)
                return Response(data=encrypted_resp, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response(
                data={
                    "status": "fail",
                    "message": "No transaction found for this reference.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )


class RedirectingPageView(View):
    def get(self, request, *args, **kwargs):
        return HttpResponse("Redirecting...")
