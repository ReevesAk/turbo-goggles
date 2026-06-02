import logging
import requests
from decimal import Decimal

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
from banking.cashback_service import CashbackService
from banking.tasks import post_vas_update
from permissions import IsAuthenticatedOrGuestWithValidId
from banking.helpers import Pin, verify_wallet_auth
from gamification.models import Points as PointsModel
from treasury.models import TreasuryAccount
from treasury.helpers import Pin as TreasuryPin
from treasury.controllers import Anchor, anchor_ops_account_id
from treasury.tasks import post_treasury_vas_update
from .utility import (
    create_activity,
    create_notification,
    # send_token,
    # send_token_to_guest_users,
)

from .controllers import VTPass
from .models import ValueAddedServices
from commons import Pay, Biometrics, Messaging
from security import encrypt, decrypt

logger = logging.getLogger(__name__)


@extend_schema(summary="Purchase airtime for any Nigerian network", tags=["VAS"])
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
        account_number="",
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

            post_vas_update.delay(
                user_id=user.id,
                account_number=account_number,
                amount_str=str(amount),
                tx_reference=tx_reference,
                service_type="AIRTIME",
                phone=phone,
                network=network,
                alert_type=getattr(user, "alert_type_choice", "Both"),
                phone_number=getattr(user, "phone_number", None),
                email=getattr(user, "email", None),
            )
        else:
            create_activity(guest_id=guest_id, title=title, description=description)

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
            idempotency_key if idempotency_key else VTPass.generate_request_id("PICA")
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

        # Acquire lock, apply cashback/points deductions, then release before VTPass call
        user_wallet = None
        account_number = ""
        cashback_used = Decimal("0")
        pts_used = Decimal("0")
        purchase_amount = int(amount) if amount else 0

        try:
            with transaction.atomic():
                if user and payment_option == "WALLET":
                    user_wallet = WalletModel.objects.select_for_update().get(user=user)
                elif user:
                    user_wallet = WalletModel.objects.filter(user=user).first()

                if (use_cashback or use_points) and payment_option == "WALLET":
                    avail_cashback = (
                        user_wallet.cashback_balance
                        if (user_wallet and use_cashback)
                        else Decimal("0")
                    )
                    avail_pts = Decimal("0")
                    if use_points:
                        try:
                            pts_obj = PointsModel.objects.get(user=user)
                            avail_pts = pts_obj.naira_value
                        except Exception:
                            pass
                    if avail_cashback + avail_pts < Decimal(str(purchase_amount)):
                        raise ValueError("insufficient_hybrid_balance")
                    if use_cashback:
                        payment = CashbackService.apply_cashback_payment(
                            user=user, amount=purchase_amount
                        )
                        cashback_used = payment["cashback_used"]
                        remaining = int(payment["wallet_amount"])
                    else:
                        remaining = purchase_amount
                    if use_points and remaining > 0:
                        Pay.with_pts(user=user, amount=remaining)
                        pts_used = avail_pts

                account_number = user_wallet.account_number if user_wallet else ""
        except WalletModel.DoesNotExist:
            return Response(
                data=encrypt({"status": "fail", "message": "Wallet not found"}),
                status=404,
            )
        except ValueError as e:
            if "insufficient_hybrid_balance" in str(e):
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "message": "Insufficient points/cashback balance to complete this purchase.",
                        }
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )
            logger.exception(f"Error preparing airtime purchase: {e}")
            return Response(
                data=encrypt({"status": "fail", "message": "Transaction failed"}),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        except Exception as e:
            logger.exception(f"Error preparing airtime purchase: {e}")
            return Response(
                data=encrypt({"status": "fail", "message": "Transaction failed"}),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        # Lock released — VTPass call proceeds without holding the DB lock

        try:
            match payment_option:
                case "WALLET":
                    if not use_points and not use_cashback and not use_bonus:
                        airtime_response = VTPass.airtime(
                            serviceID=network,
                            amount=amount,
                            phone=phone,
                            request_id=tx_reference,
                        )
                        if airtime_response is None:
                            return self._handle_airtime_failure(
                                user=user,
                                phone=phone,
                                amount=amount,
                                reason="VAS service unavailable.",
                            )
                        if VTPass.is_success(airtime_response):
                            return self._handle_airtime_success(
                                user=user,
                                phone=phone,
                                amount=amount,
                                network=network,
                                tx_reference=tx_reference,
                                cashback=cashback_used,
                                account_number=account_number,
                            )
                        # Fallback: confirm via requery
                        requery_resp = VTPass.requery(tx_reference)
                        if requery_resp and VTPass.is_success(requery_resp):
                            return self._handle_airtime_success(
                                user=user,
                                phone=phone,
                                amount=amount,
                                network=network,
                                tx_reference=tx_reference,
                                cashback=cashback_used,
                                account_number=account_number,
                            )
                        return self._handle_airtime_failure(
                            user=user,
                            phone=phone,
                            amount=amount,
                            airtime_response=airtime_response,
                            reason="Airtime top-up failed.",
                        )

                    # Hybrid: cashback/points cover full purchase
                    airtime_response = VTPass.airtime(
                        serviceID=network,
                        amount=purchase_amount,
                        phone=phone,
                        request_id=tx_reference,
                    )
                    if airtime_response is None:
                        if cashback_used:
                            CashbackService.refund_cashback(
                                user=user, cashback_amount=cashback_used
                            )
                        if pts_used:
                            Pay.refund_pts(user=user, naira_amount=pts_used)
                        return self._handle_airtime_failure(
                            user=user,
                            phone=phone,
                            amount=purchase_amount,
                            reason="VAS service unavailable.",
                        )
                    if VTPass.is_success(airtime_response):
                        return self._handle_airtime_success(
                            user=user,
                            phone=phone,
                            amount=purchase_amount,
                            network=network,
                            tx_reference=tx_reference,
                            cashback=cashback_used,
                            account_number=account_number,
                        )
                    else:
                        if cashback_used:
                            CashbackService.refund_cashback(
                                user=user, cashback_amount=cashback_used
                            )
                        if pts_used:
                            Pay.refund_pts(user=user, naira_amount=pts_used)
                        return self._handle_airtime_failure(
                            user=user,
                            phone=phone,
                            amount=purchase_amount,
                            airtime_response=airtime_response,
                            reason="Airtime top-up failed.",
                        )

                case "CARD":
                    airtime_response = VTPass.airtime(
                        serviceID=network,
                        amount=amount,
                        phone=phone,
                        request_id=tx_reference,
                    )
                    if airtime_response is None:
                        return self._handle_airtime_failure(
                            user=user,
                            guest_id=guest_id,
                            phone=phone,
                            amount=amount,
                            reason="VAS service unavailable.",
                        )
                    if VTPass.is_success(airtime_response):
                        return self._handle_airtime_success(
                            user=user,
                            guest_id=guest_id,
                            phone=phone,
                            amount=amount,
                            network=network,
                            tx_reference=tx_reference,
                            cashback=cashback_used,
                            account_number=account_number,
                        )
                    # Fallback: confirm via requery
                    requery_resp = VTPass.requery(tx_reference)
                    if requery_resp and VTPass.is_success(requery_resp):
                        return self._handle_airtime_success(
                            user=user,
                            guest_id=guest_id,
                            phone=phone,
                            amount=amount,
                            network=network,
                            tx_reference=tx_reference,
                            cashback=cashback_used,
                            account_number=account_number,
                        )
                    return self._handle_airtime_failure(
                        user=user,
                        guest_id=guest_id,
                        phone=phone,
                        amount=amount,
                        airtime_response=airtime_response,
                        reason="Airtime top-up failed.",
                    )

                # case "TREASURY": disabled — treasury VAS payments on hold
                case _:
                    return Response(
                        data=encrypt(
                            {"status": "fail", "message": "Invalid payment option"}
                        ),
                        status=status.HTTP_400_BAD_REQUEST,
                    )
        except Exception as e:
            logger.exception(f"Transaction error during airtime purchase: {e}")
            return Response(
                data=encrypt({"status": "fail", "message": "Transaction failed"}),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


@extend_schema(
    summary="Get data plans for a network provider",
    description="Retrieve variation codes for a network provider. Pass the network name (e.g. mtn, glo, airtel, etisalat).",
    tags=["VAS"],
)
class GetDataPlans(generics.RetrieveAPIView):
    serializer_class = VasStatusSerializer

    @extend_schema(
        description="Retrieve variation codes for a network provider. Pass the network name (e.g. mtn, glo, airtel, etisalat).",
        responses={
            200: OpenApiResponse(description="Successfully retrieved data plans"),
            400: OpenApiResponse(description="Invalid network provided"),
            502: OpenApiResponse(
                description="Failed to fetch data plans from provider"
            ),
            500: OpenApiResponse(description="Server error processing request"),
        },
    )
    def get(self, request, *args, **kwargs):
        # Accept network from path param or query param
        network = kwargs.get("network") or request.query_params.get("network")
        if not network:
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "network (path param or query param) is required. e.g. mtn, glo, airtel, etisalat",
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        service_id = f"{network}-data"
        vas_response = VTPass.service_variations(serviceID=service_id)
        if not vas_response:
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "Failed to fetch data plans from VAS provider.",
                    }
                ),
                status=status.HTTP_502_BAD_GATEWAY,
            )

        if vas_response.status_code != 200 or not VTPass.is_success(vas_response):
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "Failed to fetch data plans from VAS provider.",
                    }
                ),
                status=status.HTTP_502_BAD_GATEWAY,
            )

        try:
            plans_data = vas_response.json()
        except Exception as e:
            logger.error(f"Error parsing VTPass service_variations response: {e}")
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "Invalid response format from VAS provider.",
                    }
                ),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        try:
            plans_data = CashbackService.add_cashback_to_bundles(plans_data)
        except Exception as e:
            logger.warning(f"Could not attach cashback to bundles: {e}")

        return Response(
            data=encrypt({"status": "success", "data": plans_data}),
            status=status.HTTP_200_OK,
        )


@extend_schema(summary="Subscribe to a mobile data bundle", tags=["VAS"])
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
        account_number="",
    ):
        """Handle successful data purchase."""
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

            if cashback is not None:
                response_data["cashback_used"] = str(cashback)

            post_vas_update.delay(
                user_id=user.id,
                account_number=account_number,
                amount_str=str(amount),
                tx_reference=tx_reference,
                service_type="DATA",
                phone=phone,
                network=network,
                alert_type=getattr(user, "alert_type_choice", "Both"),
                phone_number=getattr(user, "phone_number", None),
                email=getattr(user, "email", None),
            )
        else:
            create_activity(guest_id=guest_id, title=title, description=description)

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
        if hasattr(data_response, "status_code") and hasattr(data_response, "text"):
            logger.warning(f"Third-party response status: {data_response.status_code}")
            logger.warning(f"Third-party response body: {data_response.text}")
        elif data_response is not None:
            logger.warning(f"Data failure response: {data_response}")
        else:
            logger.warning("Data failure: No response body from provider.")

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
        pts_used = Decimal("0")

        tx_reference = (
            idempotency_key if idempotency_key else VTPass.generate_request_id("PICA")
        )

        purchase_amount = int(amount) if amount else 0

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
                data_response = VTPass.data(
                    serviceID=f"{network}-data",
                    variation_code=product_id,
                    amount=amount,
                    phone=phone,
                    request_id=tx_reference,
                )
                if data_response is None:
                    return self._handle_data_failure(
                        user=user,
                        phone=phone,
                        amount=amount,
                        reason="VAS service unavailable.",
                    )
                if VTPass.is_success(data_response):
                    return self._handle_data_success(
                        user=user,
                        guest_id=guest_id,
                        phone=phone,
                        amount=amount,
                        network=network,
                        tx_reference=tx_reference,
                        cashback=cashback_used,
                    )
                # Fallback requery
                requery_resp = VTPass.requery(tx_reference)
                if requery_resp and VTPass.is_success(requery_resp):
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
                    data_response=data_response,
                    reason="Data subscription failed.",
                )
            else:
                return self._handle_data_failure(
                    user=user,
                    phone=phone,
                    amount=amount,
                    reason="Insufficient bonus balance.",
                )

        if (use_cashback or use_points) and payment_option == "WALLET" and user:
            avail_cashback = Decimal("0")
            if use_cashback:
                try:
                    w = WalletModel.objects.get(user=user)
                    avail_cashback = w.cashback_balance
                except WalletModel.DoesNotExist:
                    pass
            avail_pts = Decimal("0")
            if use_points:
                try:
                    from gamification.models import Points as PointsModel

                    pts_obj = PointsModel.objects.get(user=user)
                    avail_pts = pts_obj.naira_value
                except Exception:
                    pass
            if avail_cashback + avail_pts < Decimal(str(purchase_amount)):
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "message": "Insufficient points/cashback balance to complete this purchase.",
                        }
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if use_cashback:
                payment = CashbackService.apply_cashback_payment(
                    user=user, amount=purchase_amount
                )
                cashback_used = payment["cashback_used"]
                remaining = int(payment["wallet_amount"])
            else:
                remaining = purchase_amount
            if use_points and remaining > 0:
                Pay.with_pts(user=user, amount=remaining)
                pts_used = avail_pts

        match payment_option:
            case "WALLET":
                if not use_points and not use_cashback and not use_bonus:
                    data_response = VTPass.data(
                        serviceID=f"{network}-data",
                        variation_code=product_id,
                        amount=amount,
                        phone=phone,
                        request_id=tx_reference,
                    )
                    if data_response is None:
                        return self._handle_data_failure(
                            user=user,
                            phone=phone,
                            amount=amount,
                            reason="VAS service unavailable.",
                        )
                    if VTPass.is_success(data_response):
                        return self._handle_data_success(
                            user=user,
                            phone=phone,
                            productId=product_id,
                            amount=amount,
                            network=network,
                            tx_reference=tx_reference,
                            cashback=cashback_used,
                        )
                    # Fallback requery
                    requery_resp = VTPass.requery(tx_reference)
                    if requery_resp and VTPass.is_success(requery_resp):
                        return self._handle_data_success(
                            user=user,
                            phone=phone,
                            productId=product_id,
                            amount=amount,
                            network=network,
                            tx_reference=tx_reference,
                            cashback=cashback_used,
                        )
                    return self._handle_data_failure(
                        user=user,
                        phone=phone,
                        amount=amount,
                        data_response=data_response,
                        reason="Data subscription failed.",
                    )

                # Hybrid: cashback/points cover full purchase
                data_response = VTPass.data(
                    serviceID=f"{network}-data",
                    variation_code=product_id,
                    amount=purchase_amount,
                    phone=phone,
                    request_id=tx_reference,
                )
                if data_response is None:
                    if cashback_used:
                        CashbackService.refund_cashback(
                            user=user, cashback_amount=cashback_used
                        )
                    if pts_used:
                        Pay.refund_pts(user=user, naira_amount=pts_used)
                    return self._handle_data_failure(
                        user=user,
                        phone=phone,
                        amount=purchase_amount,
                        reason="VAS service unavailable.",
                    )
                if VTPass.is_success(data_response):
                    return self._handle_data_success(
                        user=user,
                        phone=phone,
                        productId=product_id,
                        amount=purchase_amount,
                        network=network,
                        tx_reference=tx_reference,
                        cashback=cashback_used,
                    )
                else:
                    if cashback_used:
                        CashbackService.refund_cashback(
                            user=user, cashback_amount=cashback_used
                        )
                    if pts_used:
                        Pay.refund_pts(user=user, naira_amount=pts_used)
                    return self._handle_data_failure(
                        user=user,
                        phone=phone,
                        amount=purchase_amount,
                        data_response=data_response,
                        reason="Data subscription failed.",
                    )

            # case "TREASURY": disabled — treasury VAS payments on hold
            case "CARD":
                data_response = VTPass.data(
                    serviceID=f"{network}-data",
                    variation_code=product_id,
                    amount=amount,
                    phone=phone,
                    request_id=tx_reference,
                )
                if data_response is None:
                    return self._handle_data_failure(
                        user=user,
                        guest_id=guest_id,
                        phone=phone,
                        amount=amount,
                        reason="VAS service unavailable.",
                    )
                if VTPass.is_success(data_response):
                    return self._handle_data_success(
                        user=user,
                        guest_id=guest_id,
                        phone=phone,
                        productId=product_id,
                        amount=amount,
                        network=network,
                        tx_reference=tx_reference,
                    )
                # Fallback requery
                requery_resp = VTPass.requery(tx_reference)
                if requery_resp and VTPass.is_success(requery_resp):
                    return self._handle_data_success(
                        user=user,
                        guest_id=guest_id,
                        phone=phone,
                        productId=product_id,
                        amount=amount,
                        network=network,
                        tx_reference=tx_reference,
                    )
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


