import logging
import requests
from decimal import Decimal

from django.db import transaction
from rest_framework.views import APIView
from rest_framework import generics, status
from rest_framework.response import Response

# from rest_framework.permissions import IsAuthenticated

import rest_framework.serializers as s
from drf_spectacular.utils import (
    extend_schema,
    OpenApiParameter,
    OpenApiResponse,
    inline_serializer,
)
from drf_spectacular.types import OpenApiTypes

from .serializers import (
    VasStatusSerializer,
    VerifyBillerSerializer,
    AirtimeTopupSerializer,
    DataSubscriptionSerializer,
    BillPaymentSerializer,
)
from accounts.models import TxModel
from banking.tx import build_receipt
from banking.models import WalletModel
from banking.cashback_service import CashbackService
from banking.tasks import post_vas_update, send_alert_notification
from permissions import IsAuthenticatedOrGuestWithValidId
from banking.helpers import Pin, verify_wallet_auth, verify_card_payment
from gamification.models import Points as PointsModel
from gamification.points import TIER_VALUES
from .utility import (
    create_activity,
    create_notification,
    complete_data_purchase,
    # send_token,
    # send_token_to_guest_users,
)

from decouple import config
from .helpers import VAS
from .models import ValueAddedServices, ELECTRICITY_SERVICE_ID_CHOICES
from .token_cache import cache_electricity_token
from commons import Pay, Biometrics
from security import encrypt, decrypt

operational_account = config("CENTRAL_OPERATIONAL_ACCOUNT", default="")
collection_account = config("CENTRAL_COLLECTION_ACCOUNT", default="")

logger = logging.getLogger(__name__)

ELECTRICITY_BILLER_IDS = {choice[0] for choice in ELECTRICITY_SERVICE_ID_CHOICES}


def _bill_payment_category(billerId, has_meter_type=False):
    """Electricity Bill vs Cable TV label for failed/pending BillPaymentView
    purchases, where there's no provider response yet to read "isToken" off
    of (see _handle_success). "meter_type" is an electricity-only field the
    client sends (required to tell prepaid/postpaid apart, see is_postpaid
    below) - Cable TV purchases never carry it - so its presence is a
    reliable signal regardless of billerId naming. Only fall back to
    ELECTRICITY_BILLER_IDS when meter_type is absent: that list is a
    VTPass-style naming guess (e.g. "portharcourt-electric") while this
    middleware's real billerIds are its own short codes (e.g. "BP-PH" for
    Port Harcourt, confirmed from production logs), so that fallback still
    mislabels real electricity billerIds as Cable TV until
    ELECTRICITY_BILLER_IDS is replaced with the real biller codes."""
    if has_meter_type:
        return "Electricity Bill"
    return "Electricity Bill" if billerId in ELECTRICITY_BILLER_IDS else "Cable TV"


def _handle_pending_response(
    user=None,
    tx_reference=None,
    tx_type=None,
    amount=None,
    description="",
    phone=None,
    network=None,
):
    """
    Shared response for a purchase the provider explicitly flagged as still
    processing (e.g. responseCode 202), even after a patient status poll.
    No refund is issued here - 9PSB settles/reverses a pending transaction
    on their side once it resolves. phone/network are stashed on the row so
    the reconciliation sweep (vas/tasks.py) can complete this purchase's
    success side effects without the original request context.
    """
    if user and tx_reference:
        try:
            with transaction.atomic():
                TxModel.objects.update_or_create(
                    tx_reference=tx_reference,
                    defaults={
                        "user": user,
                        "tx_type": tx_type,
                        "amount": amount,
                        "description": description,
                        "status": "PENDING",
                        "phone_number": phone,
                        "network": network,
                    },
                )
        except Exception as e:
            logging.error(f"Database query error: {str(e)}")

    return Response(
        data=encrypt(
            {
                "status": "pending",
                "message": "Your purchase is still processing. You'll be notified once it completes.",
                "receipt": build_receipt(user, tx_reference),
            }
        ),
        status=status.HTTP_202_ACCEPTED,
    )


def _vas_failure_reason(response):
    """Pull the most specific failure reason out of a VAS response body -
    a nested data.description (e.g. "Transaction failed") over the
    envelope's own message, since a status-check response's top-level
    message is often just "Topup transaction status retrieved" (that the
    status query itself worked, not why the purchase failed). Returns None
    if response is missing or unparseable, so callers can fall back to a
    second response (e.g. try the original VAS.data() response - which
    tends to carry the real reason, like "Insufficient balance to cover
    the transaction" - before the less specific status-check response)."""
    if response is None or not hasattr(response, "json"):
        return None
    try:
        body = response.json()
    except Exception:
        return None
    if not isinstance(body, dict):
        return None
    data = body.get("data") if isinstance(body.get("data"), dict) else None
    if isinstance(data, dict) and data.get("description"):
        return data["description"]
    return body.get("message") or None


@extend_schema(
    summary="Purchase airtime for any Nigerian network",
    tags=["VAS"],
    description="Processes an airtime top-up for any Nigerian network (MTN, GLO, Airtel, Etisalat). Supports wallet, points, cashback, and card payment options. Authenticated users must use wallet; guests must use card.",
    request=AirtimeTopupSerializer,
    responses={
        200: inline_serializer(
            name="AirtimeTopupResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
            },
        ),
        400: inline_serializer(
            name="AirtimeTopupError",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class AirTimeTopUp(generics.GenericAPIView):
    """
    Handles POST requests for airtime purchase for service providers in Nigeria.
    """

    serializer_class = AirtimeTopupSerializer
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
                    TxModel.objects.update_or_create(
                        tx_reference=tx_reference,
                        defaults={
                            "user": user,
                            "tx_type": "Airtime",
                            "amount": amount,
                            "description": title,
                            "status": "SUCCESS",
                            "phone_number": phone,
                            "network": network,
                            "is_task": self.is_task,
                            "task_id": self.task_id,
                        },
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

        response_data["receipt"] = build_receipt(user, tx_reference)
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
        tx_reference=None,
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
            if tx_reference:
                try:
                    with transaction.atomic():
                        TxModel.objects.update_or_create(
                            tx_reference=tx_reference,
                            defaults={
                                "user": user,
                                "tx_type": "Airtime",
                                "amount": amount,
                                "description": title,
                                "status": "FAILED",
                            },
                        )
                except Exception as e:
                    logging.error(f"Database query error: {str(e)}")
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

        if airtime_response is not None:
            if hasattr(airtime_response, "text"):
                try:
                    error_detail = airtime_response.json().get(
                        "message", airtime_response.text
                    )
                except ValueError:
                    error_detail = airtime_response.text
            else:
                error_detail = str(airtime_response)
        else:
            error_detail = {}

        response_data = {
            "status": "fail",
            "message": f"Airtime purchase failed. {reason}",
            "error": error_detail,
        }

        return Response(data=encrypt(response_data), status=status.HTTP_400_BAD_REQUEST)

    # Main POST Method
    def post(self, request):
        decrypted_payload = decrypt(request.data)
        user_data = {
            k: v.strip() if isinstance(v, str) else v
            for k, v in decrypted_payload.items()
        }
        self.is_task = bool(user_data.get("is_task"))
        self.task_id = user_data.get("task_id")

        user = request.user if request.user.is_authenticated else None
        guest_id = request.headers.get("X-Guest-ID")
        idempotency_key = request.headers.get("Idempotency-Key")

        # Idempotency: check if this request was already processed.
        # Only short-circuit on a confirmed outcome - a PENDING row means the
        # last attempt never resolved, and a FAILED row means it's safe to
        # retry, so both fall through to reprocess rather than lying about
        # the outcome.
        if user and idempotency_key:
            existing_tx = TxModel.objects.filter(
                user=user, tx_reference=idempotency_key
            ).first()
            if existing_tx and existing_tx.status == "SUCCESS":
                logger.info(
                    f"Idempotent request detected for {user.id} with key {idempotency_key}"
                )
                response_data = {
                    "status": "success",
                    "message": "This request was already processed.",
                    "tx_reference": idempotency_key,
                    "receipt": build_receipt(user, idempotency_key),
                }
                return Response(data=encrypt(response_data), status=status.HTTP_200_OK)
            if existing_tx and existing_tx.status == "PENDING":
                logger.info(
                    f"Idempotent request for {user.id} with key {idempotency_key} is still pending"
                )
                return _handle_pending_response()

        tx_reference = (
            idempotency_key if idempotency_key else VAS.generate_unique_code("PICA")
        )

        # Extract fields
        pin = user_data.get("pin")
        payment_option = user_data.get("payment_option")
        card_reference = user_data.get("card_reference")
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
        elif payment_option == "CARD":
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "Card payment is not available for authenticated users.",
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
                    user_wallet = WalletModel.objects.select_for_update().get(
                        user=user, walletType="INDIVIDUAL"
                    )
                elif user:
                    user_wallet = WalletModel.objects.filter(
                        user=user, walletType="INDIVIDUAL"
                    ).first()

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
                            avail_pts = pts_obj.balance * TIER_VALUES.get(
                                pts_obj.tier, Decimal("0")
                            )
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
                        pts_used = Decimal(str(remaining))

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
                    if not use_points and not use_cashback:
                        token = VAS.authenticate()
                        if not token:
                            return self._handle_airtime_failure(
                                tx_reference=tx_reference,
                                user=user,
                                phone=phone,
                                amount=amount,
                                reason="VAS authentication failed.",
                            )
                        airtime_response = VAS.airtime_topup(
                            network=network,
                            bearer_token=token,
                            amount=amount,
                            debitAccount=account_number,
                            phone_number=phone,
                            tx_ref=tx_reference,
                        )
                        if airtime_response is None:
                            status_resp = VAS.confirm_status(
                                tx_ref=tx_reference, bearer_token=token
                            )
                            if status_resp and VAS.is_success(status_resp):
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
                                tx_reference=tx_reference,
                                user=user,
                                phone=phone,
                                amount=amount,
                                reason="VAS service unavailable.",
                            )
                        if VAS.is_success(airtime_response):
                            return self._handle_airtime_success(
                                user=user,
                                phone=phone,
                                amount=amount,
                                network=network,
                                tx_reference=tx_reference,
                                cashback=cashback_used,
                                account_number=account_number,
                            )
                        # Fallback: confirm via status check
                        status_resp, outcome = VAS.resolve_outcome(
                            airtime_response, tx_reference, token
                        )
                        if outcome == "success":
                            return self._handle_airtime_success(
                                user=user,
                                phone=phone,
                                amount=amount,
                                network=network,
                                tx_reference=tx_reference,
                                cashback=cashback_used,
                                account_number=account_number,
                            )
                        if outcome == "pending":
                            return _handle_pending_response(
                                user=user,
                                tx_reference=tx_reference,
                                tx_type="Airtime",
                                amount=amount,
                                description="Airtime purchase pending.",
                            )
                        return self._handle_airtime_failure(
                            tx_reference=tx_reference,
                            user=user,
                            phone=phone,
                            amount=amount,
                            airtime_response=status_resp,
                            reason="Airtime top-up failed.",
                        )

                    # Hybrid: cashback/points cover full purchase
                    token = VAS.authenticate()
                    if not token:
                        if cashback_used:
                            CashbackService.refund_cashback(
                                user=user, cashback_amount=cashback_used
                            )
                        if pts_used:
                            Pay.refund_pts(user=user, naira_amount=pts_used)
                        return self._handle_airtime_failure(
                            tx_reference=tx_reference,
                            user=user,
                            phone=phone,
                            amount=purchase_amount,
                            reason="VAS authentication failed.",
                        )
                    airtime_response = VAS.airtime_topup(
                        network=network,
                        bearer_token=token,
                        amount=purchase_amount,
                        debitAccount=collection_account,
                        phone_number=phone,
                        tx_ref=tx_reference,
                    )
                    if airtime_response is None:
                        status_resp = VAS.confirm_status(
                            tx_ref=tx_reference, bearer_token=token
                        )
                        if status_resp and VAS.is_success(status_resp):
                            return self._handle_airtime_success(
                                user=user,
                                phone=phone,
                                amount=purchase_amount,
                                network=network,
                                tx_reference=tx_reference,
                                cashback=cashback_used,
                                account_number=account_number,
                            )
                        if cashback_used:
                            CashbackService.refund_cashback(
                                user=user, cashback_amount=cashback_used
                            )
                        if pts_used:
                            Pay.refund_pts(user=user, naira_amount=pts_used)
                        return self._handle_airtime_failure(
                            tx_reference=tx_reference,
                            user=user,
                            phone=phone,
                            amount=purchase_amount,
                            reason="VAS service unavailable.",
                        )
                    if VAS.is_success(airtime_response):
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
                        status_resp, outcome = VAS.resolve_outcome(
                            airtime_response, tx_reference, token
                        )
                        if outcome == "success":
                            return self._handle_airtime_success(
                                user=user,
                                phone=phone,
                                amount=purchase_amount,
                                network=network,
                                tx_reference=tx_reference,
                                cashback=cashback_used,
                                account_number=account_number,
                            )
                        if outcome == "pending":
                            return _handle_pending_response(
                                user=user,
                                tx_reference=tx_reference,
                                tx_type="Airtime",
                                amount=purchase_amount,
                                description="Airtime purchase pending.",
                            )
                        if cashback_used:
                            CashbackService.refund_cashback(
                                user=user, cashback_amount=cashback_used
                            )
                        if pts_used:
                            Pay.refund_pts(user=user, naira_amount=pts_used)
                        return self._handle_airtime_failure(
                            tx_reference=tx_reference,
                            user=user,
                            phone=phone,
                            amount=purchase_amount,
                            airtime_response=status_resp,
                            reason="Airtime top-up failed.",
                        )

                case "CARD":
                    funding, card_error_response = verify_card_payment(
                        card_reference, amount, user
                    )
                    if card_error_response is not None:
                        return card_error_response

                    token = VAS.authenticate()
                    if not token:
                        return self._handle_airtime_failure(
                            tx_reference=tx_reference,
                            user=user,
                            guest_id=guest_id,
                            phone=phone,
                            amount=amount,
                            reason="VAS authentication failed.",
                        )
                    airtime_response = VAS.airtime_topup(
                        network=network,
                        bearer_token=token,
                        amount=amount,
                        debitAccount=collection_account,
                        phone_number=phone,
                        tx_ref=tx_reference,
                    )
                    if airtime_response is None:
                        status_resp = VAS.confirm_status(
                            tx_ref=tx_reference, bearer_token=token
                        )
                        if status_resp and VAS.is_success(status_resp):
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
                            tx_reference=tx_reference,
                            user=user,
                            guest_id=guest_id,
                            phone=phone,
                            amount=amount,
                            reason="VAS service unavailable.",
                        )
                    if VAS.is_success(airtime_response):
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
                    status_resp, outcome = VAS.resolve_outcome(
                        airtime_response, tx_reference, token
                    )
                    if outcome == "success":
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
                    if outcome == "pending":
                        return _handle_pending_response(
                            user=user,
                            tx_reference=tx_reference,
                            tx_type="Airtime",
                            amount=amount,
                            description="Airtime purchase pending.",
                        )
                    return self._handle_airtime_failure(
                        tx_reference=tx_reference,
                        user=user,
                        guest_id=guest_id,
                        phone=phone,
                        amount=amount,
                        airtime_response=status_resp,
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
    tags=["VAS"],
    description="Retrieve available data bundle plans for a network provider. Pass the network name as a path parameter (e.g. mtn, glo, airtel, etisalat).",
    responses={
        200: inline_serializer(
            name="GetDataPlansResponse",
            fields={
                "status": s.CharField(),
                "data": s.DictField(),
            },
        ),
        400: OpenApiResponse(description="Invalid network provided"),
        502: OpenApiResponse(description="Failed to fetch data plans from provider"),
    },
)
class GetDataPlans(generics.RetrieveAPIView):
    serializer_class = VasStatusSerializer

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

        token = VAS.authenticate()
        if not token:
            return Response(
                data=encrypt(
                    {"status": "fail", "message": "VAS authentication failed."}
                ),
                status=status.HTTP_502_BAD_GATEWAY,
            )
        vas_response = VAS.dataplans(bearer_token=token, phone_number=network)
        if not vas_response or not VAS.is_success(vas_response):
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


@extend_schema(
    summary="Subscribe to a mobile data bundle",
    tags=["VAS"],
    description="Purchases a mobile data bundle for any Nigerian network. Supports wallet, cashback, points, and card payment options. Authenticated users must use wallet; guests must use card.",
    request=DataSubscriptionSerializer,
    responses={
        200: inline_serializer(
            name="DataSubscriptionResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        400: inline_serializer(
            name="DataSubscriptionError",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class DataSubscriptionView(generics.GenericAPIView):
    """
    DataSubscriptionView is a POST request handler for data
    subscription.
    """

    serializer_class = DataSubscriptionSerializer
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
        }

        title = "Data purchase"

        if user:
            complete_data_purchase(
                user=user,
                tx_reference=tx_reference,
                amount=amount,
                phone=phone,
                network=network,
                account_number=account_number,
                is_task=self.is_task,
                task_id=self.task_id,
            )
            if cashback is not None:
                response_data["cashback_used"] = str(cashback)
        else:
            description = (
                f"Guest has made a purchase of {amount} naira data on {phone}."
            )
            create_activity(guest_id=guest_id, title=title, description=description)

        response_data["receipt"] = build_receipt(user, tx_reference)
        return Response(data=encrypt(response_data), status=status.HTTP_200_OK)

    # Private Helper: Failure
    def _handle_data_failure(
        self,
        user=None,
        guest_id=None,
        phone=None,
        amount=None,
        data_response=None,
        error_detail=None,
        reason="",
        tx_reference=None,
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
            if tx_reference:
                try:
                    with transaction.atomic():
                        TxModel.objects.update_or_create(
                            tx_reference=tx_reference,
                            defaults={
                                "user": user,
                                "tx_type": "Data",
                                "amount": amount,
                                "description": title,
                                "status": "FAILED",
                            },
                        )
                except Exception as e:
                    logger.error(f"Database query error: {str(e)}")
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

        if error_detail is None:
            if data_response is not None:
                if hasattr(data_response, "data"):
                    error_detail = data_response.data
                elif hasattr(data_response, "text"):
                    try:
                        error_detail = data_response.json().get(
                            "message", data_response.text
                        )
                    except ValueError:
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
        self.is_task = bool(user_data.get("is_task"))
        self.task_id = user_data.get("task_id")

        user = request.user if request.user.is_authenticated else None
        guest_id = request.headers.get("X-Guest-ID")
        idempotency_key = request.headers.get("Idempotency-Key")

        # Idempotency: check if this request was already processed.
        # Only short-circuit on a confirmed outcome - a PENDING row means the
        # last attempt never resolved, and a FAILED row means it's safe to
        # retry, so both fall through to reprocess rather than lying about
        # the outcome.
        if user and idempotency_key:
            existing_tx = TxModel.objects.filter(
                user=user, tx_reference=idempotency_key
            ).first()
            if existing_tx and existing_tx.status == "SUCCESS":
                logger.info(
                    f"Idempotent request detected for {user.id} with key {idempotency_key}"
                )
                response_data = {
                    "status": "success",
                    "message": "This request was already processed.",
                    "tx_reference": idempotency_key,
                    "receipt": build_receipt(user, idempotency_key),
                }
                return Response(data=encrypt(response_data), status=status.HTTP_200_OK)
            if existing_tx and existing_tx.status == "PENDING":
                logger.info(
                    f"Idempotent request for {user.id} with key {idempotency_key} is still pending"
                )
                return _handle_pending_response()

        pin = user_data.get("pin")
        amount = user_data.get("amount")
        phone = user_data.get("phone_number")
        use_points = user_data.get("use_points")
        payment_option = user_data.get("payment_option")
        card_reference = user_data.get("card_reference")
        network = user_data.get("network")
        product_id = user_data.get("product_id")
        biometrics = user_data.get("use_biometrics")
        use_cashback = user_data.get("use_cashback")

        cashback_used = Decimal("0")
        pts_used = Decimal("0")

        tx_reference = (
            idempotency_key if idempotency_key else VAS.generate_unique_code("PICA")
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
        elif payment_option == "CARD":
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "Card payment is not available for authenticated users.",
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = self.serializer_class(data=user_data)
        serializer.is_valid(raise_exception=True)

        account_number = ""
        if payment_option != "CARD":
            try:
                account = WalletModel.objects.get(user=user, walletType="INDIVIDUAL")
                account_number = account.account_number
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

        if (use_cashback or use_points) and payment_option == "WALLET" and user:
            avail_cashback = Decimal("0")
            if use_cashback:
                try:
                    w = WalletModel.objects.get(user=user, walletType="INDIVIDUAL")
                    avail_cashback = w.cashback_balance
                except WalletModel.DoesNotExist:
                    pass
            avail_pts = Decimal("0")
            if use_points:
                try:
                    from gamification.models import Points as PointsModel

                    pts_obj = PointsModel.objects.get(user=user)
                    avail_pts = pts_obj.balance * TIER_VALUES.get(
                        pts_obj.tier, Decimal("0")
                    )
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
                pts_used = Decimal(str(remaining))

        match payment_option:
            case "WALLET":
                if not use_points and not use_cashback:
                    token = VAS.authenticate()
                    if not token:
                        return self._handle_data_failure(
                            tx_reference=tx_reference,
                            user=user,
                            phone=phone,
                            amount=amount,
                            reason="VAS authentication failed.",
                        )
                    data_response = VAS.data(
                        network=network,
                        bearer_token=token,
                        amount=amount,
                        productId=product_id,
                        debitAccount=account_number,
                        phone_number=phone,
                        tx_ref=tx_reference,
                    )
                    if data_response is None:
                        status_resp = VAS.confirm_status(
                            tx_ref=tx_reference, bearer_token=token
                        )
                        if status_resp and VAS.is_success(status_resp):
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
                            tx_reference=tx_reference,
                            user=user,
                            phone=phone,
                            amount=amount,
                            reason="VAS service unavailable.",
                        )
                    if VAS.is_success(data_response):
                        return self._handle_data_success(
                            user=user,
                            phone=phone,
                            productId=product_id,
                            amount=amount,
                            network=network,
                            tx_reference=tx_reference,
                            cashback=cashback_used,
                        )
                    # Fallback: confirm via status check
                    status_resp, outcome = VAS.resolve_outcome(
                        data_response, tx_reference, token
                    )
                    if outcome == "success":
                        return self._handle_data_success(
                            user=user,
                            phone=phone,
                            productId=product_id,
                            amount=amount,
                            network=network,
                            tx_reference=tx_reference,
                            cashback=cashback_used,
                        )
                    if outcome == "pending":
                        return _handle_pending_response(
                            user=user,
                            tx_reference=tx_reference,
                            tx_type="Data",
                            amount=amount,
                            description="Data purchase pending.",
                            phone=phone,
                            network=network,
                        )
                    return self._handle_data_failure(
                        tx_reference=tx_reference,
                        user=user,
                        phone=phone,
                        amount=amount,
                        data_response=status_resp,
                        error_detail=_vas_failure_reason(data_response)
                        or _vas_failure_reason(status_resp),
                        reason="Data subscription failed.",
                    )

                # Hybrid: cashback/points cover full purchase
                token = VAS.authenticate()
                if not token:
                    if cashback_used:
                        CashbackService.refund_cashback(
                            user=user, cashback_amount=cashback_used
                        )
                    if pts_used:
                        Pay.refund_pts(user=user, naira_amount=pts_used)
                    return self._handle_data_failure(
                        tx_reference=tx_reference,
                        user=user,
                        phone=phone,
                        amount=purchase_amount,
                        reason="VAS authentication failed.",
                    )
                data_response = VAS.data(
                    network=network,
                    bearer_token=token,
                    amount=purchase_amount,
                    productId=product_id,
                    debitAccount=collection_account,
                    phone_number=phone,
                    tx_ref=tx_reference,
                )
                if data_response is None:
                    status_resp = VAS.confirm_status(
                        tx_ref=tx_reference, bearer_token=token
                    )
                    if status_resp and VAS.is_success(status_resp):
                        return self._handle_data_success(
                            user=user,
                            phone=phone,
                            productId=product_id,
                            amount=purchase_amount,
                            network=network,
                            tx_reference=tx_reference,
                            cashback=cashback_used,
                        )
                    if cashback_used:
                        CashbackService.refund_cashback(
                            user=user, cashback_amount=cashback_used
                        )
                    if pts_used:
                        Pay.refund_pts(user=user, naira_amount=pts_used)
                    return self._handle_data_failure(
                        tx_reference=tx_reference,
                        user=user,
                        phone=phone,
                        amount=purchase_amount,
                        reason="VAS service unavailable.",
                    )
                if VAS.is_success(data_response):
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
                    status_resp, outcome = VAS.resolve_outcome(
                        data_response, tx_reference, token
                    )
                    if outcome == "success":
                        return self._handle_data_success(
                            user=user,
                            phone=phone,
                            productId=product_id,
                            amount=purchase_amount,
                            network=network,
                            tx_reference=tx_reference,
                            cashback=cashback_used,
                        )
                    if outcome == "pending":
                        return _handle_pending_response(
                            user=user,
                            tx_reference=tx_reference,
                            tx_type="Data",
                            amount=purchase_amount,
                            description="Data purchase pending.",
                            phone=phone,
                            network=network,
                        )
                    if cashback_used:
                        CashbackService.refund_cashback(
                            user=user, cashback_amount=cashback_used
                        )
                    if pts_used:
                        Pay.refund_pts(user=user, naira_amount=pts_used)
                    return self._handle_data_failure(
                        tx_reference=tx_reference,
                        user=user,
                        phone=phone,
                        amount=purchase_amount,
                        data_response=status_resp,
                        error_detail=_vas_failure_reason(data_response)
                        or _vas_failure_reason(status_resp),
                        reason="Data subscription failed.",
                    )

            # case "TREASURY": disabled — treasury VAS payments on hold
            case "CARD":
                funding, card_error_response = verify_card_payment(
                    card_reference, amount, user
                )
                if card_error_response is not None:
                    return card_error_response

                token = VAS.authenticate()
                if not token:
                    return self._handle_data_failure(
                        tx_reference=tx_reference,
                        user=user,
                        guest_id=guest_id,
                        phone=phone,
                        amount=amount,
                        reason="VAS authentication failed.",
                    )
                data_response = VAS.data(
                    network=network,
                    bearer_token=token,
                    amount=amount,
                    productId=product_id,
                    phone_number=phone,
                    tx_ref=tx_reference,
                )
                if data_response is None:
                    status_resp = VAS.confirm_status(
                        tx_ref=tx_reference, bearer_token=token
                    )
                    if status_resp and VAS.is_success(status_resp):
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
                        tx_reference=tx_reference,
                        user=user,
                        guest_id=guest_id,
                        phone=phone,
                        amount=amount,
                        reason="VAS service unavailable.",
                    )
                if VAS.is_success(data_response):
                    return self._handle_data_success(
                        user=user,
                        guest_id=guest_id,
                        phone=phone,
                        productId=product_id,
                        amount=amount,
                        network=network,
                        tx_reference=tx_reference,
                    )
                status_resp, outcome = VAS.resolve_outcome(
                    data_response, tx_reference, token
                )
                if outcome == "success":
                    return self._handle_data_success(
                        user=user,
                        guest_id=guest_id,
                        phone=phone,
                        productId=product_id,
                        amount=amount,
                        network=network,
                        tx_reference=tx_reference,
                    )
                if outcome == "pending":
                    return _handle_pending_response(
                        user=user,
                        tx_reference=tx_reference,
                        tx_type="Data",
                        amount=amount,
                        description="Data purchase pending.",
                        phone=phone,
                        network=network,
                    )
                return self._handle_data_failure(
                    tx_reference=tx_reference,
                    user=user,
                    guest_id=guest_id,
                    phone=phone,
                    amount=amount,
                    data_response=status_resp,
                    error_detail=_vas_failure_reason(data_response)
                    or _vas_failure_reason(status_resp),
                    reason="Data subscription failed.",
                )

            case _:
                return Response(
                    data=encrypt(
                        {"status": "fail", "message": "Invalid payment option"}
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )


@extend_schema(
    summary="Get service variations for a given VAS serviceID",
    tags=["VAS"],
    description="Returns the available service variations (packages/plans) for a given VAS service ID. Pass the serviceID as a query parameter (e.g. dstv, gotv).",
    parameters=[
        OpenApiParameter(
            name="serviceID",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            description="VAS service ID (e.g. dstv, gotv, startimes)",
        ),
    ],
    responses={
        200: inline_serializer(
            name="GetPaymentCategoriesResponse",
            fields={"status": s.CharField(), "data": s.DictField()},
        ),
        400: inline_serializer(
            name="GetPaymentCategoriesError",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        502: inline_serializer(
            name="GetPaymentCategoriesGatewayError",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
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
        token = VAS.authenticate()
        if not token:
            return Response(
                data=encrypt(
                    {"status": "fail", "message": "VAS authentication failed."}
                ),
                status=status.HTTP_502_BAD_GATEWAY,
            )
        variations_resp = VAS.get_categories(bearer_token=token)
        if not variations_resp or not VAS.is_success(variations_resp):
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
                    "data": variations_resp.json(),
                }
            ),
            status=status.HTTP_200_OK,
        )


@extend_schema(
    summary="Get bill payment categories for a serviceID",
    tags=["VAS"],
    description="Returns the available bill payment categories for a given category ID. Can be passed as a URL path parameter or query parameter.",
    parameters=[
        OpenApiParameter(
            name="category_id",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            description="Bill payment category ID",
        ),
    ],
    responses={
        200: inline_serializer(
            name="BillPaymentCategoriesResponse",
            fields={"status": s.CharField(), "data": s.DictField()},
        ),
        400: inline_serializer(
            name="BillPaymentCategoriesError",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        502: inline_serializer(
            name="BillPaymentCategoriesGatewayError",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class BillPaymentCategoriesView(APIView):
    """
    Returns bill payment categories for a given category ID.
    """

    def get(self, request, *args, **kwargs):
        category_id = kwargs.get("category_id") or request.query_params.get(
            "category_id"
        )
        if not category_id:
            return Response(
                data=encrypt({"status": "fail", "message": "category_id is required."}),
                status=status.HTTP_400_BAD_REQUEST,
            )
        token = VAS.authenticate()
        if not token:
            return Response(
                data=encrypt(
                    {"status": "fail", "message": "VAS authentication failed."}
                ),
                status=status.HTTP_502_BAD_GATEWAY,
            )
        variations_resp = VAS.bill_payment_categories(
            bearer_token=token, category_id=category_id
        )
        if not variations_resp or not VAS.is_success(variations_resp):
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
                    "data": variations_resp.json(),
                }
            ),
            status=status.HTTP_200_OK,
        )


@extend_schema(
    summary="Get biller fields for a biller ID",
    tags=["VAS"],
    description="Returns the required fields and items for a specific biller ID (e.g. electricity distributor or cable provider).",
    parameters=[
        OpenApiParameter(
            name="billers_id",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.PATH,
            description="Biller ID (e.g. ikeja-electric, dstv)",
        ),
    ],
    responses={
        200: inline_serializer(
            name="BillersCategoriesResponse",
            fields={"status": s.CharField(), "data": s.DictField()},
        ),
        400: inline_serializer(
            name="BillersCategoriesError",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        502: inline_serializer(
            name="BillersCategoriesGatewayError",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class BillersCategoriesView(APIView):
    """
    Returns fields/items for a specific biller ID.
    """

    def get(self, request, *args, **kwargs):
        biller_id = kwargs.get("billers_id") or request.query_params.get("biller_id")
        if not biller_id:
            return Response(
                data=encrypt({"status": "fail", "message": "biller_id is required."}),
                status=status.HTTP_400_BAD_REQUEST,
            )
        token = VAS.authenticate()
        if not token:
            return Response(
                data=encrypt(
                    {"status": "fail", "message": "VAS authentication failed."}
                ),
                status=status.HTTP_502_BAD_GATEWAY,
            )
        variations_resp = VAS.billers_categories(
            bearer_token=token, biller_id=biller_id
        )
        if not variations_resp or not VAS.is_success(variations_resp):
            return Response(
                data=encrypt(
                    {"status": "fail", "message": "Failed to retrieve biller fields."}
                ),
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(
            data=encrypt(
                {
                    "status": "success",
                    "message": "Biller fields retrieved successfully.",
                    "data": variations_resp.json(),
                }
            ),
            status=status.HTTP_200_OK,
        )


@extend_schema(
    summary="Verify a biller account (meter number or smart card)",
    tags=["VAS"],
    description="Verifies a meter number (electricity) or smart card/IUC number (cable TV) against the VAS provider. Returns the customer name and details on success.",
    request=VerifyBillerSerializer,
    responses={
        200: inline_serializer(
            name="VerifyBillerResponse",
            fields={"status": s.CharField(), "data": s.DictField()},
        ),
        400: inline_serializer(
            name="VerifyBillerError",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        502: inline_serializer(
            name="VerifyBillerGatewayError",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
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

        if request.user.is_authenticated:
            requester = f"{request.user.first_name} {request.user.last_name}"
        else:
            requester = f"guest {request.headers.get('X-Guest-ID')}"

        logger.info(
            f"User {requester} is attempting to verify biller account with data: {user_data}"
        )

        # billerId maps to VTPass serviceID (e.g. ikeja-electric, dstv)
        # customerId maps to VTPass billersCode (meter / IUC number)
        service_id = user_data.get("billerId")
        billers_code = user_data.get("customerId")
        item_id = user_data.get("itemId") or user_data.get("meter_type")
        amount = user_data.get("amount", 0)

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
            token = VAS.authenticate()
            if not token:
                return Response(
                    data=encrypt(
                        {"status": "fail", "message": "VAS authentication failed."}
                    ),
                    status=status.HTTP_502_BAD_GATEWAY,
                )

            verify_resp = VAS.verify_bill_payer(
                bearer_token=token,
                billerId=service_id,
                customerId=billers_code,
                itemId=item_id,
                amount=amount,
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

            if VAS.is_success(verify_resp):
                verify_json = verify_resp.json()
                verify_data = (
                    verify_json.get("data", {}) if isinstance(verify_json, dict) else {}
                )
                address = None
                other_field = (
                    verify_data.get("otherField")
                    if isinstance(verify_data, dict)
                    else None
                ) or ""
                if isinstance(other_field, str) and other_field.lower().startswith(
                    "address:"
                ):
                    address = other_field.split(":", 1)[1].strip()

                response_data = {"status": "success", "data": verify_json}
                if address:
                    response_data["address"] = address
                logger.info(
                    f"Biller verification successful for {requester}: {response_data}"
                )
                return Response(data=encrypt(response_data), status=status.HTTP_200_OK)
            else:
                biller_response = verify_resp.json()
                logger.warning(
                    f"Biller verification failed for {requester}: {biller_response}"
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
                f"RequestException for {requester}: {str(e)}",
                exc_info=True,
            )
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "Service request failed. Please try again.",
                    }
                ),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


@extend_schema(
    summary="Pay electricity or cable TV bill",
    tags=["VAS"],
    description="Processes an electricity prepaid token purchase or cable TV subscription. Service type is detected automatically: responses with a token field indicate electricity. Supports wallet, points, and card payment options.",
    request=BillPaymentSerializer,
    responses={
        200: inline_serializer(
            name="BillPaymentResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "token_details": s.CharField(required=False),
                "units_bought": s.CharField(required=False),
            },
        ),
        400: inline_serializer(
            name="BillPaymentError",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class BillPaymentView(generics.GenericAPIView):
    """
    Unified BillPaymentView for both Electricity and Cable subscriptions.
    Service type is detected from VTPass response: if response content includes
    a 'token' field, the service is Electricity. Otherwise it's Cable.
    """

    serializer_class = BillPaymentSerializer
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
        address=None,
        is_postpaid=False,
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

        # VTPass: {"code": "000", "content": {"transactions": {...}}}
        # 9PSB:   {"status": "success", "data": {...}}
        if isinstance(vas_json, dict) and "content" in vas_json:
            vas_content = vas_json.get("content", {})
            vas_data = vas_content.get("transactions", vas_content)
        else:
            vas_data = vas_json.get("data", {}) if isinstance(vas_json, dict) else {}

        # Determine if electricity. Prefer the provider's own "isToken" flag
        # (present on a direct pay response, e.g.
        # {"otherField": "Units: 4.2", "isToken": True, "token": "Token: ..."})
        # - this is authoritative and doesn't depend on billerId naming.
        # billerId is NOT a reliable fallback here: ELECTRICITY_BILLER_IDS
        # (vas/models.py) is a VTPass-style naming guess (e.g.
        # "portharcourt-electric"), but this middleware actually sends its
        # own short codes (e.g. "BP-PH" for Port Harcourt, confirmed from
        # production VAS logs) - so that membership check was always false
        # for real production billerIds, silently mislabeling every
        # electricity purchase as Cable TV. Only fall back to it when
        # "isToken" is genuinely absent - e.g. the shared topup status
        # endpoint (VAS.resolve_outcome -> VAS.status) used when settlement
        # lags, which carries neither "isToken" nor "token" regardless of
        # service type.
        token = vas_data.get("token") if isinstance(vas_data, dict) else None
        if isinstance(vas_data, dict) and "isToken" in vas_data:
            is_electricity = bool(vas_data.get("isToken"))
        else:
            is_electricity = billerId in ELECTRICITY_BILLER_IDS

        # The provider embeds a literal "Token: " prefix inside the token
        # string itself (see the log above) - strip it so
        # response/SMS/email don't double up ("token is: Token: 1234...").
        if token and isinstance(token, str) and token.startswith("Token:"):
            token = token.split(":", 1)[1].strip()

        # For missing tokens in the case of postpaidelectricity,
        # the provider returns a literal string "null"
        # (not JSON null) - treat that as missing.
        token_missing_after_debit = False
        if token and isinstance(token, str) and token.strip().lower() == "null":
            token_missing_after_debit = True
            token = None

        # Units bought come back under "otherField" (e.g. "Units: 4.2"), not
        # a "units" key - vas_data.get("units", "") was reading a key this
        # provider never sends, so units_bought (and the email below) were
        # always blank. Fall back to "units" too in case another provider
        # shape does use that key.
        units = vas_data.get("units") if isinstance(vas_data, dict) else None
        if not units and isinstance(vas_data, dict):
            other_field = vas_data.get("otherField") or ""
            if isinstance(other_field, str) and other_field.lower().startswith(
                "units:"
            ):
                units = other_field.split(":", 1)[1].strip()
        units = units or ""

        response_data = {
            "status": "success",
            "message": f"Purchase of {amount} was successful.",
        }

        if is_electricity:
            response_data["token_details"] = token
            response_data["units_bought"] = units
            response_data["customer_name"] = customerName

        response_data["service_response"] = vas_data

        title = "Electricity Bill" if is_electricity else "Cable TV"
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
                    TxModel.objects.update_or_create(
                        tx_reference=tx_reference,
                        defaults={
                            "user": user,
                            "tx_type": "Bill Payment",
                            "amount": amount,
                            "description": title,
                            "status": "SUCCESS",
                            "is_task": self.is_task,
                            "task_id": self.task_id,
                            "address": address,
                            "customer_name": customerName,
                            "meter_type": (
                                ("postpaid" if is_postpaid else "prepaid")
                                if is_electricity
                                else None
                            ),
                        },
                    )
            except Exception as e:
                logger.error(f"TxModel creation error: {str(e)}")
            try:
                with transaction.atomic():
                    ValueAddedServices.objects.create(
                        user=user if user else None,
                        guest_id=guest_id if not user else None,
                        tx_reference=tx_reference,
                        customerId=customerId,
                        billerId=billerId,
                        itemId=itemId,
                        amount=amount,
                        phone_number=phone_number,
                        customerName=customerName,
                        otherField=otherField,
                    )
            except Exception as e:
                logger.error(f"ValueAddedServices creation error: {str(e)}")
        else:
            create_activity(guest_id=guest_id, title=title, description=description)

        # Non-permanent token store: cached against tx_reference (TTL, no DB
        # column) so RetrieveTransaction can re-surface it for a while after
        # the SMS/email. Runs for guests too. See vas/token_cache.py.
        if is_electricity and token:
            cache_electricity_token(tx_reference, token, units)

        response_data["receipt"] = build_receipt(user, tx_reference)

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
            sms_msg = f"Your electricity token is: {token}"
            if customerName:
                sms_msg += f" | Name: {customerName}"
            if units:
                sms_msg += f" | Units: {units}"
            sms_msg += f" | Ref: {tx_reference}"

            from django.template.loader import render_to_string

            email_body = render_to_string(
                "picadailys_email.html",
                {
                    "title": "Electricity Token",
                    "rows": [
                        {"label": "Token", "value": token},
                        {"label": "Name", "value": customerName or ""},
                        {"label": "Units", "value": units or "N/A"},
                        {"label": "Amount", "value": f"₦{float(amount):,.2f}"},
                        {"label": "Meter Number", "value": customerId or ""},
                        {"label": "Reference", "value": tx_reference},
                    ],
                    "support_email": "notifications@picadailys.com",
                    "picadailys_phone": "02012271894 02012271895",
                },
            )
            # Backgrounded - see send_alert_notification's docstring
            # (banking/tasks.py). This used to send the token SMS/email
            # inline here before responding, with no timeout on the
            # outbound HTTP call - a slow notification gateway could hang
            # the purchase response even though the token was already
            # resolved above.
            send_alert_notification.delay(
                phone_number=getattr(user, "phone_number", None),
                email=getattr(user, "email", None),
                alert_type=alert_type,
                sms_msg=sms_msg,
                email_subject="Your Electricity Token",
                email_body=sms_msg,
                html_content=email_body,
            )

        # 9PSB confirmed the debit but never issued a real token (see the
        # "Token: null" guard above). Postpaid electricity is a straight
        # bill payment - no token is ever issued, so a null token there is
        # expected, not an incident (confirmed after PICA-92769646948278
        # turned out to be postpaid, not a real loss - 9PSB's own
        # "isToken" flag was true regardless, so it can't be trusted to
        # tell prepaid/postpaid apart; is_postpaid has to come from the
        # client's own item selection instead). Only prepaid gets flagged:
        # there, the customer's money moved with nothing to show for it
        # and we have no automated way to regenerate a token from here.
        if is_electricity and token_missing_after_debit and not is_postpaid:
            logger.error(
                "Electricity purchase debited with no token issued: "
                "tx_reference=%s customerId=%s billerId=%s amount=%s user=%s",
                tx_reference,
                customerId,
                billerId,
                amount,
                getattr(user, "email", None) or guest_id,
            )
            ops_body = (
                f"Electricity purchase debited but 9PSB returned no token.\n\n"
                f"Reference: {tx_reference}\n"
                f"Meter/customerId: {customerId}\n"
                f"BillerId: {billerId}\n"
                f"Amount: NGN {amount}\n"
                f"Customer: {getattr(user, 'email', None) or guest_id}\n\n"
                f"Please follow up with 9PSB to reissue the token or refund the customer."
            )
            send_alert_notification.delay(
                email="support@picadailys.com",
                alert_type="Email",
                email_subject=f"[ACTION NEEDED] Electricity token missing - {tx_reference}",
                email_body=ops_body,
                html_content=f"<pre>{ops_body}</pre>",
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
        tx_reference=None,
        billerId=None,
        has_meter_type=False,
    ):
        """Central failure handler for both Electricity and Cable payment failures."""
        if vas_response is not None:
            if hasattr(vas_response, "text"):
                try:
                    error_detail = vas_response.json().get("message", vas_response.text)
                except ValueError:
                    error_detail = vas_response.text
            else:
                error_detail = vas_response
        else:
            error_detail = {}

        title = f"Failed {_bill_payment_category(billerId, has_meter_type)}"
        message = f"Bill payment of {amount} on {phone_number} failed."
        description = (
            f"{user.first_name if user else 'Guest'} {user.last_name if user else ''} "
            f"failed to make a payment of {amount} for {reason}"
        )

        if user:
            create_notification(user=user, title=title, message=message)
            create_activity(user=user, title=title, description=description)
            if tx_reference:
                try:
                    with transaction.atomic():
                        TxModel.objects.update_or_create(
                            tx_reference=tx_reference,
                            defaults={
                                "user": user,
                                "tx_type": "Bill Payment",
                                "amount": amount,
                                "description": title,
                                "status": "FAILED",
                            },
                        )
                except Exception as e:
                    logger.error(f"Database query error: {str(e)}")
        elif guest_id:
            create_activity(guest_id=guest_id, title=title, description=description)

        logger.warning(description)

        response_data = {
            "status": "fail",
            "message": f"Bill payment failed. {reason}",
            "error": error_detail or {},
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
        self.is_task = bool(user_data.get("is_task"))
        self.task_id = user_data.get("task_id")
        user = request.user if request.user.is_authenticated else None

        # Idempotency: check if this request was already processed.
        # Only short-circuit on a confirmed outcome - a PENDING row means the
        # last attempt never resolved, and a FAILED row means it's safe to
        # retry, so both fall through to reprocess rather than lying about
        # the outcome.
        if user and idempotency_key:
            existing_tx = TxModel.objects.filter(
                user=user, tx_reference=idempotency_key
            ).first()
            if existing_tx and existing_tx.status == "SUCCESS":
                logger.info(
                    f"Idempotent request detected for {user.id} with key {idempotency_key}"
                )
                response_data = {
                    "status": "success",
                    "message": "This request was already processed.",
                    "tx_reference": idempotency_key,
                    "receipt": build_receipt(user, idempotency_key),
                }
                return Response(data=encrypt(response_data), status=status.HTTP_200_OK)
            if existing_tx and existing_tx.status == "PENDING":
                logger.info(
                    f"Idempotent request for {user.id} with key {idempotency_key} is still pending"
                )
                return _handle_pending_response()

        # Extract fields
        # billerId → VTPass serviceID (e.g. ikeja-electric, dstv)
        # customerId → VTPass billersCode (meter / IUC number)
        # itemId → VTPass variation_code (prepaid/postpaid or package code)
        pin = user_data.get("pin")
        amount = user_data.get("amount")
        use_points = user_data.get("use_points")
        use_cashback = user_data.get("use_cashback")
        payment_option = user_data.get("payment_option")
        card_reference = user_data.get("card_reference")
        customerId = user_data.get("customerId")
        billerId = user_data.get("billerId")
        phone_number = user_data.get("phone_number") or (
            user.phone_number if user else None
        )
        customerName = user_data.get("customerName")
        itemId = user_data.get("itemId")
        otherField = user_data.get("otherField")
        address = user_data.get("address")
        # Electricity only - "prepaid" (token issued) or "postpaid" (bill
        # payment, no token ever issued). 9PSB's own "isToken" flag isn't a
        # reliable signal for this (seen true on a postpaid purchase with
        # no token), so this has to come from the client's own item
        # selection instead of anything in the provider response.
        is_postpaid = str(user_data.get("meter_type") or "").lower() == "postpaid"
        has_meter_type = bool(user_data.get("meter_type"))
        biometrics = user_data.get("use_biometrics")

        tx_reference = (
            idempotency_key if idempotency_key else VAS.generate_unique_code("PICA")
        )

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
        elif payment_option == "CARD":
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "Card payment is not available for authenticated users.",
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate payload with serializer
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

        account_number = ""
        if payment_option == "WALLET" and user:
            try:
                account = WalletModel.objects.get(user=user, walletType="INDIVIDUAL")
                account_number = account.account_number
            except WalletModel.DoesNotExist:
                return Response(
                    data=encrypt(
                        {"status": "fail", "error": "Account not found for user"}
                    ),
                    status=status.HTTP_404_NOT_FOUND,
                )

        # Hybrid points/cashback payment: lock, validate, deduct atomically,
        # release before VAS call. Cashback is applied first, points cover
        # whatever's left - together they must cover the full amount.
        cashback_used = Decimal("0")
        pts_used = Decimal("0")
        purchase_amount = int(amount) if amount else 0

        if (use_points or use_cashback) and payment_option == "WALLET" and user:
            try:
                with transaction.atomic():
                    user_wallet = WalletModel.objects.select_for_update().get(
                        user=user, walletType="INDIVIDUAL"
                    )
                    avail_cashback = (
                        user_wallet.cashback_balance if use_cashback else Decimal("0")
                    )
                    avail_pts = Decimal("0")
                    if use_points:
                        try:
                            pts_obj = PointsModel.objects.get(user=user)
                            avail_pts = pts_obj.balance * TIER_VALUES.get(
                                pts_obj.tier, Decimal("0")
                            )
                        except PointsModel.DoesNotExist:
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
                        pts_used = Decimal(str(remaining))
            except WalletModel.DoesNotExist:
                return Response(
                    data=encrypt({"status": "fail", "message": "Wallet not found."}),
                    status=status.HTTP_404_NOT_FOUND,
                )
        # Lock released — VAS call proceeds without holding the DB lock

        match payment_option:
            case "WALLET":
                token = VAS.authenticate()
                if not token:
                    if cashback_used:
                        CashbackService.refund_cashback(
                            user=user, cashback_amount=cashback_used
                        )
                    if pts_used:
                        Pay.refund_pts(user=user, naira_amount=pts_used)
                    return self._handle_failure(
                        tx_reference=tx_reference,
                        user=user,
                        guest_id=guest_id,
                        phone_number=phone_number,
                        amount=(
                            purchase_amount if (use_points or use_cashback) else amount
                        ),
                        reason="VAS authentication failed.",
                        billerId=billerId,
                        has_meter_type=has_meter_type,
                    )
                vas_response = VAS.bill_payment(
                    bearer_token=token,
                    customerId=customerId,
                    billerId=billerId,
                    itemId=itemId,
                    amount=purchase_amount if (use_points or use_cashback) else amount,
                    customerPhone=phone_number,
                    customerName=customerName,
                    otherField=otherField,
                    transactionReference=tx_reference,
                    debitAccount=(
                        collection_account
                        if (use_points or use_cashback)
                        else account_number
                    ),
                )
                if vas_response is None:
                    if cashback_used:
                        CashbackService.refund_cashback(
                            user=user, cashback_amount=cashback_used
                        )
                    if pts_used:
                        Pay.refund_pts(user=user, naira_amount=pts_used)
                    return self._handle_failure(
                        tx_reference=tx_reference,
                        user=user,
                        guest_id=guest_id,
                        phone_number=phone_number,
                        amount=(
                            purchase_amount if (use_points or use_cashback) else amount
                        ),
                        reason="VAS service unavailable.",
                        billerId=billerId,
                        has_meter_type=has_meter_type,
                    )
                if VAS.is_success(vas_response):
                    return self._handle_success(
                        user=user,
                        guest_id=guest_id,
                        customerId=customerId,
                        billerId=billerId,
                        itemId=itemId,
                        amount=(
                            purchase_amount if (use_points or use_cashback) else amount
                        ),
                        phone_number=phone_number,
                        customerName=customerName,
                        otherField=otherField,
                        address=address,
                        is_postpaid=is_postpaid,
                        vas_response=vas_response,
                        tx_reference=tx_reference,
                        account_number=account_number,
                    )
                # Fallback: confirm via status check
                status_resp, outcome = VAS.resolve_outcome(
                    vas_response, tx_reference, token
                )
                if outcome == "success":
                    return self._handle_success(
                        user=user,
                        guest_id=guest_id,
                        customerId=customerId,
                        billerId=billerId,
                        itemId=itemId,
                        amount=(
                            purchase_amount if (use_points or use_cashback) else amount
                        ),
                        phone_number=phone_number,
                        customerName=customerName,
                        otherField=otherField,
                        address=address,
                        is_postpaid=is_postpaid,
                        vas_response=status_resp,
                        tx_reference=tx_reference,
                        account_number=account_number,
                    )
                if outcome == "pending":
                    return _handle_pending_response(
                        user=user,
                        tx_reference=tx_reference,
                        tx_type="Bill Payment",
                        amount=(
                            purchase_amount if (use_points or use_cashback) else amount
                        ),
                        description=f"{_bill_payment_category(billerId, has_meter_type)} pending.",
                    )
                if cashback_used:
                    CashbackService.refund_cashback(
                        user=user, cashback_amount=cashback_used
                    )
                if pts_used:
                    Pay.refund_pts(user=user, naira_amount=pts_used)
                return self._handle_failure(
                    tx_reference=tx_reference,
                    user=user,
                    guest_id=guest_id,
                    phone_number=phone_number,
                    amount=purchase_amount if (use_points or use_cashback) else amount,
                    vas_response=status_resp,
                    reason="Bill payment failed.",
                    billerId=billerId,
                    has_meter_type=has_meter_type,
                )

            # case "TREASURY": disabled — treasury VAS payments on hold
            case "CARD":
                funding, card_error_response = verify_card_payment(
                    card_reference, amount, user
                )
                if card_error_response is not None:
                    return card_error_response

                token = VAS.authenticate()
                if not token:
                    return self._handle_failure(
                        tx_reference=tx_reference,
                        user=user,
                        guest_id=guest_id,
                        phone_number=phone_number,
                        amount=amount,
                        reason="VAS authentication failed.",
                        billerId=billerId,
                        has_meter_type=has_meter_type,
                    )
                vas_response = VAS.bill_payment(
                    bearer_token=token,
                    customerId=customerId,
                    billerId=billerId,
                    itemId=itemId,
                    amount=amount,
                    customerPhone=phone_number,
                    customerName=customerName,
                    otherField=otherField,
                    transactionReference=tx_reference,
                )
                if vas_response is None:
                    return self._handle_failure(
                        tx_reference=tx_reference,
                        user=user,
                        guest_id=guest_id,
                        phone_number=phone_number,
                        amount=amount,
                        reason="VAS service unavailable.",
                        billerId=billerId,
                        has_meter_type=has_meter_type,
                    )
                if VAS.is_success(vas_response):
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
                        address=address,
                        is_postpaid=is_postpaid,
                        vas_response=vas_response,
                        tx_reference=tx_reference,
                        account_number=account_number,
                    )
                status_resp, outcome = VAS.resolve_outcome(
                    vas_response, tx_reference, token
                )
                if outcome == "success":
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
                        address=address,
                        is_postpaid=is_postpaid,
                        vas_response=status_resp,
                        tx_reference=tx_reference,
                        account_number=account_number,
                    )
                if outcome == "pending":
                    return _handle_pending_response(
                        user=user,
                        tx_reference=tx_reference,
                        tx_type="Bill Payment",
                        amount=amount,
                        description=f"{_bill_payment_category(billerId, has_meter_type)} pending.",
                    )
                return self._handle_failure(
                    tx_reference=tx_reference,
                    user=user,
                    guest_id=guest_id,
                    phone_number=phone_number,
                    amount=amount,
                    vas_response=status_resp,
                    reason="Bill payment failed.",
                    billerId=billerId,
                    has_meter_type=has_meter_type,
                )

            case _:
                return Response(
                    data=encrypt(
                        {"status": "fail", "message": "Invalid payment option"}
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )
