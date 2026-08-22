import logging

from decouple import config

from .controllers import FlightsLogic
from .models import Airport

logger = logging.getLogger(__name__)

FLIGHTSLOGIC_SERVER_IP = config("FLIGHTSLOGIC_SERVER_IP", default="127.0.0.1")


def _extract_airports(response):
    if isinstance(response, list):
        return response
    for value in response.values():
        if isinstance(value, list):
            return value
    return []


def sync_airports():
    client = FlightsLogic()
    response = client.airport_list(ip_address=FLIGHTSLOGIC_SERVER_IP)
    if client.is_error(response):
        logger.error(
            "FlightsLogic airport_list sync failed: %s", response.get("Errors")
        )
        return

    airports = _extract_airports(response)
    records = [
        Airport(
            airport_code=entry["AirportCode"],
            airport_name=entry.get("AirportName"),
            city=entry.get("City"),
            country=entry.get("Country"),
            country_code=entry.get("CountryCode"),
            latitude=entry.get("Latitude"),
            longitude=entry.get("Longitude"),
        )
        for entry in airports
        if entry.get("AirportCode")
    ]

    Airport.objects.bulk_create(
        records,
        update_conflicts=True,
        unique_fields=["airport_code"],
        update_fields=[
            "airport_name",
            "city",
            "country",
            "country_code",
            "latitude",
            "longitude",
            "updated_at",
        ],
        batch_size=1000,
    )
    logger.info("Synced %s airports from FlightsLogic", len(records))