@extend_schema(summary="Get service variations for a given VAS serviceID", tags=["VAS"])
class GetPaymentCategoriesView(APIView):
    """
    Returns service variations for a given serviceID.
    Pass serviceID as a query param (e.g. ?serviceID=dstv).
    """

    def get(self, request, *args, **kwargs):
        service_id = request.query_params.get("serviceID")
        if not service_id:
            return Response(
                data=encrypt(
                    {"status": "fail", "message": "serviceID query param is required."}
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        variations_resp = VTPass.service_variations(serviceID=service_id)
        if not variations_resp or not VTPass.is_success(variations_resp):
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "Failed to retrieve service variations.",
                    }
                ),
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(
            data=encrypt(
                {
                    "status": "success",
                    "message": "Service variations retrieved successfully.",
                    "data": variations_resp.json().get("content", {}),
                }
            ),
            status=status.HTTP_200_OK,
        )


@extend_schema(summary="Get bill payment categories for a serviceID", tags=["VAS"])
class BillPaymentCategoriesView(APIView):
    """
    Returns service variations for a bill payment serviceID (e.g. dstv, gotv, ikeja-electric).
    """

    def get(self, request, *args, **kwargs):
        service_id = kwargs.get("category_id") or request.query_params.get("serviceID")
        if not service_id:
            return Response(
                data=encrypt({"status": "fail", "message": "serviceID is required."}),
                status=status.HTTP_400_BAD_REQUEST,
            )
        variations_resp = VTPass.service_variations(serviceID=service_id)
        if not variations_resp or not VTPass.is_success(variations_resp):
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "Failed to retrieve bill payment categories.",
                    }
                ),
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(
            data=encrypt(
                {
                    "status": "success",
                    "message": "Bill payment categories retrieved successfully.",
                    "data": variations_resp.json().get("content", {}),
                }
            ),
            status=status.HTTP_200_OK,
        )


@extend_schema(summary="Get biller categories for a serviceID", tags=["VAS"])
class BillersCategoriesView(APIView):
    """
    Returns service variations for a biller serviceID.
    """

    def get(self, request, *args, **kwargs):
        service_id = kwargs.get("billers_id") or request.query_params.get("serviceID")
        if not service_id:
            return Response(
                data=encrypt({"status": "fail", "message": "serviceID is required."}),
                status=status.HTTP_400_BAD_REQUEST,
            )
        variations_resp = VTPass.service_variations(serviceID=service_id)
        if not variations_resp or not VTPass.is_success(variations_resp):
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "Failed to retrieve billers categories.",
                    }
                ),
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(
            data=encrypt(
                {
                    "status": "success",
                    "message": "Billers categories retrieved successfully.",
                    "data": variations_resp.json().get("content", {}),
                }
            ),
            status=status.HTTP_200_OK,
        )


@extend_schema(
    summary="Verify a biller account (meter number or smart card)", tags=["VAS"]
)
class VerifyBillerAccountView(generics.GenericAPIView):
    """
    VerifyBillerAccountView is a POST request handler for verifying
    a meter number (electricity) or smart card / IUC number (cable TV).
    """

    serializer_class = VerifyBillerSerializer

    def post(self, request):
        decrypted_payload = decrypt(request.data)
        user_data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_payload.items()
        }

        logger.info(
            f"User {request.user.first_name} {request.user.last_name} is attempting to verify biller account with data: {user_data}"
        )

        # billerId maps to VTPass serviceID (e.g. ikeja-electric, dstv)
        # customerId maps to VTPass billersCode (meter / IUC number)
        service_id = user_data.get("billerId")
        billers_code = user_data.get("customerId")
        meter_type = user_data.get(
            "meter_type"
        )  # prepaid | postpaid (electricity only)

        if not service_id or not billers_code:
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "billerId and customerId are required.",
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            verify_resp = VTPass.verify_merchant(
                serviceID=service_id,
                billersCode=billers_code,
                meter_type=meter_type,
            )

            if verify_resp is None:
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "message": "Bill verification service is unavailable. Please try again.",
                        }
                    ),
                    status=status.HTTP_502_BAD_GATEWAY,
                )

            if VTPass.is_success(verify_resp):
                response_data = {
                    "status": "success",
                    "data": verify_resp.json().get("content", {}),
                }
                logger.info(
                    f"Biller verification successful for {request.user.first_name} {request.user.last_name}: {response_data}"
                )
                return Response(data=encrypt(response_data), status=status.HTTP_200_OK)
            else:
                biller_response = verify_resp.json()
                logger.warning(
                    f"Biller verification failed for {request.user.first_name} {request.user.last_name}: {biller_response}"
                )
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "message": "Biller verification failed.",
                            "error": biller_response,
                        }
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )

        except requests.exceptions.RequestException as e:
            logger.error(
                f"RequestException for {request.user.first_name} {request.user.last_name}: {str(e)}"
            )
            return Response(
                data=encrypt({"error": str(e)}),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


@extend_schema(summary="Pay electricity or cable TV bill", tags=["VAS"])
class BillPaymentView(generics.GenericAPIView):
    """
    Unified BillPaymentView for both Electricity and Cable subscriptions.
    Service type is detected from VTPass response: if response content includes
    a 'token' field, the service is Electricity. Otherwise it's Cable.
    """

    serializer_class = BillPaymentSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticatedOrGuestWithValidId]

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
        account_number="",
    ):
        """
        Central success handler for both Electricity (token) and Cable.
        vas_response is the requests.Response object returned from VTPass.pay().
        """
        vas_json = {}
        try:
            vas_json = (
                vas_response.json()
                if hasattr(vas_response, "json")
                else vas_response or {}
            )
        except Exception:
            vas_json = vas_response or {}

        # VTPass response structure: {"code": "000", "content": {"transactions": {...}}}
        vas_content = vas_json.get("content", {}) if isinstance(vas_json, dict) else {}
        vas_data = vas_content.get("transactions", vas_content)

        # Determine if electricity by presence of token
        token = vas_data.get("token") if isinstance(vas_data, dict) else None
        is_electricity = bool(token)

        response_data = {
            "status": "success",
            "message": f"Purchase of {amount} was successful.",
            "bonus balance": getattr(user, "welcome_bonus", 0),
        }

        if is_electricity:
            response_data["token_details"] = token
            response_data["units_bought"] = vas_data.get("units", "")

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

        if user:
            post_vas_update.delay(
                user_id=user.id,
                account_number=account_number,
                amount_str=str(amount),
                tx_reference=tx_reference,
                service_type="BILL",
                phone=phone_number or customerName or customerId,
                network=None,
                alert_type=getattr(user, "alert_type_choice", "Both"),
                phone_number=getattr(user, "phone_number", None),
                email=getattr(user, "email", None),
            )

        if user and is_electricity and token:
            alert_type = getattr(user, "alert_type_choice", "Both")
            units = vas_data.get("units", "") if isinstance(vas_data, dict) else ""
            sms_msg = f"Your electricity token is: {token}"
            if units:
                sms_msg += f" | Units: {units}"
            sms_msg += f" | Ref: {tx_reference}"

            if alert_type in ("SMS", "Both") and getattr(user, "phone_number", None):
                Messaging.send_sms(phone_number=user.phone_number[1:], msg=sms_msg)

            if alert_type in ("Email", "Both") and getattr(user, "email", None):
                from django.template.loader import render_to_string

                email_body = render_to_string(
                    "picadailys_email.html",
                    {
                        "title": "Electricity Token",
                        "rows": [
                            {"label": "Token", "value": token},
                            {"label": "Units", "value": units or "N/A"},
                            {"label": "Amount", "value": f"₦{float(amount):,.2f}"},
                            {"label": "Meter Number", "value": customerId or ""},
                            {"label": "Reference", "value": tx_reference},
                        ],
                        "support_email": "notifications@picadailys.com",
                        "picadailys_phone": "02012271894 02012271895",
                    },
                )
                Messaging.send_email(
                    email=user.email,
                    subject="Your Electricity Token",
                    html_content=email_body,
                    sender_email="notifications@picadailys.com",
                    body=sms_msg,
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
        # billerId → VTPass serviceID (e.g. ikeja-electric, dstv)
        # customerId → VTPass billersCode (meter / IUC number)
        # itemId → VTPass variation_code (prepaid/postpaid or package code)
        pin = user_data.get("pin")
        use_bonus = user_data.get("use_bonus")
        amount = user_data.get("amount")
        use_points = user_data.get("use_points")
        payment_option = user_data.get("payment_option")
        customerId = user_data.get("customerId")
        billerId = user_data.get("billerId")
        phone_number = user_data.get("phone_number") or (
            user.phone_number if user else None
        )
        customerName = user_data.get("customerName")
        itemId = user_data.get("itemId")
        otherField = user_data.get("otherField")
        biometrics = user_data.get("use_biometrics")
        use_cashback = user_data.get("use_cashback")

        tx_reference = (
            idempotency_key if idempotency_key else VTPass.generate_request_id("PICA")
        )

        # Acquire and immediately release wallet lock
        user_wallet = None
        account_number = ""
        if user:
            try:
                with transaction.atomic():
                    user_wallet = WalletModel.objects.select_for_update().get(user=user)
                    account_number = user_wallet.account_number
            except WalletModel.DoesNotExist:
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

        # --- Use bonus flow ---
        if use_bonus:
            if user and user.welcome_bonus >= float(amount):
                try:
                    vas_response = VTPass.pay(
                        serviceID=billerId,
                        variation_code=itemId,
                        amount=amount,
                        phone=phone_number,
                        request_id=tx_reference,
                        billersCode=customerId,
                    )
                except Exception as e:
                    logger.error(f"VTPass pay error (bonus): {e}")
                    return self._handle_failure(
                        user=user,
                        guest_id=guest_id,
                        phone_number=phone_number,
                        amount=amount,
                        vas_response=None,
                        reason="Provider call error",
                    )

                if vas_response and VTPass.is_success(vas_response):
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
                        account_number=account_number,
                    )
                # Fallback requery
                try:
                    requery_resp = VTPass.requery(tx_reference)
                    if requery_resp and VTPass.is_success(requery_resp):
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
                            account_number=account_number,
                        )
                except Exception:
                    pass

            return self._handle_failure(
                user=user,
                guest_id=guest_id,
                phone_number=phone_number,
                amount=amount,
                vas_response=(vas_response.json() if vas_response else None),
                reason="Insufficient bonus balance.",
            )

        # Centralized payment orchestration
        cashback_used = Decimal("0")
        pts_used = Decimal("0")
        purchase_amount = int(amount) if amount else 0

        if (use_cashback or use_points) and payment_option == "WALLET" and user:
            avail_cashback = Decimal("0")
            if use_cashback:
                try:
                    w = WalletModel.objects.get(user=user)
                    avail_cashback = w.cashback_balance
                except WalletModel.DoesNotExist:
                    pass
            avail_pts = Decimal("0")
            if use_points:
                try:
                    from gamification.models import Points as PointsModel

                    pts_obj = PointsModel.objects.get(user=user)
                    avail_pts = pts_obj.naira_value
                except Exception:
                    pass
            if avail_cashback + avail_pts < Decimal(str(purchase_amount)):
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "message": "Insufficient points/cashback balance to complete this purchase.",
                        }
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if use_cashback:
                payment = CashbackService.apply_cashback_payment(
                    user=user, amount=purchase_amount
                )
                cashback_used = payment["cashback_used"]
                remaining = int(payment["wallet_amount"])
            else:
                remaining = purchase_amount
            if use_points and remaining > 0:
                Pay.with_pts(user=user, amount=remaining)
                pts_used = avail_pts

        match payment_option:
            case "WALLET":
                if not use_points and not use_cashback and not use_bonus:
                    vas_response = VTPass.pay(
                        serviceID=billerId,
                        variation_code=itemId,
                        amount=amount,
                        phone=phone_number,
                        request_id=tx_reference,
                        billersCode=customerId,
                    )
                    if vas_response is None:
                        return self._handle_failure(
                            user=user,
                            guest_id=guest_id,
                            phone_number=phone_number,
                            amount=amount,
                            reason="VAS service unavailable.",
                        )
                    if VTPass.is_success(vas_response):
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
                            account_number=account_number,
                        )
                    # Fallback requery
                    requery_resp = VTPass.requery(tx_reference)
                    if requery_resp and VTPass.is_success(requery_resp):
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
                            account_number=account_number,
                        )
                    return self._handle_failure(
                        user=user,
                        guest_id=guest_id,
                        phone_number=phone_number,
                        amount=amount,
                        vas_response=vas_response,
                        reason="Bill payment failed.",
                    )

                # Hybrid: cashback/points cover full purchase
                vas_response = VTPass.pay(
                    serviceID=billerId,
                    variation_code=itemId,
                    amount=purchase_amount,
                    phone=phone_number,
                    request_id=tx_reference,
                    billersCode=customerId,
                )
                if vas_response is None:
                    if cashback_used:
                        CashbackService.refund_cashback(
                            user=user, cashback_amount=cashback_used
                        )
                    if pts_used:
                        Pay.refund_pts(user=user, naira_amount=pts_used)
                    return self._handle_failure(
                        user=user,
                        guest_id=guest_id,
                        phone_number=phone_number,
                        amount=purchase_amount,
                        reason="VAS service unavailable.",
                    )
                if VTPass.is_success(vas_response):
                    return self._handle_success(
                        user=user,
                        guest_id=guest_id,
                        customerId=customerId,
                        billerId=billerId,
                        itemId=itemId,
                        amount=purchase_amount,
                        phone_number=phone_number,
                        customerName=customerName,
                        otherField=otherField,
                        vas_response=vas_response,
                        tx_reference=tx_reference,
                        account_number=account_number,
                    )
                else:
                    if cashback_used:
                        CashbackService.refund_cashback(
                            user=user, cashback_amount=cashback_used
                        )
                    if pts_used:
                        Pay.refund_pts(user=user, naira_amount=pts_used)
                    return self._handle_failure(
                        user=user,
                        guest_id=guest_id,
                        phone_number=phone_number,
                        amount=purchase_amount,
                        vas_response=vas_response,
                        reason="Bill payment failed.",
                    )

            # case "TREASURY": disabled — treasury VAS payments on hold
            case "CARD":
                vas_response = VTPass.pay(
                    serviceID=billerId,
                    variation_code=itemId,
                    amount=amount,
                    phone=phone_number,
                    request_id=tx_reference,
                    billersCode=customerId,
                )
                if vas_response is None:
                    return self._handle_failure(
                        user=user,
                        guest_id=guest_id,
                        phone_number=phone_number,
                        amount=amount,
                        reason="VAS service unavailable.",
                    )
                if VTPass.is_success(vas_response):
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
                        account_number=account_number,
                    )
                # Fallback requery
                requery_resp = VTPass.requery(tx_reference)
                if requery_resp and VTPass.is_success(requery_resp):
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
                        account_number=account_number,
                    )
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
