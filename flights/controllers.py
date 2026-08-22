from decimal import Decimal

import requests
from decouple import config

FLIGHTSLOGIC_USER_ID = config("FLIGHTSLOGIC_USER_ID")
FLIGHTSLOGIC_PASSWORD = config("FLIGHTSLOGIC_PASSWORD")
FLIGHTSLOGIC_BASE_URL = config("FLIGHTSLOGIC_BASE_URL")
FLIGHTSLOGIC_ACCESS = config("FLIGHTSLOGIC_ACCESS", default="Test")


class FlightsLogic:
    def __init__(self):
        self.user_id = FLIGHTSLOGIC_USER_ID
        self.password = FLIGHTSLOGIC_PASSWORD
        self.access = FLIGHTSLOGIC_ACCESS
        self.base_url = FLIGHTSLOGIC_BASE_URL.rstrip("/")

    def _build_url(self, endpoint):
        return f"{self.base_url}/{endpoint.lstrip('/')}"

    def _call(self, endpoint, payload, ip_address, timeout=30):
        body = {
            "user_id": self.user_id,
            "user_password": self.password,
            "access": self.access,
            "ip_address": ip_address,
            **payload,
        }
        response = requests.post(self._build_url(endpoint), json=body, timeout=timeout)
        response.raise_for_status()
        return response.json()

    @staticmethod
    def is_error(response):
        return bool(response.get("Errors"))

    @staticmethod
    def unwrap(response, response_key, result_key):
        return response.get(response_key, {}).get(result_key, response)

    @staticmethod
    def extract_total_fare(fare_itinerary):
        try:
            fare_info = fare_itinerary["FareItinerary"]
            return Decimal(str(fare_info["TotalFare"])), fare_info.get("Currency")
        except (KeyError, TypeError):
            return None, None

    def search(
        self,
        ip_address,
        journey_type,
        origin_destination_info,
        adults,
        childs=0,
        infants=0,
        cabin_class="Economy",
        required_currency="NGN",
    ):
        payload = {
            "journeyType": journey_type,
            "OriginDestinationInfo": origin_destination_info,
            "class": cabin_class,
            "adults": adults,
            "childs": childs,
            "infants": infants,
            "requiredCurrency": required_currency,
        }
        return self._call("availability", payload, ip_address)

    def revalidate(self, ip_address, session_id, fare_source_code):
        payload = {
            "session_id": session_id,
            "fare_source_code": fare_source_code,
        }
        return self._call("revalidate", payload, ip_address)

    def airport_list(self, ip_address):
        return self._call("airport_list", {}, ip_address)

    def fare_rules(self, ip_address, session_id, fare_source_code):
        payload = {
            "session_id": session_id,
            "fare_source_code": fare_source_code,
        }
        return self._call("fare_rules", payload, ip_address)

    def booking(self, ip_address, flight_booking_info, pax_info):
        payload = {
            "flightBookingInfo": flight_booking_info,
            "paxInfo": pax_info,
        }
        return self._call("booking", payload, ip_address)

    def ticket_order(self, ip_address, unique_id):
        return self._call("ticket_order", {"UniqueID": unique_id}, ip_address)

    def cancel_booking(self, ip_address, unique_id):
        return self._call("cancel", {"UniqueID": unique_id}, ip_address)

    def trip_details(self, ip_address, unique_id):
        return self._call("trip_details", {"UniqueID": unique_id}, ip_address)
