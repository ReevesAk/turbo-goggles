import logging
import uuid
from decimal import Decimal

import requests
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.response import Response

from banking.cashback_service import CashbackService
from banking.helpers import verify_wallet_auth
from banking.models import TxModel, WalletModel
from commons import Pay
from gamification.models import Points as PointsModel
from gamification.points import TIER_VALUES
from modules.billing_mixings import BrandChargeMixin
from permissions import IsAuthenticatedOrGuestWithValidId
from security import encrypt, decrypt
from .caching import get_cached_search, set_cached_search
from .controllers import FlightsLogic
from .models import Airport, FlightBooking
from .serializers import (
    AirportSerializer,
    FareRulesSerializer,
    FlightBookingSerializer,
    FlightCancelSerializer,
    FlightRevalidateSerializer,
    FlightSearchSerializer,
)
from .tasks import finalize_flight_booking

logger = logging.getLogger(__name__)


class FlightBookingFailed(Exception):
    pass


class InsufficientHybridBalance(Exception):
    pass


def _envelope(status_str, message, data=None):
    """Every flights response body is {status, message, data} — no endpoint
    omits or renames one of these three keys, so mobile can parse any
    response the same way regardless of which endpoint or branch produced
    it."""
    return encrypt({"status": status_str, "message": message, "data": data})


def _ok(message, data=None):
    return Response(data=_envelope("success", message, data), status=status.HTTP_200_OK)


def _fail(message, data=None, http_status=status.HTTP_400_BAD_REQUEST):
    return Response(data=_envelope("fail", message, data), status=http_status)


def _client_ip(request):
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _call_provider(call, action):
    """Runs a FlightsLogic client call, returning (response, error_response).
    Exactly one of the two is None."""
    try:
        response = call()
    except requests.RequestException as e:
        logger.error("FlightsLogic %s request failed: %s", action, e)
        return None, _fail(
            "Failed to reach flight provider.", http_status=status.HTTP_502_BAD_GATEWAY
        )

    if FlightsLogic.is_error(response):
        errors = response.get("Errors") or {}
        logger.warning("FlightsLogic %s returned errors: %s", action, errors)
        message = errors.get("ErrorMessage") or "The flight provider returned an error."
        return None, _fail(
            message, data=errors, http_status=status.HTTP_502_BAD_GATEWAY
        )

    return response, None


class FlightSearchView(generics.GenericAPIView):
    """POST /v1/flights/search/ — search available flights via FlightsLogic."""

    permission_classes = [IsAuthenticatedOrGuestWithValidId]
    serializer_class = FlightSearchSerializer

    def post(self, request):
        payload = decrypt(request.data)
        serializer = self.get_serializer(data=payload)
        if not serializer.is_valid():
            return _fail("Invalid request.", data=serializer.errors)

        data = serializer.validated_data
        cached = get_cached_search(data)
        if cached is not None:
            return _ok("Cached search results.", data=cached)

        response, error = _call_provider(
            lambda: FlightsLogic().search(
                ip_address=_client_ip(request),
                journey_type=data["journey_type"],
                origin_destination_info=data["origin_destination_info"],
                adults=data["adults"],
                childs=data["childs"],
                infants=data["infants"],
                cabin_class=data["cabin_class"],
                required_currency=data["required_currency"],
            ),
            "search",
        )
        if error:
            return error

        set_cached_search(data, response)

        return _ok("Search results retrieved successfully.", data=response)


class FlightRevalidateView(generics.GenericAPIView):
    """POST /v1/flights/revalidate/ — re-confirm price/availability for a
    selected fare before the passenger-details step."""

    permission_classes = [IsAuthenticatedOrGuestWithValidId]
    serializer_class = FlightRevalidateSerializer

    def post(self, request):
        payload = decrypt(request.data)
        serializer = self.get_serializer(data=payload)
        if not serializer.is_valid():
            return _fail("Invalid request.", data=serializer.errors)

        data = serializer.validated_data
        response, error = _call_provider(
            lambda: FlightsLogic().revalidate(
                ip_address=_client_ip(request),
                session_id=data["session_id"],
                fare_source_code=data["fare_source_code"],
            ),
            "revalidate",
        )
        if error:
            return error

        result = FlightsLogic.unwrap(
            response, "AirRevalidateResponse", "AirRevalidateResult"
        )
        if not result.get("IsValid"):
            return _fail("This fare is no longer available. Please search again.")

        return _ok("Fare revalidated successfully.", data=result)


class FareRulesView(generics.GenericAPIView):
    """POST /v1/flights/fare-rules/ — baggage allowance and fare rules for a
    selected flight, keyed by the same session_id/fare_source_code pair used
    for Revalidate."""

    permission_classes = [IsAuthenticatedOrGuestWithValidId]
    serializer_class = FareRulesSerializer

    def post(self, request):
        payload = decrypt(request.data)
        serializer = self.get_serializer(data=payload)
        if not serializer.is_valid():
            return _fail("Invalid request.", data=serializer.errors)

        data = serializer.validated_data
        response, error = _call_provider(
            lambda: FlightsLogic().fare_rules(
                ip_address=_client_ip(request),
                session_id=data["session_id"],
                fare_source_code=data["fare_source_code"],
            ),
            "fare_rules",
        )
        if error:
            return error

        result = FlightsLogic.unwrap(
            response, "FareRules1_1Response", "FareRules1_1Result"
        )

        return _ok("Fare rules retrieved successfully.", data=result)


class FlightBookingView(BrandChargeMixin, generics.GenericAPIView):
    """POST /v1/flights/book/ — pay for and book a revalidated fare.

    Ordering is deliberate: Revalidate is called again here (server-side) to
    get a live, trusted fare amount — we never charge whatever amount the
    client claims, matching the lesson already learned elsewhere in this
    codebase (see the Paystack kobo-conversion fix in banking/). Only once
    that's confirmed do we verify payment and, inside the payment step, call
    FlightsLogic's booking endpoint — so a failed provider booking is
    refunded like any other failed purchase.

    Two payment paths:
      - WALLET/CARD, no points/rewards: routed through
        BrandChargeMixin.charge_and_create() (same mixin CreateAdAndOnboardBrandView
        uses), which owns idempotency and the wallet-debit/card-verify +
        compensating refund.
      - WALLET with use_points/use_rewards: charge_and_create() has no
        cashback/points awareness, so this goes through
        _book_with_points_or_rewards() instead, mirroring the exact
        select_for_update + CashbackService.apply_cashback_payment() +
        Pay.with_pts() pattern vas/views.py already uses. Matches that
        existing precedent: cashback+points must cover the FULL amount
        together, or the whole payment fails — there's no partial discount
        stacked on top of a wallet-balance debit."""

    permission_classes = [IsAuthenticatedOrGuestWithValidId]
    serializer_class = FlightBookingSerializer

    def post(self, request):
        payload = decrypt(request.data)
        serializer = self.get_serializer(data=payload)
        if not serializer.is_valid():
            return _fail("Invalid request.", data=serializer.errors)

        data = serializer.validated_data
        user = request.user if request.user.is_authenticated else None

        if not user and data["payment_option"] != "CARD":
            return _fail("Guests must pay by card.")

        client = FlightsLogic()
        ip_address = _client_ip(request)

        revalidate_response, error = _call_provider(
            lambda: client.revalidate(
                ip_address=ip_address,
                session_id=data["session_id"],
                fare_source_code=data["fare_source_code"],
            ),
            "revalidate",
        )
        if error:
            return error

        revalidate_result = FlightsLogic.unwrap(
            revalidate_response, "AirRevalidateResponse", "AirRevalidateResult"
        )
        if not revalidate_result.get("IsValid"):
            return _fail("This fare is no longer available. Please search again.")

        fare_itineraries = revalidate_result.get("FareItineraries") or []
        amount, currency = (
            FlightsLogic.extract_total_fare(fare_itineraries[0])
            if fare_itineraries
            else (None, None)
        )
        if amount is None:
            return _fail(
                "Could not confirm fare pricing.",
                http_status=status.HTTP_502_BAD_GATEWAY,
            )

        is_verified, auth_error = verify_wallet_auth(
            user=user,
            payment_option=data["payment_option"],
            pin=data.get("pin"),
            use_biometrics=data.get("use_biometrics"),
        )
        if not is_verified:
            return auth_error

        tx_reference = (
            request.headers.get("Idempotency-Key")
            or f"PICAFLT{uuid.uuid4().hex[:16].upper()}"
        )
        guest_id = None if user else request.headers.get("X-Guest-ID")

        if (
            user
            and data["payment_option"] == "WALLET"
            and (data.get("use_points") or data.get("use_rewards"))
        ):
            return self._book_with_points_or_rewards(
                data, user, guest_id, tx_reference, amount, currency, client, ip_address
            )

        booking, charge_error = self.charge_and_create(
            user=user,
            payment_option=data["payment_option"],
            card_reference=data.get("card_reference"),
            amount=amount,
            tx_reference=tx_reference,
            tx_type="Travel",
            tx_description=f"Flight booking - {data['customer_email']}",
            notification_title="Flight Booking",
            notification_phrase="your flight booking",
            activity_description="booked a flight",
            debit_reason="Flight booking payment",
            save_fn=lambda: self._create_booking_after_payment(
                client, ip_address, data, user, guest_id, tx_reference, amount, currency
            ),
        )
        if charge_error:
            return charge_error

        finalize_flight_booking.delay(str(booking.tx_reference))

        return _ok(
            "Flight booked successfully. Confirmation pending.",
            data={"booking_id": str(booking.tx_reference)},
        )

    @staticmethod
    def _create_booking_after_payment(
        client, ip_address, data, user, guest_id, tx_reference, amount, currency
    ):
        booking_response, booking_error = _call_provider(
            lambda: client.booking(
                ip_address=ip_address,
                flight_booking_info=data["flight_booking_info"],
                pax_info=data["pax_info"],
            ),
            "booking",
        )
        if booking_error is not None:
            raise FlightBookingFailed(
                "FlightsLogic booking call failed after payment succeeded"
            )

        return FlightBooking.objects.create(
            user=user,
            guest_id=guest_id,
            tx_reference=tx_reference,
            session_id=data["session_id"],
            fare_source_code=data["fare_source_code"],
            fare_type=data["fare_type"],
            status="PENDING",
            currency=currency,
            total_price=amount,
            customer_email=data["customer_email"],
            customer_phone=data["customer_phone"],
            passengers=data["passengers"],
            provider_response=booking_response,
        )

    def _book_with_points_or_rewards(
        self, data, user, guest_id, tx_reference, amount, currency, client, ip_address
    ):
        existing = TxModel.objects.filter(
            tx_reference=tx_reference, tx_type="Travel"
        ).first()
        if existing is not None:
            if existing.status == "SUCCESS":
                return _ok(
                    "This request was already processed.",
                    data={"booking_id": tx_reference},
                )
            if existing.status == "PENDING":
                return _fail(
                    "A previous request for this payment is still processing. Please try again shortly.",
                    http_status=status.HTTP_409_CONFLICT,
                )

        cashback_used = Decimal("0")
        points_naira_used = Decimal("0")

        try:
            with transaction.atomic():
                wallet = WalletModel.objects.select_for_update().get(
                    user=user, walletType="INDIVIDUAL"
                )
                avail_cashback = (
                    wallet.cashback_balance if data.get("use_rewards") else Decimal("0")
                )

                avail_pts = Decimal("0")
                if data.get("use_points"):
                    pts_obj = (
                        PointsModel.objects.select_for_update()
                        .filter(user=user)
                        .first()
                    )
                    if pts_obj:
                        avail_pts = pts_obj.balance * TIER_VALUES.get(
                            pts_obj.tier, Decimal("0")
                        )

                if avail_cashback + avail_pts < amount:
                    raise InsufficientHybridBalance()

                remaining = amount
                if data.get("use_rewards"):
                    result = CashbackService.apply_cashback_payment(
                        user=user, amount=remaining
                    )
                    cashback_used = result["cashback_used"]
                    remaining = result["wallet_amount"]

                if data.get("use_points") and remaining > 0:
                    outcome, _ = Pay.with_pts(user=user, amount=remaining)
                    if outcome != "Enough":
                        raise InsufficientHybridBalance()
                    points_naira_used = remaining

                if existing is not None:
                    existing.amount = float(amount)
                    existing.status = "PENDING"
                    existing.save(update_fields=["amount", "status"])
                    tx = existing
                else:
                    tx = TxModel.objects.create(
                        user=user,
                        tx_reference=tx_reference,
                        tx_type="Travel",
                        amount=float(amount),
                        description=f"Flight booking - {data['customer_email']}",
                        status="PENDING",
                    )
        except InsufficientHybridBalance:
            return _fail("Insufficient points/rewards balance to cover this flight.")
        except WalletModel.DoesNotExist:
            return _fail("Wallet not found.", http_status=status.HTTP_404_NOT_FOUND)

        # Lock released — FlightsLogic call proceeds without holding the DB lock
        try:
            booking = self._create_booking_after_payment(
                client, ip_address, data, user, guest_id, tx_reference, amount, currency
            )
        except Exception:
            logger.exception(
                "Flight booking failed after points/rewards payment succeeded — "
                "issuing compensating refund for tx_reference=%s",
                tx_reference,
            )
            if cashback_used > 0:
                CashbackService.refund_cashback(
                    user=user, cashback_amount=cashback_used
                )
            if points_naira_used > 0:
                Pay.refund_pts(user=user, naira_amount=points_naira_used)
            tx.status = "FAILED"
            tx.save(update_fields=["status"])
            return _fail(
                "Booking failed. Your points/rewards have been refunded.",
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        tx.status = "SUCCESS"
        tx.save(update_fields=["status"])

        finalize_flight_booking.delay(str(booking.tx_reference))

        return _ok(
            "Flight booked successfully. Confirmation pending.",
            data={"booking_id": str(booking.tx_reference)},
        )


class FlightCancelView(generics.GenericAPIView):
    """POST /v1/flights/cancel/ — cancel a confirmed booking via FlightsLogic.

    Client sends our own booking_id (tx_reference), never the vendor's
    UniqueID directly. Only cancels with the provider and records the
    RefundAmount it reports — does NOT itself reverse the original
    wallet/card charge. Whether/how much to refund the user back into their
    wallet is a separate money-movement decision, deliberately not guessed
    at here until a real cancellation response (and any provider fees) has
    been observed live."""

    permission_classes = [IsAuthenticatedOrGuestWithValidId]
    serializer_class = FlightCancelSerializer

    def post(self, request):
        payload = decrypt(request.data)
        serializer = self.get_serializer(data=payload)
        if not serializer.is_valid():
            return _fail("Invalid request.", data=serializer.errors)

        user = request.user if request.user.is_authenticated else None
        guest_id = None if user else request.headers.get("X-Guest-ID")

        try:
            booking = FlightBooking.objects.get(
                tx_reference=serializer.validated_data["booking_id"]
            )
        except FlightBooking.DoesNotExist:
            return _fail("Booking not found.", http_status=status.HTTP_404_NOT_FOUND)

        owns_booking = (user and booking.user_id == user.id) or (
            guest_id and str(booking.guest_id) == str(guest_id)
        )
        if not owns_booking:
            return _fail("Booking not found.", http_status=status.HTTP_404_NOT_FOUND)

        if booking.status == "CANCELLED":
            return _ok(
                "This booking is already cancelled.",
                data={"booking_id": str(booking.tx_reference)},
            )
        if not booking.booking_reference:
            return _fail(
                "This booking isn't confirmed with the provider yet, so it can't be cancelled."
            )

        response, error = _call_provider(
            lambda: FlightsLogic().cancel_booking(
                ip_address=_client_ip(request), unique_id=booking.booking_reference
            ),
            "cancel",
        )
        if error:
            return error

        result = FlightsLogic.unwrap(
            response, "CancelBookingResponse", "CancelBookingResult"
        )
        if not result.get("Success"):
            return _fail(
                "Cancellation was not confirmed by the provider.",
                http_status=status.HTTP_502_BAD_GATEWAY,
            )

        booking.status = "CANCELLED"
        booking.cancelled_at = timezone.now()
        refund_amount = result.get("RefundAmount")
        if refund_amount is not None:
            booking.refund_amount = refund_amount
        booking.save(update_fields=["status", "cancelled_at", "refund_amount"])

        return _ok(
            "Booking cancelled successfully.",
            data={
                "booking_id": str(booking.tx_reference),
                "refund_amount": booking.refund_amount,
            },
        )


class AirportSearchView(generics.ListAPIView):
    """GET /v1/flights/airports/?q=<query> — local autocomplete lookup for
    origin/destination city fields, backed by a synced copy of FlightsLogic's
    Airport List so the vendor is never called directly from the client."""

    permission_classes = [IsAuthenticatedOrGuestWithValidId]
    serializer_class = AirportSerializer

    def get_queryset(self):
        query = self.request.query_params.get("q", "").strip()
        if len(query) < 2:
            return Airport.objects.none()
        return Airport.objects.filter(
            Q(city__icontains=query)
            | Q(airport_name__icontains=query)
            | Q(airport_code__iexact=query)
        )[:20]

    def list(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_queryset(), many=True)
        return _ok("Airports retrieved successfully.", data=serializer.data)
