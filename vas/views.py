import os
import json
import logging
import requests
from decimal import Decimal

from django.conf import settings
from django.db import transaction

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
from commons import Pay, Biometrics
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
        else:
            create_activity(guest_id=None, title=title, description=description)

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

        response_data = {
            "status": "fail",
            "message": f"Airtime purchase failed. {reason}",
            "error": airtime_response or {},
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
        if not vas_token:
            return Response(
                data=encrypt({"status": "fail", "message": "VAS service is temporarily unavailable."}),
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
                # Lock wallet row INSIDE the transaction to prevent the error
                if user and payment_option == "WALLET":
                    user_wallet = WalletModel.objects.select_for_update().get(user=user)
                elif user:
                    user_wallet = WalletModel.objects.filter(user=user).first()
                else:
                    user_wallet = None

                cashback_used = 0
                if use_cashback:
                    payment = CashbackService.apply_cashback_payment(
                        user=user, amount=amount
                    )
                    amount = payment["wallet_amount"]
                    cashback_used = payment["cashback_used"]

                # USE BONUS logic
                if use_bonus:
                    if user and user.welcome_bonus >= float(amount):
                        airtime_response = VAS.airtime_topup(
                            network=network,
                            bearer_token=vas_token,
                            amount=amount,
                            debitAccount=user_wallet.account_number,
                            phone_number=phone,
                            tx_ref=tx_reference,
                        )
                        if airtime_response is None:
                            return self._handle_airtime_failure(
                                user=user, phone=phone, amount=amount,
                                reason="VAS service unavailable.",
                            )
                        status_query = VAS.status(
                            bearer_token=vas_token, tx_ref=tx_reference
                        )
                        if status_query is None:
                            return self._handle_airtime_failure(
                                user=user, phone=phone, amount=amount,
                                reason="Could not verify transaction status.",
                            )
                        status_resp = status_query.json().get("data", {})
                        if (
                            status_resp.get("transactionStatus") == "success"
                            and status_resp.get("responseCode") == 200
                        ):
                            return self._handle_airtime_success(
                                user=user,
                                phone=phone,
                                amount=amount,
                                network=network,
                                tx_reference=tx_reference,
                                cashback=cashback_used,
                            )

                    return self._handle_airtime_failure(
                        user=user,
                        phone=phone,
                        amount=amount,
                        reason="Insufficient bonus balance.",
                    )

                # PAYMENT OPTIONS logic
                match payment_option:
                    case "WALLET":
                        amount = int(amount)
                        pts_amt = 0

                        if use_points:
                            _, pts_amt = Pay.with_pts(user=user, amount=amount)

                        if use_points and pts_amt >= amount:
                            wallet_debit_amount = 0
                        elif use_points and pts_amt < amount:
                            wallet_debit_amount = amount - pts_amt
                        else:
                            wallet_debit_amount = amount

                        if wallet_debit_amount > 0:
                            debit_response = Wallet.Debit(
                                debitAccount=user_wallet.account_number,
                                amount=wallet_debit_amount,
                                reason="Debit for airtime recharge.",
                                merchantFeeAmount="",
                            )

                            if debit_response is None:
                                return self._handle_airtime_failure(
                                    user=user, phone=phone, amount=amount,
                                    reason="Wallet service unavailable.",
                                )

                            if debit_response.status_code == 200:
                                airtime_response = VAS.airtime_topup(
                                    network=network,
                                    bearer_token=vas_token,
                                    amount=amount,
                                    debitAccount=user_wallet.account_number,
                                    phone_number=phone,
                                    tx_ref=tx_reference,
                                )

                                if airtime_response is None:
                                    return self._handle_airtime_failure(
                                        user=user, phone=phone, amount=amount,
                                        reason="VAS service unavailable.",
                                    )

                                airtime_data = airtime_response.json()
                                status_resp = VAS.status(
                                    bearer_token=vas_token, tx_ref=tx_reference
                                )
                                if status_resp is None:
                                    return self._handle_airtime_failure(
                                        user=user, phone=phone, amount=amount,
                                        reason="Could not verify transaction status.",
                                    )
                                status_data = status_resp.json().get("data", {})
                                if (
                                    status_data.get("transactionStatus") == "success"
                                    and status_data.get("responseCode") == 200
                                ):
                                    return self._handle_airtime_success(
                                        user=user,
                                        phone=phone,
                                        amount=amount,
                                        network=network,
                                        tx_reference=tx_reference,
                                    )
                                else:
                                    return self._handle_airtime_failure(
                                        user=user,
                                        phone=phone,
                                        amount=amount,
                                        airtime_response=airtime_data,
                                        reason="Airtime top-up failed.",
                                    )

                            return Response(
                                data=encrypt(debit_response.json()),
                                status=debit_response.status_code,
                            )

                        # Case where points covered everything
                        airtime_response = VAS.airtime_topup(
                            network=network,
                            bearer_token=vas_token,
                            amount=amount,
                            debitAccount=user_wallet.account_number,
                            phone_number=phone,
                            tx_ref=tx_reference,
                        )
                        if airtime_response is None:
                            return self._handle_airtime_failure(
                                user=user, phone=phone, amount=amount,
                                reason="VAS service unavailable.",
                            )
                        return self._handle_airtime_success(
                            user=user,
                            phone=phone,
                            amount=amount,
                            network=network,
                            tx_reference=tx_reference,
                        )

                    case "CARD":
                        debit_account = user_wallet.account_number if user else None
                        airtime_response = VAS.airtime_topup(
                            network=network,
                            bearer_token=vas_token,
                            amount=amount,
                            debitAccount=debit_account,
                            phone_number=phone,
                            tx_ref=tx_reference,
                        )

                        if airtime_response is None:
                            return self._handle_airtime_failure(
                                user=user, guest_id=guest_id,
                                phone=phone, amount=amount,
                                reason="VAS service unavailable.",
                            )

                        airtime_data = airtime_response.json()
                        if (
                            user
                            and airtime_data.get("status") == "success"
                            and airtime_data.get("responseCode") == 200
                        ):
                            return self._handle_airtime_success(
                                user=user,
                                phone=phone,
                                amount=amount,
                                network=network,
                                tx_reference=tx_reference,
                            )
                        else:
                            # Failure (user or guest)
                            return self._handle_airtime_failure(
                                user=user,
                                guest_id=guest_id,
                                phone=phone,
                                amount=amount,
                                airtime_response=airtime_data,
                                reason=airtime_data.get(
                                    "response_description", "Transaction failed"
                                ),
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
        """Handle failed Data purchase."""
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

        response_data = {
            "status": "fail",
            "message": f"Data purchase failed. {reason}",
            "error": data_response or {},
        }

        return Response(data=encrypt(response_data), status=status.HTTP_400_BAD_REQUEST)

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

        pin = user_data.get("pin")
        use_bonus = user_data.get("use_bonus")
        amount = user_data.get("amount")
        phone = user_data.get("phone_number")
        use_points = user_data.get("use_points")
        payment_option = user_data.get("payment_option")
        network = user_data.get("network")
        product_id = user_data.get("productId")
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
                data=encrypt({"status": "fail", "message": "VAS service is temporarily unavailable."}),
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
                    tx_ref=tx_reference,
                )
                if data_response is None:
                    return self._handle_data_failure(
                        user=user, phone=phone, amount=amount,
                        reason="VAS service unavailable.",
                    )
                status_resp = VAS.status(bearer_token=vas_token, tx_ref=tx_reference)
                if status_resp is None:
                    return self._handle_data_failure(
                        user=user, phone=phone, amount=amount,
                        reason="Could not verify transaction status.",
                    )
                status_data = status_resp.json().get("data", {})
                if (
                    status_data.get("transactionStatus") == "success"
                    and status_data.get("responseCode") == 200
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

            return self._handle_data_failure(
                user=user,
                phone=phone,
                amount=amount,
                data_response=data_response.json() if data_response else None,
                reason="Insufficient bonus balance.",
            )

        # PAYMENT OPTIONS
        match payment_option:
            case "WALLET":
                amount = int(amount)
                pts_amt = 0

                if use_points:
                    _, pts_amt = Pay.with_pts(user=user, amount=amount)

                # Determine wallet debit amount
                if use_points and pts_amt >= amount:
                    wallet_debit_amount = 0
                elif use_points and pts_amt < amount:
                    wallet_debit_amount = amount - pts_amt
                else:
                    wallet_debit_amount = amount

                # Debit wallet only if required
                if wallet_debit_amount > 0:
                    try:
                        with transaction.atomic():
                            account = WalletModel.objects.select_for_update().get(
                                user=user
                            )

                            debit_response = Wallet.Debit(
                                debitAccount=account.account_number,
                                amount=wallet_debit_amount,
                                reason="Debit for data subscription.",
                                transactionReference="",
                            )

                            if debit_response is None:
                                return self._handle_data_failure(
                                    user=user, phone=phone, amount=amount,
                                    reason="Wallet service unavailable.",
                                )

                            if debit_response.status_code == 200:
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
                                        user=user, phone=phone, amount=amount,
                                        reason="VAS service unavailable.",
                                    )

                                data_topup = data_response.json()
                                status_resp = VAS.status(
                                    bearer_token=vas_token, tx_ref=tx_reference
                                )
                                if status_resp is None:
                                    return self._handle_data_failure(
                                        user=user, phone=phone, amount=amount,
                                        reason="Could not verify transaction status.",
                                    )
                                status_data = status_resp.json().get("data", {})
                                if (
                                    status_data.get("transactionStatus") == "success"
                                    and status_data.get("responseCode") == 200
                                ):
                                    return self._handle_data_success(
                                        user=user,
                                        guest_id=guest_id,
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
                                        data_response=data_topup,
                                        reason="Data subscription failed after wallet debit.",
                                    )
                            return Response(
                                data=encrypt(debit_response.json()),
                                status=debit_response.status_code,
                            )
                    except Exception as e:
                        logger.exception(
                            f"Transaction error during wallet data purchase: {e}"
                        )
                        return Response(
                            data=encrypt(
                                {"status": "fail", "message": "Transaction failed"}
                            ),
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        )

            case "CARD":
                # Card flow for authenticated users and guests
                try:
                    data_response = VAS.data(
                        network=network,
                        bearer_token=vas_token,
                        amount=amount,
                        productId=product_id,
                        debitAccount=user_wallet.account_number if user_wallet else None,
                        phone_number=phone,
                        tx_ref=tx_reference,
                    )

                    if data_response is None:
                        return self._handle_data_failure(
                            user=user, guest_id=guest_id,
                            phone=phone, amount=amount,
                            reason="VAS service unavailable.",
                        )

                    data_topup = data_response.json()
                    status_resp = VAS.status(
                        bearer_token=vas_token, tx_ref=tx_reference
                    )
                    if status_resp is None:
                        return self._handle_data_failure(
                            user=user, guest_id=guest_id,
                            phone=phone, amount=amount,
                            reason="Could not verify transaction status.",
                        )
                    status_data = status_resp.json().get("data", {})
                    if (
                        status_data.get("transactionStatus") == "success"
                        and status_data.get("responseCode") == 200
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
                            phone=phone,
                            amount=amount,
                            data_response=data_topup,
                            reason="Data subscription failed after card debit.",
                        )
                except Exception as e:
                    logger.error(f"Card processing error: {str(e)}")
                    return Response(
                        data=encrypt(
                            {"status": "error", "message": "Processing error occurred"}
                        ),
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
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
                data=encrypt({"status": "fail", "message": "VAS service is temporarily unavailable."}),
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
                data=encrypt({"status": "fail", "message": "VAS service is temporarily unavailable."}),
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
                    data=encrypt({"status": "fail", "message": "VAS service is temporarily unavailable."}),
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

        # Generate transaction reference and authenticate VAS
        tx_reference = (
            idempotency_key if idempotency_key else VAS.generate_unique_code("PICA")
        )
        vas_token = VAS.authenticate()
        if not vas_token:
            return Response(
                data=encrypt({"status": "fail", "message": "VAS service is temporarily unavailable."}),
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
                    status_data.get("transactionStatus") == "success"
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

        # --- Normal payment flows (WALLET or CARD) ---
        match payment_option:
            case "WALLET":
                amount = int(amount)
                pts_amt = 0

                if use_points:
                    _, pts_amt = Pay.with_pts(user=user, amount=amount)

                # Determine wallet debit amount
                if use_points and pts_amt >= amount:
                    wallet_debit_amount = 0
                elif use_points and pts_amt < amount:
                    wallet_debit_amount = amount - pts_amt
                else:
                    wallet_debit_amount = amount

                # Debit user's account
                if wallet_debit_amount > 0:
                    try:
                        with transaction.atomic():
                            account = WalletModel.objects.select_for_update().get(
                                user=user
                            )

                            debit_response = Wallet.Debit(
                                debitAccount=account.account_number,
                                amount=wallet_debit_amount,
                                reason="Debit for bill payment.",
                                transactionReference="",
                            )

                            if debit_response is None:
                                return self._handle_failure(
                                    user=user, guest_id=guest_id,
                                    phone_number=phone_number, amount=amount,
                                    reason="Wallet service unavailable.",
                                )

                            if debit_response.status_code == 200:
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
                                    logger.error(
                                        f"VAS electricity call error (wallet): {e}"
                                    )
                                    return self._handle_failure(
                                        user=user,
                                        guest_id=guest_id,
                                        phone_number=phone_number,
                                        amount=amount,
                                        vas_response=None,
                                        reason="Provider call error",
                                    )

                                # Check VAS status
                                try:
                                    status_resp = VAS.status(
                                        bearer_token=vas_token, tx_ref=tx_reference
                                    )
                                    status_data = status_resp.json().get("data", {})
                                except Exception:
                                    status_data = {}

                                if (
                                    status_data.get("transactionStatus") == "success"
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
                                else:
                                    # VAS failed after debit
                                    vas_data = (
                                        vas_response.json() if vas_response else {}
                                    )
                                    return self._handle_failure(
                                        user=user,
                                        guest_id=guest_id,
                                        phone_number=phone_number,
                                        amount=amount,
                                        vas_response=vas_data,
                                        reason="Bill payment failed after wallet debit.",
                                    )

                            # debit_response not 200 -> pass the debit response back
                            return Response(
                                data=encrypt(debit_response.json()),
                                status=debit_response.status_code,
                            )
                    except Exception as e:
                        logger.exception(
                            f"Transaction error during wallet bill payment: {e}"
                        )
                        return Response(
                            data=encrypt(
                                {"status": "fail", "message": "Transaction failed"}
                            ),
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        )

            case "CARD":
                # Card flow for both authenticated users and guests
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
                        debitAccount=(user.wallet.account_number if user else None),
                        transactionReference=tx_reference,
                    )
                except Exception as e:
                    logger.error(f"Card VAS call error: {e}")
                    return Response(
                        data=encrypt(
                            {"status": "error", "message": "Processing error occurred"}
                        ),
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    )

                vas_data_raw = vas_response.json() if vas_response else {}
                # Check VAS status
                try:
                    status_resp = VAS.status(
                        bearer_token=vas_token, tx_ref=tx_reference
                    )
                    status_data = status_resp.json().get("data", {})
                except Exception:
                    status_data = {}

                if (
                    status_data.get("transactionStatus") == "success"
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
                else:
                    return self._handle_failure(
                        user=user,
                        guest_id=guest_id,
                        phone_number=phone_number,
                        amount=amount,
                        vas_response=vas_data_raw,
                        reason="Bill payment failed after card processing.",
                    )

            case _:
                return Response(
                    data=encrypt(
                        {"status": "fail", "message": "Invalid payment option"}
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )
