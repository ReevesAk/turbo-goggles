import logging

from celery import shared_task

from accounts.models import UserNotification
from roles.models import ActivityModel

from .controllers import FlightsLogic
from .jobs import FLIGHTSLOGIC_SERVER_IP
from .models import FlightBooking

logger = logging.getLogger(__name__)

_UNIQUE_ID_KEYS = ("UniqueID", "PNR")


def _extract_unique_id(response):
    result = FlightsLogic.unwrap(response, "BookingResponse", "BookingResult")
    for key in _UNIQUE_ID_KEYS:
        value = result.get(key)
        if value:
            return value
    return None


@shared_task(autoretry_for=(Exception,), max_retries=3, default_retry_delay=30)
def finalize_flight_booking(tx_reference):
    try:
        booking = FlightBooking.objects.get(tx_reference=tx_reference)
    except FlightBooking.DoesNotExist:
        logger.error(
            "finalize_flight_booking: no FlightBooking for tx_reference=%s",
            tx_reference,
        )
        return

    unique_id = _extract_unique_id(booking.provider_response or {})
    if not unique_id:
        logger.warning(
            "finalize_flight_booking: could not find a booking reference in the "
            "provider response for tx_reference=%s — Booking's success shape is "
            "still unconfirmed. Leaving status PENDING for manual follow-up.",
            tx_reference,
        )
        return

    booking.booking_reference = unique_id
    client = FlightsLogic()

    if booking.fare_type == "WebFare":
        booking.status = "SUCCESS"
        booking.save(update_fields=["booking_reference", "status"])
        _notify_customer(booking)
        return

    ticket_response = client.ticket_order(
        ip_address=FLIGHTSLOGIC_SERVER_IP, unique_id=unique_id
    )
    if client.is_error(ticket_response):
        logger.error(
            "finalize_flight_booking: ticket_order failed for tx_reference=%s: %s",
            tx_reference,
            ticket_response.get("Errors"),
        )
        booking.status = "FAILED"
        booking.save(update_fields=["booking_reference", "status"])
        return

    booking.status = "SUCCESS"
    booking.save(update_fields=["booking_reference", "status"])
    _notify_customer(booking)


def _notify_customer(booking):
    if not booking.user:
        return
    UserNotification.objects.create(
        user=booking.user,
        title="Flight Booking Confirmed",
        message=f"Your flight booking ({booking.booking_reference}) is confirmed.",
    )
    ActivityModel.objects.create(
        user=booking.user,
        title="Flight Booking Confirmed",
        description=f"{booking.user} booked a flight ({booking.booking_reference}).",
    )
