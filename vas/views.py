import os
import json
import logging
import requests
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.template.loader import render_to_string

from rest_framework.views import APIView
from rest_framework import generics, status
from rest_framework.response import Response

# from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication

from drf_spectacular.utils import (
    extend_schema,
    OpenApiResponse,
)

from .serializers import (
    VasStatusSerializer,
    VerifyBillerSerializer,
    AirtimeTopupSerializer,
    DataSubscriptionSerializer,
    BillPaymentSerializer,
)
from accounts.models import TxModel
from banking.models import WalletModel
from banking.controllers import Wallet
from banking.cashback_service import CashbackService
from banking.tasks import send_transfer_notifications
from permissions import IsAuthenticatedOrGuestWithValidId
from banking.helpers import Pin, verify_wallet_auth
from banking.cashback_service import CashbackService
from gamification.points import Points
from gamification.utils import NextBee

from .utility import (
    create_activity,
    create_notification,
    # send_token,
    # send_token_to_guest_users,
)
from .helpers import VAS
from .models import ValueAddedServices
from commons import Pay, Biometrics, Messaging
from banking.helpers import generate_transaction_sms
from security import encrypt, decrypt

logger = logging.getLogger(__name__)


class AirTimeTopUp(generics.GenericAPIView):
    """
    Handles POST requests for airtime purchase for service providers in Nigeria.
    """

    serializer_class = AirtimeTopupSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticatedOrGuestWithValidId]

    # Private Helper: Success
    def _handle_airtime_success(
        self,
        user=None,
        guest_id=None,
        phone=None,
        amount=None,
        network=None,
        tx_reference=None,
        cashback=None,
    ):
        """Handle successful airtime purchase."""
        response_data = {
            "status": "success",
            "message": f"Airtime purchase of {amount} was successful.",
            "bonus balance": getattr(user, "welcome_bonus", 0),
        }

        logger.info(
            f"User {user.first_name if user else 'Guest'} {user.last_name if user else ''} "
            f"successfully purchased airtime of {amount} for {phone}."
        )

        title = "Airtime purchase"
        message = f"This is to inform you that you have made a purchase of {amount} naira airtime on {phone}."
        description = (
            f"{user.first_name if user else 'Guest'} {user.last_name if user else ''} "
            f"has made a purchase of {amount} naira airtime on {phone}."
        )

        if user:
            create_notification(user=user, title=title, message=message)
            create_activity(user=user, title=title, description=description)
            try:
                with transaction.atomic():
                    # Create a new transaction entry
                    TxModel.objects.create(
                        user=user,
                        tx_reference=tx_reference,
                        tx_type="Airtime",
                        amount=amount,
                        description=title,
                    )

                    CashbackService.reward_cashback(
                        user=user, amount=amount, service="airtime", tx_ref=tx_reference
                    )
            except Exception as e:
                logging.error(f"Database query error: {str(e)}")

            # --- Notification Block (Email/SMS) using Celery task (like transfer) ---
            support_email = "support@picadailys.com"
            alert_type = getattr(user, "alert_type_choice", "Both")
            phone_number = getattr(user, "phone_number", None)
            email = getattr(user, "email", None)

            wallet = getattr(user, "wallet", None)
            account_number = getattr(wallet, "account_number", "") if wallet else ""
            balance = float(getattr(wallet, "balance", 0.0)) if wallet else 0.0
            # Query latest balance from third party if account_number exists
            if account_number:
                enquiry_resp = Wallet.getWalletDetails(account_number)
                if enquiry_resp and hasattr(enquiry_resp, "json"):
                    enquiry_data = enquiry_resp.json()
                    if isinstance(enquiry_data, dict):
                        bal = enquiry_data.get("data", {}).get("availableBalance")
                        if bal is not None:
                            balance = bal

            sms_msg = generate_transaction_sms(
                transaction_type="AIRTIME",
                account_number=account_number,
                amount=float(amount),
                balance=float(balance) if balance else 0.0,
                description=f"Airtime purchase for {phone}",
                reference=tx_reference,
            )
            sms_msg += f"\nIf you did not authorize this transaction, contact support: {support_email}"

            email_subject = "Airtime Purchase Confirmation"
            email_context = {
                "title": "Airtime Purchase Confirmation",
                "rows": [
                    {"label": "Amount", "value": f"₦{float(amount):,.2f}"},
                    {"label": "Account Number", "value": account_number},
                    {"label": "Phone", "value": phone},
                    {"label": "Network", "value": network},
                    {"label": "Reference", "value": tx_reference},
                    {"label": "Datetime", "value": ""},  # Optionally add timestamp
                    {"label": "Transaction Type", "value": "Airtime"},
                    {"label": "Balance", "value": f"₦{balance:,.2f}"},
                ],
                "support_email": support_email,
                "picadailys_phone": "02012271894 02012271895",
            }

            email_body = render_to_string("picadailys_email.html", email_context)
            send_transfer_notifications.delay(
                user.id,
                phone_number[1:] if phone_number else None,
                email,
                alert_type,
                sms_msg,
                email_subject,
                email_body,
                email_body,  # html_content
            )
        else:
            create_activity(guest_id=guest_id, title=title, description=description)

        if user and user.has_done_survey:
            # Calculate points for service purchase activity
            logger.info(
                "Calculating points for user %s service purchase activity.",
                user.phone_number,
            )
            points = Points.determine(
                activity_type="service_purchase", level=user.level
            )
            NextBee.member_activity(
                member_email=user.email, activityId="8474", numericValue=str(points)
            )
            Points.refresh_user_points(user)

        # (Notification is now handled above via send_transfer_notifications)
        return Response(data=encrypt(response_data), status=status.HTTP_200_OK)

    # Private Helper: Failure
    def _handle_airtime_failure(
        self,
        user=None,
        guest_id=None,
        phone=None,
        amount=None,
        airtime_response=None,
        reason="",
    ):
        """Handle failed airtime purchase."""
        title = "Failed airtime purchase"
        message = f"Airtime purchase of {amount} on {phone} failed."
        description = (
            f"{user.first_name if user else 'Guest'} {user.last_name if user else ''} "
            f"failed to purchase airtime of {amount} on {phone}. {reason}"
        )

        if user:
            create_notification(user=user, title=title, message=message)
            create_activity(user=user, title=title, description=description)
        elif guest_id:
            create_activity(guest_id=guest_id, title=title, description=description)

        logger.warning(description)
        # Log the actual response and payload if available
        if hasattr(airtime_response, "request") and hasattr(airtime_response, "text"):
            try:
                logger.warning(
                    f"Airtime failure request payload: {airtime_response.request.body}"
                )
            except Exception:
                logger.warning("Airtime failure: Could not log request payload.")
            logger.warning(
                f"Airtime failure response status: {airtime_response.status_code}"
            )
            logger.warning(f"Airtime failure response body: {airtime_response.text}")
        elif airtime_response is not None:
            logger.warning(f"Airtime failure response: {airtime_response}")
        else:
            logger.warning("Airtime failure: No response body from provider.")

        response_data = {
            "status": "fail",
            "message": f"Airtime purchase failed. {reason}",
            "error": (
                airtime_response.json()
                if hasattr(airtime_response, "json")
                else str(airtime_response) if airtime_response else {}
            ),
        }

        return Response(data=encrypt(response_data), status=status.HTTP_400_BAD_REQUEST)

    # Main POST Method
    def post(self, request):
        decrypted_payload = decrypt(request.data)
        user_data = {
            k: v.strip() if isinstance(v, str) else v
            for k, v in decrypted_payload.items()
        }

        user = request.user if request.user.is_authenticated else None
        guest_id = request.headers.get("X-Guest-ID")
        idempotency_key = request.headers.get("Idempotency-Key")

        # Idempotency: check if this request was already processed
        if user and idempotency_key:
            existing_tx = TxModel.objects.filter(
                user=user, tx_reference=idempotency_key
            ).first()
            if existing_tx:
                logger.info(
                    f"Idempotent request detected for {user.id} with key {idempotency_key}"
                )
                response_data = {
                    "status": "success",
                    "message": "This request was already processed.",
                    "tx_reference": idempotency_key,
                }
                return Response(data=encrypt(response_data), status=status.HTTP_200_OK)

        tx_reference = (
            idempotency_key if idempotency_key else VAS.generate_unique_code("PICA")
        )
        vas_token = VAS.authenticate()
        logger.info(f"VAS.authenticate() returned token: {vas_token}")
        if not vas_token:
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "VAS service is temporarily unavailable.",
                    }
                ),
                status=status.HTTP_502_BAD_GATEWAY,
            )

        # Extract fields
        pin = user_data.get("pin")
        payment_option = user_data.get("payment_option")
        use_bonus = user_data.get("use_bonus")
        use_points = user_data.get("use_points")
        phone = user_data.get("phone_number")
        amount = user_data.get("amount")
        network = user_data.get("network")
        biometrics = user_data.get("use_biometrics")
        use_cashback = user_data.get("use_cashback")

        # Guest validations
        if not user:
            if not guest_id:
                return Response(
                    data=encrypt({"status": "fail", "message": "Guest ID required"}),
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if payment_option != "CARD":
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "message": "Guests can only use card payments",
                        }
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Required field validations
        if not phone or not network:
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "phone_number and network are required.",
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate payload
        serializer = self.serializer_class(data=user_data)
        serializer.is_valid(raise_exception=True)

        # Payment Authentication
        is_verified, error_response = verify_wallet_auth(
            user=user,
            payment_option=payment_option,
            pin=pin,
            use_biometrics=biometrics,
        )

        if not is_verified:
            return error_response

        # --- Start Transactional logic ---
        try:
            with transaction.atomic():
                # Step 1: Debit user (wallet/card/points/cashback) into central collection account
                user_wallet = None
                if user and payment_option == "WALLET":
                    user_wallet = WalletModel.objects.select_for_update().get(user=user)
                elif user:
                    user_wallet = WalletModel.objects.filter(user=user).first()

                cashback_used = 0
                if use_cashback:
                    payment = CashbackService.apply_cashback_payment(
                        user=user, amount=amount
                    )
                    amount = payment["wallet_amount"]
                    cashback_used = payment["cashback_used"]

                # Points/bonus logic (deduct internally, not from wallet)
                pts_amt = 0
                if use_points:
                    _, pts_amt = Pay.with_pts(user=user, amount=int(amount))
                if use_points and pts_amt >= int(amount):
                    wallet_debit_amount = 0
                elif use_points and pts_amt < int(amount):
                    wallet_debit_amount = int(amount) - pts_amt
                else:
                    wallet_debit_amount = int(amount)

                # Payment orchestration using match/case
                match payment_option:
                    case "WALLET":
                        # Wallet-only: if no points/cashback/bonus, debit user directly in VAS call
                        if not use_points and not use_cashback and not use_bonus:
                            airtime_response = VAS.airtime_topup(
                                network=network,
                                bearer_token=vas_token,
                                amount=amount,
                                debitAccount=user_wallet.account_number,
                                phone_number=phone,
                                tx_ref=tx_reference,
                            )
                            logger.info(
                                f"VAS.airtime_topup() response: {airtime_response}"
                            )
                            if airtime_response is None:
                                return self._handle_airtime_failure(
                                    user=user,
                                    phone=phone,
                                    amount=amount,
                                    reason="VAS service unavailable.",
                                )
                            # Check if airtime_response is successful
                            airtime_success = False
                            try:
                                if hasattr(airtime_response, "status_code") and (
                                    str(airtime_response.status_code) == "200"
                                    or airtime_response.status_code == 200
                                ):
                                    airtime_json = (
                                        airtime_response.json()
                                        if hasattr(airtime_response, "json")
                                        else {}
                                    )
                                    airtime_data = (
                                        airtime_json.get("data", {})
                                        if isinstance(airtime_json, dict)
                                        else {}
                                    )
                                    if (
                                        airtime_data.get("status") == "success"
                                        or airtime_json.get("status") == "success"
                                    ):
                                        airtime_success = True
                            except Exception as e:
                                logger.warning(f"Error parsing airtime_response: {e}")

                            status_query = VAS.status(
                                bearer_token=vas_token, tx_ref=tx_reference
                            )
                            logger.info(f"VAS.status() response: {status_query}")
                            status_resp = (
                                status_query.json().get("data", {})
                                if status_query
                                else {}
                            )
                            status_success = status_resp.get("status") == "success" or (
                                status_resp.get("responseCode") == "200"
                                or status_resp.get("responseCode") == 200
                            )

                            if airtime_success or status_success:
                                return self._handle_airtime_success(
                                    user=user,
                                    phone=phone,
                                    amount=amount,
                                    network=network,
                                    tx_reference=tx_reference,
                                    cashback=cashback_used,
                                )
                            else:
                                return self._handle_airtime_failure(
                                    user=user,
                                    phone=phone,
                                    amount=amount,
                                    airtime_response=airtime_response,
                                    reason="Airtime top-up failed.",
                                )
                        # Hybrid: points/cashback/bonus + wallet, collect wallet portion to central, call VAS with central
                        # Only perform local debit in hybrid cases
                        if (
                            use_points or use_cashback or use_bonus
                        ) and wallet_debit_amount > 0:
                            debit_response = Wallet.Debit(
                                debitAccount=user_wallet.account_number,
                                amount=wallet_debit_amount,
                                reason="Debit for airtime recharge (to central collection)",
                                merchantFeeAmount="",
                                destinationAccount=settings.CENTRAL_COLLECTION_ACCOUNT,
                            )
                            if (
                                debit_response is None
                                or str(debit_response.status_code) != "200"
                            ):
                                return self._handle_airtime_failure(
                                    user=user,
                                    phone=phone,
                                    amount=amount,
                                    reason="Wallet service unavailable or debit failed.",
                                )
                        vas_debit_account = settings.CENTRAL_OPERATIONAL_ACCOUNT
                        airtime_response = VAS.airtime_topup(
                            network=network,
                            bearer_token=vas_token,
                            amount=amount,
                            debitAccount=vas_debit_account,
                            phone_number=phone,
                            tx_ref=tx_reference,
                        )
                        if airtime_response is None:
                            # Refund only if hybrid (points/cashback/bonus + wallet)
                            if wallet_debit_amount > 0 and (
                                use_points or use_cashback or use_bonus
                            ):
                                Wallet.Credit(
                                    acct_no=user_wallet.account_number,
                                    amount=wallet_debit_amount,
                                    reason="Refund after failed VAS purchase",
                                    sourceAccount=settings.CENTRAL_OPERATIONAL_ACCOUNT,
                                )
                            return self._handle_airtime_failure(
                                user=user,
                                phone=phone,
                                amount=amount,
                                reason="VAS service unavailable.",
                            )
                        status_query = VAS.status(
                            bearer_token=vas_token, tx_ref=tx_reference
                        )
                        status_resp = (
                            status_query.json().get("data", {}) if status_query else {}
                        )
                        logger.info(f"VAS.status() response: {status_resp}")
                        if (
                            status_resp.get("status") == "success"
                            and status_resp.get("responseCode") == "200"
                        ):
                            return self._handle_airtime_success(
                                user=user,
                                phone=phone,
                                amount=amount,
                                network=network,
                                tx_reference=tx_reference,
                                cashback=cashback_used,
                            )
                        else:
                            # Refund only if hybrid (points/cashback/bonus + wallet)
                            if wallet_debit_amount > 0 and (
                                use_points or use_cashback or use_bonus
                            ):
                                Wallet.Credit(
                                    acct_no=user_wallet.account_number,
                                    amount=wallet_debit_amount,
                                    reason="Refund after failed VAS purchase",
                                    sourceAccount=settings.CENTRAL_OPERATIONAL_ACCOUNT,
                                )
                            return self._handle_airtime_failure(
                                user=user,
                                phone=phone,
                                amount=amount,
                                airtime_response=airtime_response,
                                reason="Airtime top-up failed.",
                            )
                    case "CARD":
                        # Card payment: collect from card to central, call VAS with central debit account
                        # (Assume card payment is already processed and amount is in central collection)
                        vas_debit_account = settings.CENTRAL_OPERATIONAL_ACCOUNT
                        airtime_response = VAS.airtime_topup(
                            network=network,
                            bearer_token=vas_token,
                            amount=amount,
                            debitAccount=vas_debit_account,
                            phone_number=phone,
                            tx_ref=tx_reference,
                        )
                        if airtime_response is None:
                            return self._handle_airtime_failure(
                                user=user,
                                guest_id=guest_id,
                                phone=phone,
                                amount=amount,
                                reason="VAS service unavailable.",
                            )
                        status_query = VAS.status(
                            bearer_token=vas_token, tx_ref=tx_reference
                        )
                        status_resp = (
                            status_query.json().get("data", {}) if status_query else {}
                        )
                        if (
                            status_resp.get("status") == "success"
                            and status_resp.get("responseCode") == "200"
                        ):
                            return self._handle_airtime_success(
                                user=user,
                                guest_id=guest_id,
                                phone=phone,
                                amount=amount,
                                network=network,
                                tx_reference=tx_reference,
                                cashback=cashback_used,
                            )
                        else:
                            return self._handle_airtime_failure(
                                user=user,
                                guest_id=guest_id,
                                phone=phone,
                                amount=amount,
                                airtime_response=airtime_response,
                                reason="Airtime top-up failed.",
                            )
                    case _:
                        return Response(
                            data=encrypt(
                                {"status": "fail", "message": "Invalid payment option"}
                            ),
                            status=status.HTTP_400_BAD_REQUEST,
                        )
        except WalletModel.DoesNotExist:
            return Response(
                data=encrypt({"status": "fail", "message": "Wallet not found"}),
                status=404,
            )
        except Exception as e:
            logger.exception(f"Transaction error during airtime purchase: {e}")
            return Response(
                data=encrypt({"status": "fail", "message": "Transaction failed"}),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class GetNetworkProvider(generics.RetrieveAPIView):
    serializer_class = VasStatusSerializer

    # Map full service IDs to their corresponding filenames
    SERVICE_MAPPINGS = {
        "MTN": "mtn_grouped_dataplans_by_validity.json",
        "AIRTEL": "airtel_grouped_dataplans_by_validity.json",
        "GLO": "glo_grouped_data_set.json",
        "9MOBILE": "nine_mobile_grouped_dataplans_by_validity.json",
    }

    @extend_schema(
        description="Retrieve variation codes for network providers",
        responses={
            200: OpenApiResponse(description="Successfully retrieved data plans"),
            400: OpenApiResponse(description="Invalid data plans provided"),
            404: OpenApiResponse(description="Data plans file not found"),
            500: OpenApiResponse(description="Server error processing request"),
        },
    )
    def get(self, request, *args, **kwargs):
        # Get the full service ID (e.g. 'mtn-data', 'etisalat-data')
        service_id = kwargs.get("network", "").lower().strip()

        # derive provider token and normalize to mapping keys (MTN, AIRTEL, GLO, 9MOBILE)
        provider = service_id.split("-")[0].upper() if service_id else ""
        filename = self.SERVICE_MAPPINGS.get(provider)

        if not filename:
            return Response(
                data=encrypt(
                    {
                        "status": "error",
                        "message": f"Unsupported service provider: {service_id}",
                        "supported_providers": list(self.SERVICE_MAPPINGS.keys()),
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            json_path = os.path.join(settings.BASE_DIR, "vas", "data_plans", filename)
            logger.debug(f"Checking for file at: {json_path}")

            if not os.path.isfile(json_path):
                return Response(
                    data=encrypt(
                        {
                            "status": "error",
                            "message": f"Network data plans file not found for {service_id}",
                            "expected_filename": filename,
                        }
                    ),
                    status=status.HTTP_404_NOT_FOUND,
                )

            with open(json_path, "r") as f:
                variation_data = json.load(f)

            variation_data = CashbackService.add_cashback_to_bundles(variation_data)

            return Response(
                data=encrypt(
                    {"status": "success", "service": service_id, "data": variation_data}
                ),
                status=status.HTTP_200_OK,
            )

        except json.JSONDecodeError:
            logger.error(f"Invalid JSON format in file: {filename}")
            return Response(
                data=encrypt(
                    {
                        "status": "error",
                        "message": "Invalid data format in data plans file",
                    }
                ),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        except Exception as e:
            logger.error(f"Error loading data plans: {str(e)}")
            return Response(
                data=encrypt(
                    {"status": "error", "message": "Failed to load data plans"}
                ),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class DataSubscriptionView(generics.GenericAPIView):
    """
    DataSubscriptionView is a POST request handler for data
    subscription.
    """

    serializer_class = DataSubscriptionSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticatedOrGuestWithValidId]

    # Private Helper: Success
    def _handle_data_success(
        self,
        user=None,
        guest_id=None,
        phone=None,
        productId=None,
        amount=None,
        network=None,
        tx_reference=None,
        cashback=None,
    ):
        """Handle successful airtime/data purchase."""
        response_data = {
            "status": "success",
            "message": f"Data purchase of {amount} was successful.",
            "bonus balance": getattr(user, "welcome_bonus", 0),
        }

        title = "Data purchase"
        message = f"This is to inform you that you have made a data purchase of {amount} naira data on {phone}."
        description = (
            f"{user.first_name if user else 'Guest'} {user.last_name if user else ''} "
            f"has made a purchase of {amount} naira data on {phone}."
        )

        if user:
            create_notification(user=user, title=title, message=message)
            create_activity(user=user, title=title, description=description)
            try:
                with transaction.atomic():
                    TxModel.objects.create(
                        user=user,
                        tx_reference=tx_reference,
                        tx_type="Data",
                        amount=amount,
                        description=title,
                    )

                    CashbackService.reward_cashback(
                        user=user, amount=amount, service="data", tx_ref=tx_reference
                    )

            except Exception as e:
                logger.error(f"Database query error: {str(e)}")
        else:
            create_activity(guest_id=guest_id, title=title, description=description)

        if user and getattr(user, "has_done_survey", False):
            points = Points.determine(
                activity_type="service_purchase", level=user.level
            )
            NextBee.member_activity(
                member_email=user.email, activityId="8474", numericValue=str(points)
            )
            Points.refresh_user_points(user)

        if cashback is not None:
            response_data["cashback_used"] = str(cashback)
        # --- Notification Block (Email/SMS) using Celery task (like airtime) ---
        if user:
            support_email = "support@picadailys.com"
            alert_type = getattr(user, "alert_type_choice", "Both")
            phone_number = getattr(user, "phone_number", None)
            email = getattr(user, "email", None)
            wallet = getattr(user, "wallet", None)
            account_number = getattr(wallet, "account_number", "") if wallet else ""
            balance = float(getattr(wallet, "balance", 0.0)) if wallet else 0.0
            # Query latest balance from third party if account_number exists
            if account_number:
                from banking.controllers import Wallet as WalletController

                enquiry_resp = WalletController.getWalletDetails(account_number)
                if enquiry_resp and hasattr(enquiry_resp, "json"):
                    enquiry_data = enquiry_resp.json()
                    if isinstance(enquiry_data, dict):
                        bal = enquiry_data.get("data", {}).get("availableBalance")
                        if bal is not None:
                            balance = bal

            sms_msg = generate_transaction_sms(
                transaction_type="DATA",
                account_number=account_number,
                amount=float(amount),
                balance=float(balance) if balance else 0.0,
                description=f"Data purchase for {phone}",
                reference=tx_reference,
            )
            sms_msg += f"\nIf you did not authorize this transaction, contact support: {support_email}"

            email_subject = "Data Purchase Confirmation"
            email_context = {
                "title": "Data Purchase Confirmation",
                "rows": [
                    {"label": "Amount", "value": f"₦{float(amount):,.2f}"},
                    {"label": "Account Number", "value": account_number},
                    {"label": "Phone", "value": phone},
                    {"label": "Network", "value": network},
                    {"label": "Reference", "value": tx_reference},
                    {"label": "Datetime", "value": ""},  # Optionally add timestamp
                    {"label": "Transaction Type", "value": "Data"},
                    {"label": "Balance", "value": f"₦{balance:,.2f}"},
                ],
                "support_email": support_email,
                "picadailys_phone": "02012271894 02012271895",
            }
            email_body = render_to_string("picadailys_email.html", email_context)
            send_transfer_notifications.delay(
                user.id,
                phone_number[1:] if phone_number else None,
                email,
                alert_type,
                sms_msg,
                email_subject,
                email_body,
                email_body,  # html_content
            )
        return Response(data=encrypt(response_data), status=status.HTTP_200_OK)

    # Private Helper: Failure
    def _handle_data_failure(
        self,
        user=None,
        guest_id=None,
        phone=None,
        amount=None,
        data_response=None,
        reason="",
    ):
        """Handle failed data purchase."""
        title = "Failed data purchase"
        message = f"Data purchase of {amount} on {phone} failed."
        description = (
            f"{user.first_name if user else 'Guest'} {user.last_name if user else ''} "
            f"failed to purchase data of {amount} on {phone}. {reason}"
        )

        if user:
            create_notification(user=user, title=title, message=message)
            create_activity(user=user, title=title, description=description)
        elif guest_id:
            create_activity(guest_id=guest_id, title=title, description=description)

        logger.warning(description)
        # Log the actual response from the third party if available
        if hasattr(data_response, "status_code") and hasattr(data_response, "text"):
            logger.warning(f"Third-party response status: {data_response.status_code}")
            logger.warning(f"Third-party response body: {data_response.text}")
        elif data_response is not None:
            logger.warning(f"Data failure response: {data_response}")
        else:
            logger.warning("Data failure: No response body from provider.")

        # Ensure error is always JSON serializable
        if data_response is not None:
            if hasattr(data_response, "data"):
                error_detail = data_response.data
            elif hasattr(data_response, "text"):
                error_detail = data_response.text
            else:
                error_detail = str(data_response)
        else:
            error_detail = {}

        response_data = {
            "status": "fail",
            "message": f"Data purchase failed. {reason}",
            "error": error_detail,
        }

        return Response(data=encrypt(response_data), status=status.HTTP_400_BAD_REQUEST)

        # Main POST Method

    def post(self, request):
        decrypted_payload = decrypt(request.data)
        user_data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_payload.items()
        }

        user = request.user if request.user.is_authenticated else None
        guest_id = request.headers.get("X-Guest-ID")
        idempotency_key = request.headers.get("Idempotency-Key")

        # Idempotency: check if this request was already processed
        if user and idempotency_key:
            existing_tx = TxModel.objects.filter(
                user=user, tx_reference=idempotency_key
            ).first()
            if existing_tx:
                logger.info(
                    f"Idempotent request detected for {user.id} with key {idempotency_key}"
                )
                response_data = {
                    "status": "success",
                    "message": "This request was already processed.",
                    "tx_reference": idempotency_key,
                }
                return Response(data=encrypt(response_data), status=status.HTTP_200_OK)

        pin = user_data.get("pin")
        use_bonus = user_data.get("use_bonus")
        amount = user_data.get("amount")
        phone = user_data.get("phone_number")
        use_points = user_data.get("use_points")
        payment_option = user_data.get("payment_option")
        network = user_data.get("network")
        product_id = user_data.get("product_id")
        biometrics = user_data.get("use_biometrics")
        use_cashback = user_data.get("use_cashback")

        cashback_used = Decimal("0")

        if user:
            try:
                with transaction.atomic():
                    user_wallet = WalletModel.objects.select_for_update().get(user=user)
            except WalletModel.DoesNotExist:
                user_wallet = None
        else:
            user_wallet = None

        tx_reference = (
            idempotency_key if idempotency_key else VAS.generate_unique_code("PICA")
        )
        vas_token = VAS.authenticate()
        if not vas_token:
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "VAS service is temporarily unavailable.",
                    }
                ),
                status=status.HTTP_502_BAD_GATEWAY,
            )

        # Apply cashback for payment
        if use_cashback:
            payment = CashbackService.apply_cashback_payment(user=user, amount=amount)
            amount = payment["wallet_amount"]
            cashback_used = payment["cashback_used"]

        # Guest validations
        if not user:
            if not guest_id:
                return Response(
                    data=encrypt({"status": "fail", "message": "Guest ID required"}),
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if payment_option != "CARD":
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "message": "Guests can only use card payments",
                        }
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )

        serializer = self.serializer_class(data=user_data)
        serializer.is_valid(raise_exception=True)

        if payment_option != "CARD":
            try:
                account = WalletModel.objects.get(user=user)
            except WalletModel.DoesNotExist:
                return Response(
                    data=encrypt(
                        {"status": "fail", "error": "Account not found for user"}
                    ),
                    status=status.HTTP_404_NOT_FOUND,
                )

        verification = True
        if payment_option == "WALLET":
            if biometrics:
                verification = Biometrics.authenticate(user.phone_number)
            elif account and account.pin is not None:
                verification = Pin.verify(user=user, pin=pin, hashed_pin=account.pin)
            else:
                return Response(
                    data=encrypt(
                        {"status": "fail", "error": "Account or PIN not found"}
                    ),
                    status=status.HTTP_404_NOT_FOUND,
                )

        if not verification:
            return Response(
                data=encrypt({"status": "fail", "error": "Invalid credentials"}),
                status=status.HTTP_401_UNAUTHORIZED,
            )

        data_response = None

        # Use bonus flow
        if use_bonus:
            if user and user.welcome_bonus >= float(amount):
                data_response = VAS.data(
                    network=network,
                    bearer_token=vas_token,
                    amount=amount,
                    debitAccount=user_wallet.account_number,
                    phone_number=phone,
                    productId=product_id,
                    tx_ref=tx_reference,
                )
                if data_response is None:
                    return self._handle_data_failure(
                        user=user,
                        phone=phone,
                        amount=amount,
                        reason="VAS service unavailable.",
                    )
                status_resp = VAS.status(bearer_token=vas_token, tx_ref=tx_reference)
                if status_resp is None:
                    return self._handle_data_failure(
                        user=user,
                        phone=phone,
                        amount=amount,
                        reason="Could not verify transaction status.",
                    )
                status_data = status_resp.json().get("data", {})
                if status_data.get("status") == "success" and (
                    status_data.get("responseCode") == "200"
                    or status_data.get("responseCode") == 200
                ):
                    return self._handle_data_success(
                        user=user,
                        guest_id=guest_id,
                        phone=phone,
                        amount=amount,
                        network=network,
                        tx_reference=tx_reference,
                        cashback=cashback_used,
                    )
                else:
                    return self._handle_data_failure(
                        user=user,
                        phone=phone,
                        amount=amount,
                        data_response=data_response.json() if data_response else None,
                        reason="Insufficient bonus balance.",
                    )
            else:
                return self._handle_data_failure(
                    user=user,
                    phone=phone,
                    amount=amount,
                    data_response=data_response.json() if data_response else None,
                    reason="Insufficient bonus balance.",
                )

        pts_amt = 0
        if use_points:
            _, pts_amt = Pay.with_pts(user=user, amount=int(amount))
        if use_points and pts_amt >= int(amount):
            wallet_debit_amount = 0
        elif use_points and pts_amt < int(amount):
            wallet_debit_amount = int(amount) - pts_amt
        else:
            wallet_debit_amount = int(amount)

        match payment_option:
            case "WALLET":
                if not use_points and not use_cashback and not use_bonus:
                    # Wallet-only: debit user wallet directly
                    data_response = VAS.data(
                        network=network,
                        bearer_token=vas_token,
                        amount=amount,
                        productId=product_id,
                        debitAccount=user_wallet.account_number,
                        phone_number=phone,
                        tx_ref=tx_reference,
                    )
                    if data_response is None:
                        return self._handle_data_failure(
                            user=user,
                            phone=phone,
                            amount=amount,
                            reason="VAS service unavailable.",
                        )
                    # Check if data_response is successful
                    data_success = False
                    try:
                        if hasattr(data_response, "status_code") and (
                            str(data_response.status_code) == "200"
                            or data_response.status_code == 200
                        ):
                            data_json = (
                                data_response.json()
                                if hasattr(data_response, "json")
                                else {}
                            )
                            data_data = (
                                data_json.get("data", {})
                                if isinstance(data_json, dict)
                                else {}
                            )
                            if (
                                data_data.get("status") == "success"
                                or data_json.get("status") == "success"
                            ):
                                data_success = True
                    except Exception as e:
                        logger.warning(f"Error parsing data_response: {e}")

                    status_query = VAS.status(
                        bearer_token=vas_token, tx_ref=tx_reference
                    )
                    status_resp = (
                        status_query.json().get("data", {}) if status_query else {}
                    )
                    status_success = status_resp.get("status") == "success" or (
                        status_resp.get("responseCode") == "200"
                        or status_resp.get("responseCode") == 200
                    )

                    if data_success or status_success:
                        return self._handle_data_success(
                            user=user,
                            phone=phone,
                            productId=product_id,
                            amount=amount,
                            network=network,
                            tx_reference=tx_reference,
                            cashback=cashback_used,
                        )
                    else:
                        return self._handle_data_failure(
                            user=user,
                            phone=phone,
                            amount=amount,
                            data_response=data_response,
                            reason="Data subscription failed.",
                        )
                # Hybrid: points/cashback/bonus + wallet, collect wallet portion to central, call VAS with central
                # Only perform local debit in hybrid cases
                if (
                    use_points or use_cashback or use_bonus
                ) and wallet_debit_amount > 0:
                    debit_response = Wallet.Debit(
                        debitAccount=user_wallet.account_number,
                        amount=wallet_debit_amount,
                        reason="Debit for data subscription (to central collection)",
                        merchantFeeAmount="",
                        destinationAccount=settings.CENTRAL_COLLECTION_ACCOUNT,
                    )
                    if (
                        debit_response is None
                        or str(debit_response.status_code) != "200"
                    ):
                        return self._handle_data_failure(
                            user=user,
                            phone=phone,
                            amount=amount,
                            reason="Wallet service unavailable or debit failed.",
                        )
                vas_debit_account = settings.CENTRAL_OPERATIONAL_ACCOUNT
                data_response = VAS.data(
                    network=network,
                    bearer_token=vas_token,
                    amount=amount,
                    productId=product_id,
                    debitAccount=vas_debit_account,
                    phone_number=phone,
                    tx_ref=tx_reference,
                )
                if data_response is None:
                    # Refund only if hybrid (points/cashback/bonus + wallet)
                    if wallet_debit_amount > 0 and (
                        use_points or use_cashback or use_bonus
                    ):
                        Wallet.Credit(
                            acct_no=user_wallet.account_number,
                            amount=wallet_debit_amount,
                            reason="Refund after failed VAS data purchase",
                            sourceAccount=settings.CENTRAL_OPERATIONAL_ACCOUNT,
                        )
                    return self._handle_data_failure(
                        user=user,
                        phone=phone,
                        amount=amount,
                        reason="VAS service unavailable.",
                    )
                status_query = VAS.status(bearer_token=vas_token, tx_ref=tx_reference)
                status_resp = (
                    status_query.json().get("data", {}) if status_query else {}
                )
                if status_resp.get("transactionStatus") == "success" and (
                    status_resp.get("responseCode") == "200"
                    or status_resp.get("responseCode") == 200
                ):
                    return self._handle_data_success(
                        user=user,
                        phone=phone,
                        productId=product_id,
                        amount=amount,
                        network=network,
                        tx_reference=tx_reference,
                        cashback=cashback_used,
                    )
                else:
                    # Refund only if hybrid (points/cashback/bonus + wallet)
                    if wallet_debit_amount > 0 and (
                        use_points or use_cashback or use_bonus
                    ):
                        Wallet.Credit(
                            acct_no=user_wallet.account_number,
                            amount=wallet_debit_amount,
                            reason="Refund after failed VAS data purchase",
                            sourceAccount=settings.CENTRAL_OPERATIONAL_ACCOUNT,
                        )
                    return self._handle_data_failure(
                        user=user,
                        phone=phone,
                        amount=amount,
                        data_response=data_response,
                        reason="Data subscription failed.",
                    )
            case "CARD":
                vas_debit_account = settings.CENTRAL_OPERATIONAL_ACCOUNT
                data_response = VAS.data(
                    network=network,
                    bearer_token=vas_token,
                    amount=amount,
                    productId=product_id,
                    debitAccount=vas_debit_account,
                    phone_number=phone,
                    tx_ref=tx_reference,
                )
                if data_response is None:
                    return self._handle_data_failure(
                        user=user,
                        guest_id=guest_id,
                        phone=phone,
                        amount=amount,
                        reason="VAS service unavailable.",
                    )
                status_query = VAS.status(bearer_token=vas_token, tx_ref=tx_reference)
                status_resp = (
                    status_query.json().get("data", {}) if status_query else {}
                )
                if status_resp.get("status") == "success" and (
                    status_resp.get("responseCode") == "200"
                    or status_resp.get("responseCode") == 200
                ):
                    return self._handle_data_success(
                        user=user,
                        guest_id=guest_id,
                        phone=phone,
                        productId=product_id,
                        amount=amount,
                        network=network,
                        tx_reference=tx_reference,
                    )
                else:
                    return self._handle_data_failure(
                        user=user,
                        guest_id=guest_id,
                        phone=phone,
                        amount=amount,
                        data_response=data_response,
                        reason="Data subscription failed.",
                    )
            case _:
                return Response(
                    data=encrypt(
                        {"status": "fail", "message": "Invalid payment option"}
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )


class BillPaymentCategoriesView(APIView):
    """
    BillPaymentCategoriesView is the GET request handler that returns a list of
    bill payment categories.
    """

    def get(self, request, *args, **kwargs):
        token = VAS.authenticate()
        if not token:
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "VAS service is temporarily unavailable.",
                    }
                ),
                status=status.HTTP_502_BAD_GATEWAY,
            )
        categories_resp = VAS.bill_payment_categories(
            bearer_token=token, category_id=kwargs.get("category_id")
        )
        categories = categories_resp.json().get("data", [])

        return Response(
            data=encrypt(
                {
                    "status": "success.",
                    "message": "Bill payment categories retrieved successfully.",
                    "categories": categories,
                }
            ),
            status=status.HTTP_200_OK,
        )


class BillersCategoriesView(APIView):
    """
    BillersCategoriesView is the GET request handler that returns a list of
    billers categories.
    """

    def get(self, request, *args, **kwargs):
        token = VAS.authenticate()
        if not token:
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "VAS service is temporarily unavailable.",
                    }
                ),
                status=status.HTTP_502_BAD_GATEWAY,
            )
        billers_resp = VAS.billers_categories(
            bearer_token=token, biller_id=kwargs.get("billers_id")
        )
        billers = billers_resp.json().get("data", [])

        return Response(
            data=encrypt(
                {
                    "status": "success.",
                    "message": "Billers categories retrieved successfully.",
                    "categories": billers,
                }
            ),
            status=status.HTTP_200_OK,
        )


class VerifyBillerAccountView(generics.GenericAPIView):
    """
    VerifyBillerAccountView is a POST request handler for verifying
    biller account number.
    """

    serializer_class = VerifyBillerSerializer

    @extend_schema(
        description="Biller account",
        responses={200: {"description": "Verify biller account"}},
    )
    def post(self, request):
        decrypted_payload = decrypt(request.data)
        user_data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_payload.items()
        }

        logger.info(
            f"User {request.user.first_name} {request.user.last_name} is attempting to verify biller account number with data: {user_data}"
        )

        try:
            token = VAS.authenticate()
            if not token:
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "message": "VAS service is temporarily unavailable.",
                        }
                    ),
                    status=status.HTTP_502_BAD_GATEWAY,
                )
            verify_biller = VAS.verify_bill_payer(
                bearer_token=token,
                billerId=user_data.get("billerId"),
                customerId=user_data.get("customerId"),
                itemId=user_data.get("itemId"),
                amount=user_data.get("amount"),
            )

            biller_response = verify_biller.json()
            logger.info(f"Biller verification response: {biller_response}")

            if (
                biller_response.get("status") == "success"
                and biller_response.get("responseCode") == 200
            ):
                response_data = {
                    "data": biller_response,
                }
                logger.info(
                    f"Biller account verification successful for user {request.user.first_name} {request.user.last_name}: {response_data}"
                )
                return Response(data=encrypt(response_data), status=status.HTTP_200_OK)
            else:
                logger.warning(
                    f"Biller account verification failed for user {request.user.first_name} {request.user.last_name}: {biller_response}"
                )
                return Response(
                    data=encrypt(biller_response),
                    status=biller_response.get("responseCode"),
                )

        except requests.exceptions.RequestException as e:
            logger.error(
                f"RequestException occurred for user {request.user.first_name} {request.user.last_name}: {str(e)}"
            )
            return Response(
                data=encrypt({"error": str(e)}),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class BillPaymentView(generics.GenericAPIView):
    """
    Unified BillPaymentView for both Electricity and Cable subscriptions.
    Service type is detected from VAS response: if VAS response data includes
    a 'token' field, the service is Electricity (token returned). Otherwise it's Cable.
    """

    serializer_class = BillPaymentSerializer  # same serializer for both services
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticatedOrGuestWithValidId]

    # --- helpers (reuse your existing handlers) ---
    def _handle_success(
        self,
        user=None,
        guest_id=None,
        customerId=None,
        billerId=None,
        itemId=None,
        amount=None,
        phone_number=None,
        customerName=None,
        otherField=None,
        vas_response=None,
        tx_reference=None,
    ):
        """
        Central success handler for both Electricity (token) and Cable.
        vas_response is the requests.Response object returned from VAS.* call.
        """
        # Pull VAS response data safely
        vas_json = {}
        try:
            vas_json = (
                vas_response.json()
                if hasattr(vas_response, "json")
                else vas_response or {}
            )
        except Exception:
            vas_json = vas_response or {}

        vas_data = vas_json.get("data", {}) if isinstance(vas_json, dict) else {}

        # Determine if electricity by presence of token
        token = vas_data.get("token")
        is_electricity = bool(token)

        response_data = {
            "status": "success",
            "message": f"Purchase of {amount} was successful.",
            "bonus balance": getattr(user, "welcome_bonus", 0),
        }

        # If electricity include token details
        if is_electricity:
            response_data["token_details"] = vas_data.get("token", {})
            response_data["units_bought"] = vas_data.get("otherField", "")

        # Add raw vas_data for tracing (optional)
        response_data["service_response"] = vas_data

        title = "Bill Payment"
        message = (
            f"This is to inform you that you have made a payment of {amount} naira."
        )
        description = (
            f"{user.first_name if user else 'Guest'} {user.last_name if user else ''} "
            f"has made a payment of {amount} naira."
        )

        if user:
            create_notification(user=user, title=title, message=message)
            create_activity(user=user, title=title, description=description)
            try:
                with transaction.atomic():
                    TxModel.objects.create(
                        user=user,
                        tx_reference=tx_reference,
                        tx_type="Bill Payment",
                        amount=amount,
                        description=title,
                    )

                    ValueAddedServices.objects.create(
                        user=user if user else None,
                        guest_id=guest_id if not user else None,
                        customerId=customerId,
                        billerId=billerId,
                        itemId=itemId,
                        amount=amount,
                        phone_number=phone_number,
                        customerName=customerName,
                        otherField=otherField,
                        tx_reference=tx_reference,
                    )
            except Exception as e:
                logger.error(f"Database query error: {str(e)}")
        else:
            create_activity(guest_id=guest_id, title=title, description=description)

        # Award points if applicable (registered users)
        if user and getattr(user, "has_done_survey", False):
            points = Points.determine(
                activity_type="service_purchase", level=user.level
            )
            NextBee.member_activity(
                member_email=user.email, activityId="8474", numericValue=str(points)
            )
            Points.refresh_user_points(user)

        # --- SMS Notification for Success ---
        if (
            user
            and hasattr(user, "phone_number")
            and getattr(user, "alert_type_choice", None) in ("SMS", "Both")
        ):
            wallet = getattr(user, "wallet", None)
            account_number = getattr(wallet, "account_number", "") if wallet else ""
            balance = getattr(wallet, "balance", "") if wallet else ""
            # Use wallet enquiry to get latest balance
            if account_number:
                enquiry_resp = Wallet.getWalletDetails(account_number)
                if enquiry_resp and hasattr(enquiry_resp, "json"):
                    enquiry_data = enquiry_resp.json()
                    if isinstance(enquiry_data, dict):
                        bal = enquiry_data.get("data", {}).get("availableBalance")
                        if bal is not None:
                            balance = bal
            sms_msg = generate_transaction_sms(
                transaction_type="BILL",
                account_number=account_number,
                amount=float(amount),
                balance=float(balance) if balance else 0.0,
                description=f"Bill payment for {phone_number or customerName or customerId}",
                reference=tx_reference,
            )
            Messaging.send_sms(
                phone_number=user.phone_number[1:],
                msg=sms_msg,
            )
        return Response(data=encrypt(response_data), status=status.HTTP_200_OK)

    def _handle_failure(
        self,
        user=None,
        guest_id=None,
        phone_number=None,
        amount=None,
        vas_response=None,
        reason="",
    ):
        """Central failure handler for both Electricity and Cable payment failures."""
        # Attempt to parse vas_response for debugging
        vas_json = None
        try:
            vas_json = (
                vas_response.json() if hasattr(vas_response, "json") else vas_response
            )
        except Exception:
            vas_json = vas_response

        title = "Failed Bill Payment"
        message = f"Bill payment of {amount} on {phone_number} failed."
        description = (
            f"{user.first_name if user else 'Guest'} {user.last_name if user else ''} "
            f"failed to make a payment of {amount} for {reason}"
        )

        if user:
            create_notification(user=user, title=title, message=message)
            create_activity(user=user, title=title, description=description)
        elif guest_id:
            create_activity(guest_id=guest_id, title=title, description=description)

        logger.warning(description)

        response_data = {
            "status": "fail",
            "message": f"Bill payment failed. {reason}",
            "error": vas_json or {},
        }

        return Response(data=encrypt(response_data), status=status.HTTP_400_BAD_REQUEST)

    # --- POST flow (mirrors DataSubscription flow) ---
    def post(self, request):
        guest_id = request.headers.get("X-Guest-ID")
        idempotency_key = request.headers.get("Idempotency-Key")
        decrypted_payload = decrypt(request.data)
        user_data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_payload.items()
        }
        user = request.user if request.user.is_authenticated else None

        # Idempotency: check if this request was already processed
        if user and idempotency_key:
            existing_tx = TxModel.objects.filter(
                user=user, tx_reference=idempotency_key
            ).first()
            if existing_tx:
                logger.info(
                    f"Idempotent request detected for {user.id} with key {idempotency_key}"
                )
                response_data = {
                    "status": "success",
                    "message": "This request was already processed.",
                    "tx_reference": idempotency_key,
                }
                return Response(data=encrypt(response_data), status=status.HTTP_200_OK)

        # Extract fields
        pin = user_data.get("pin")
        use_bonus = user_data.get("use_bonus")
        amount = user_data.get("amount")
        use_points = user_data.get("use_points")
        payment_option = user_data.get("payment_option")
        customerId = user_data.get("customerId")
        billerId = user_data.get("billerId")
        phone_number = user_data.get("phone_number")
        customerName = user_data.get("customerName")
        itemId = user_data.get("itemId")
        otherField = user_data.get("otherField")
        biometrics = user_data.get("use_biometrics")
        use_cashback = user_data.get("use_cashback")

        # Generate transaction reference and authenticate VAS
        tx_reference = (
            idempotency_key if idempotency_key else VAS.generate_unique_code("PICA")
        )
        vas_token = VAS.authenticate()
        if not vas_token:
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "VAS service is temporarily unavailable.",
                    }
                ),
                status=status.HTTP_502_BAD_GATEWAY,
            )

        # Lock wallet for authenticated users
        if user:
            try:
                user_wallet = WalletModel.objects.select_for_update().get(user=user)
            except WalletModel.DoesNotExist:
                user_wallet = None
        else:
            user_wallet = None

        # Guest validations (guests only allowed CARD)
        if not user:
            if not guest_id:
                return Response(
                    data=encrypt({"status": "fail", "message": "Guest ID required"}),
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if payment_option != "CARD":
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "message": "Guests can only use card payments",
                        }
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Validate payload with serializer
        serializer = self.serializer_class(data=user_data)
        serializer.is_valid(raise_exception=True)

        # If wallet flows will be used, ensure we can get the account
        if payment_option != "CARD":
            try:
                account = WalletModel.objects.get(user=user)
            except WalletModel.DoesNotExist:
                return Response(
                    data=encrypt(
                        {"status": "fail", "error": "Account not found for user"}
                    ),
                    status=status.HTTP_404_NOT_FOUND,
                )

        # Authentication / verification step (PIN or biometrics) for WALLET option
        verification = True
        if payment_option == "WALLET":
            if biometrics:
                verification = Biometrics.authenticate(user.phone_number)
            elif account and account.pin is not None:
                verification = Pin.verify(user=user, pin=pin, hashed_pin=account.pin)
            else:
                return Response(
                    data=encrypt(
                        {"status": "fail", "error": "Account or PIN not found"}
                    ),
                    status=status.HTTP_404_NOT_FOUND,
                )

        if not verification:
            return Response(
                data=encrypt({"status": "fail", "error": "Invalid credentials"}),
                status=status.HTTP_401_UNAUTHORIZED,
            )

        vas_response = None

        # --- Use bonus flow (only for authenticated users) ---
        if use_bonus:
            if user and user.welcome_bonus >= float(amount):
                try:
                    vas_response = VAS.bill_payment(
                        bearer_token=vas_token,
                        customerId=customerId,
                        billerId=billerId,
                        itemId=itemId,
                        amount=amount,
                        phone_number=phone_number,
                        customerName=customerName,
                        otherField=otherField,
                        debitAccount=user.wallet.account_number,
                        transactionReference=tx_reference,
                    )
                except Exception as e:
                    logger.error(f"VAS electricity call error (bonus): {e}")
                    return self._handle_failure(
                        user=user,
                        guest_id=guest_id,
                        phone_number=phone_number,
                        amount=amount,
                        vas_response=None,
                        reason="Provider call error",
                    )

                # Check VAS status (same mapping as your Data endpoint)
                try:
                    status_resp = VAS.status(
                        bearer_token=vas_token, tx_ref=tx_reference
                    )
                    status_data = status_resp.json().get("data", {})
                except Exception:
                    status_data = {}

                if (
                    status_data.get("status") == "success"
                    and status_data.get("responseCode") == 200
                ):
                    return self._handle_success(
                        user=user,
                        guest_id=guest_id,
                        customerId=customerId,
                        billerId=billerId,
                        itemId=itemId,
                        amount=amount,
                        phone_number=phone_number,
                        customerName=customerName,
                        otherField=otherField,
                        vas_response=vas_response,
                        tx_reference=tx_reference,
                    )

            # If we reach here, bonus flow failed (insufficient bonus or VAS failure)
            return self._handle_failure(
                user=user,
                guest_id=guest_id,
                phone_number=phone_number,
                amount=amount,
                vas_response=(vas_response.json() if vas_response else None),
                reason="Insufficient bonus balance.",
            )

        # Centralized payment orchestration (mirrors AirTimeTopUp logic)
        pts_amt = 0
        if use_points:
            _, pts_amt = Pay.with_pts(user=user, amount=int(amount))
        if use_points and pts_amt >= int(amount):
            wallet_debit_amount = 0
        elif use_points and pts_amt < int(amount):
            wallet_debit_amount = int(amount) - pts_amt
        else:
            wallet_debit_amount = int(amount)

        match payment_option:
            case "WALLET":
                if not use_points and not use_cashback and not use_bonus:
                    # Wallet-only: debit user wallet directly
                    vas_response = VAS.bill_payment(
                        bearer_token=vas_token,
                        customerId=customerId,
                        billerId=billerId,
                        itemId=itemId,
                        amount=amount,
                        phone_number=phone_number,
                        customerName=customerName,
                        otherField=otherField,
                        debitAccount=user_wallet.account_number,
                        transactionReference=tx_reference,
                    )
                    if vas_response is None:
                        return self._handle_failure(
                            user=user,
                            guest_id=guest_id,
                            phone_number=phone_number,
                            amount=amount,
                            reason="VAS service unavailable.",
                        )
                    # Check if vas_response is successful
                    bill_success = False
                    try:
                        if hasattr(vas_response, "status_code") and (
                            str(vas_response.status_code) == "200"
                            or vas_response.status_code == 200
                        ):
                            bill_json = (
                                vas_response.json()
                                if hasattr(vas_response, "json")
                                else {}
                            )
                            bill_data = (
                                bill_json.get("data", {})
                                if isinstance(bill_json, dict)
                                else {}
                            )
                            if (
                                bill_data.get("status") == "success"
                                or bill_json.get("status") == "success"
                            ):
                                bill_success = True
                    except Exception as e:
                        logger.warning(f"Error parsing vas_response: {e}")

                    status_query = VAS.status(
                        bearer_token=vas_token, tx_ref=tx_reference
                    )
                    status_resp = (
                        status_query.json().get("data", {}) if status_query else {}
                    )
                    status_success = status_resp.get("status") == "success" or (
                        status_resp.get("responseCode") == "200"
                        or status_resp.get("responseCode") == 200
                    )

                    if bill_success or status_success:
                        return self._handle_success(
                            user=user,
                            guest_id=guest_id,
                            customerId=customerId,
                            billerId=billerId,
                            itemId=itemId,
                            amount=amount,
                            phone_number=phone_number,
                            customerName=customerName,
                            otherField=otherField,
                            vas_response=vas_response,
                            tx_reference=tx_reference,
                        )
                    else:
                        return self._handle_failure(
                            user=user,
                            guest_id=guest_id,
                            phone_number=phone_number,
                            amount=amount,
                            vas_response=vas_response,
                            reason="Bill payment failed.",
                        )
                # Hybrid: points/cashback/bonus + wallet, collect wallet portion to central, call VAS with central
                # Only perform local debit in hybrid cases
                if (
                    use_points or use_cashback or use_bonus
                ) and wallet_debit_amount > 0:
                    debit_response = Wallet.Debit(
                        debitAccount=user_wallet.account_number,
                        amount=wallet_debit_amount,
                        reason="Debit for bill payment (to central collection)",
                        merchantFeeAmount="",
                        destinationAccount=settings.CENTRAL_COLLECTION_ACCOUNT,
                    )
                    if (
                        debit_response is None
                        or str(debit_response.status_code) != "200"
                    ):
                        return self._handle_failure(
                            user=user,
                            guest_id=guest_id,
                            phone_number=phone_number,
                            amount=amount,
                            reason="Wallet service unavailable or debit failed.",
                        )
                vas_debit_account = settings.CENTRAL_OPERATIONAL_ACCOUNT
                vas_response = VAS.bill_payment(
                    bearer_token=vas_token,
                    customerId=customerId,
                    billerId=billerId,
                    itemId=itemId,
                    amount=amount,
                    phone_number=phone_number,
                    customerName=customerName,
                    otherField=otherField,
                    debitAccount=vas_debit_account,
                    transactionReference=tx_reference,
                )
                if vas_response is None:
                    # Refund only if hybrid (points/cashback/bonus + wallet)
                    if wallet_debit_amount > 0 and (
                        use_points or use_cashback or use_bonus
                    ):
                        Wallet.Credit(
                            acct_no=user_wallet.account_number,
                            amount=wallet_debit_amount,
                            reason="Refund after failed VAS bill payment",
                            sourceAccount=settings.CENTRAL_OPERATIONAL_ACCOUNT,
                        )
                    return self._handle_failure(
                        user=user,
                        guest_id=guest_id,
                        phone_number=phone_number,
                        amount=amount,
                        reason="VAS service unavailable.",
                    )
                status_query = VAS.status(bearer_token=vas_token, tx_ref=tx_reference)
                status_resp = (
                    status_query.json().get("data", {}) if status_query else {}
                )
                if (
                    status_resp.get("status") == "success"
                    and status_resp.get("responseCode") == 200
                ):
                    return self._handle_success(
                        user=user,
                        guest_id=guest_id,
                        customerId=customerId,
                        billerId=billerId,
                        itemId=itemId,
                        amount=amount,
                        phone_number=phone_number,
                        customerName=customerName,
                        otherField=otherField,
                        vas_response=vas_response,
                        tx_reference=tx_reference,
                    )
                else:
                    # Refund only if hybrid (points/cashback/bonus + wallet)
                    if wallet_debit_amount > 0 and (
                        use_points or use_cashback or use_bonus
                    ):
                        Wallet.Credit(
                            acct_no=user_wallet.account_number,
                            amount=wallet_debit_amount,
                            reason="Refund after failed VAS bill payment",
                            sourceAccount=settings.CENTRAL_OPERATIONAL_ACCOUNT,
                        )
                    return self._handle_failure(
                        user=user,
                        guest_id=guest_id,
                        phone_number=phone_number,
                        amount=amount,
                        vas_response=vas_response,
                        reason="Bill payment failed.",
                    )
            case "CARD":
                vas_debit_account = settings.CENTRAL_OPERATIONAL_ACCOUNT
                vas_response = VAS.bill_payment(
                    bearer_token=vas_token,
                    customerId=customerId,
                    billerId=billerId,
                    itemId=itemId,
                    amount=amount,
                    phone_number=phone_number,
                    customerName=customerName,
                    otherField=otherField,
                    debitAccount=vas_debit_account,
                    transactionReference=tx_reference,
                )
                if vas_response is None:
                    return self._handle_failure(
                        user=user,
                        guest_id=guest_id,
                        phone_number=phone_number,
                        amount=amount,
                        reason="VAS service unavailable.",
                    )
                status_query = VAS.status(bearer_token=vas_token, tx_ref=tx_reference)
                status_resp = (
                    status_query.json().get("data", {}) if status_query else {}
                )
                if (
                    status_resp.get("status") == "success"
                    and status_resp.get("responseCode") == 200
                ):
                    return self._handle_success(
                        user=user,
                        guest_id=guest_id,
                        customerId=customerId,
                        billerId=billerId,
                        itemId=itemId,
                        amount=amount,
                        phone_number=phone_number,
                        customerName=customerName,
                        otherField=otherField,
                        vas_response=vas_response,
                        tx_reference=tx_reference,
                    )
                else:
                    return self._handle_failure(
                        user=user,
                        guest_id=guest_id,
                        phone_number=phone_number,
                        amount=amount,
                        vas_response=vas_response,
                        reason="Bill payment failed.",
                    )
            case _:
                return Response(
                    data=encrypt(
                        {"status": "fail", "message": "Invalid payment option"}
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )
