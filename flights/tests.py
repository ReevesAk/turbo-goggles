import math
import uuid
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.contrib.auth.hashers import make_password
from django.test import SimpleTestCase, TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import TxModel, User
from banking.models import FundWithCard, WalletModel
from gamification.models import Points as PointsModel
from gamification.points import TIER_VALUES
from security import decrypt, encrypt

from .controllers import FlightsLogic
from .models import Airport, FlightBooking
from .serializers import (
    FlightBookingSerializer,
    FlightCancelSerializer,
    FlightSearchSerializer,
)
from .tasks import _extract_unique_id, finalize_flight_booking

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _create_user(**overrides):
    seed = uuid.uuid4().hex[:8]
    data = {
        "phone_number": f"23481{seed[:7]}",
        "password": "StrongPass123!",
        "first_name": "Jane",
        "last_name": "Doe",
        "email": f"jane.{seed}@example.com",
        "country": "NG",
        "state": "Lagos",
        "city": "Ikeja",
        "is_verified": True,
    }
    data.update(overrides)
    password = data.pop("password")
    user = User.objects.create(**data)
    user.set_password(password)
    user.save()
    return user


def _revalidate_response(total_fare="1000.00", currency="NGN", is_valid=True):
    return {
        "AirRevalidateResponse": {
            "AirRevalidateResult": {
                "IsValid": is_valid,
                "IsPassportMandatory": False,
                "FareItineraries": [
                    {
                        "FareItinerary": {
                            "TotalFare": total_fare,
                            "BaseFare": "900.00",
                            "Taxes": "100.00",
                            "Currency": currency,
                        }
                    }
                ],
            }
        }
    }


def _booking_success_response(unique_id="ABCDEF"):
    return {
        "BookingResponse": {
            "BookingResult": {
                "Success": True,
                "UniqueID": unique_id,
                "PNR": unique_id,
                "Status": "Confirmed",
            }
        }
    }


def _cancel_response(success=True, refund_amount="450.00"):
    return {
        "CancelBookingResponse": {
            "CancelBookingResult": {
                "Success": success,
                "UniqueID": "ABCDEF",
                "Status": "Cancelled" if success else "Failed",
                "RefundAmount": refund_amount,
            }
        }
    }


def _valid_passenger(**overrides):
    data = {
        "type": "adult",
        "title": "Mr",
        "first_name": "John",
        "last_name": "Doe",
        "dob": "1990-01-01",
        "nationality": "NG",
    }
    data.update(overrides)
    return data


def _valid_booking_payload(**overrides):
    data = {
        "session_id": "sess-1",
        "fare_source_code": "fsc-1",
        "fare_type": "Public",
        "is_passport_mandatory": False,
        "customer_email": "jane.doe@example.com",
        "customer_phone": "+2348012345678",
        "passengers": [_valid_passenger()],
        "payment_option": "WALLET",
        "pin": "1234",
    }
    data.update(overrides)
    return data


# ---------------------------------------------------------------------------
# Controller (FlightsLogic) static helpers
# ---------------------------------------------------------------------------


class FlightsLogicHelperTests(TestCase):
    def test_extract_total_fare_reads_flat_shape(self):
        fare_itinerary = {
            "FareItinerary": {
                "TotalFare": "535.50",
                "BaseFare": "450.00",
                "Taxes": "85.50",
                "Currency": "NGN",
            }
        }
        amount, currency = FlightsLogic.extract_total_fare(fare_itinerary)
        self.assertEqual(amount, Decimal("535.50"))
        self.assertEqual(currency, "NGN")

    def test_extract_total_fare_returns_none_on_malformed_input(self):
        self.assertEqual(FlightsLogic.extract_total_fare({}), (None, None))
        self.assertEqual(FlightsLogic.extract_total_fare(None), (None, None))
        self.assertEqual(
            FlightsLogic.extract_total_fare({"FareItinerary": {}}), (None, None)
        )

    def test_is_error_detects_errors_key(self):
        self.assertTrue(FlightsLogic.is_error({"Errors": {"ErrorCode": "X"}}))
        self.assertFalse(FlightsLogic.is_error({"status": "ok"}))
        self.assertFalse(FlightsLogic.is_error({}))

    def test_unwrap_returns_nested_result(self):
        response = {"BookingResponse": {"BookingResult": {"Success": True}}}
        result = FlightsLogic.unwrap(response, "BookingResponse", "BookingResult")
        self.assertEqual(result, {"Success": True})

    def test_unwrap_falls_back_to_whole_response_when_key_missing(self):
        response = {"unexpected": "shape"}
        result = FlightsLogic.unwrap(response, "BookingResponse", "BookingResult")
        self.assertEqual(result, response)


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------


class FlightSearchSerializerTests(SimpleTestCase):
    def test_one_way_builds_single_leg(self):
        serializer = FlightSearchSerializer(
            data={
                "journey_type": "OneWay",
                "origin": "LOS",
                "destination": "LHR",
                "departure_date": "2026-09-15",
                "adults": 1,
            }
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        info = serializer.validated_data["origin_destination_info"]
        self.assertEqual(len(info), 1)
        self.assertEqual(info[0]["airportOriginCode"], "LOS")
        self.assertEqual(info[0]["airportDestinationCode"], "LHR")
        self.assertEqual(info[0]["departureDate"], "2026-09-15")

    def test_one_way_missing_required_field_is_rejected(self):
        serializer = FlightSearchSerializer(
            data={"journey_type": "OneWay", "origin": "LOS", "adults": 1}
        )
        self.assertFalse(serializer.is_valid())

    def test_return_builds_two_legs(self):
        serializer = FlightSearchSerializer(
            data={
                "journey_type": "Return",
                "origin": "LOS",
                "destination": "LHR",
                "departure_date": "2026-09-15",
                "return_date": "2026-09-25",
                "adults": 1,
            }
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        info = serializer.validated_data["origin_destination_info"]
        self.assertEqual(len(info), 2)
        self.assertEqual(info[1]["airportOriginCode"], "LHR")
        self.assertEqual(info[1]["airportDestinationCode"], "LOS")

    def test_multicity_requires_at_least_two_legs(self):
        serializer = FlightSearchSerializer(
            data={
                "journey_type": "MultiCity",
                "legs": [
                    {
                        "origin": "LOS",
                        "destination": "LHR",
                        "departure_date": "2026-09-15",
                    }
                ],
                "adults": 1,
            }
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("legs", serializer.errors)

    def test_multicity_rejects_more_than_five_legs(self):
        legs = [
            {
                "origin": "LOS",
                "destination": "LHR",
                "departure_date": "2026-09-15",
            }
            for _ in range(6)
        ]
        serializer = FlightSearchSerializer(
            data={"journey_type": "MultiCity", "legs": legs, "adults": 1}
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("legs", serializer.errors)

    def test_circle_journey_type_accepted_like_multicity(self):
        legs = [
            {"origin": "LOS", "destination": "LHR", "departure_date": "2026-09-15"},
            {"origin": "LHR", "destination": "DXB", "departure_date": "2026-09-20"},
            {"origin": "DXB", "destination": "LOS", "departure_date": "2026-09-25"},
        ]
        serializer = FlightSearchSerializer(
            data={"journey_type": "Circle", "legs": legs, "adults": 1}
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(len(serializer.validated_data["origin_destination_info"]), 3)


class FlightBookingSerializerTests(SimpleTestCase):
    def test_valid_payload_builds_flight_booking_info_and_pax_info(self):
        serializer = FlightBookingSerializer(data=_valid_booking_payload())
        self.assertTrue(serializer.is_valid(), serializer.errors)
        data = serializer.validated_data
        self.assertEqual(data["flight_booking_info"]["fareType"], "Public")
        self.assertEqual(data["pax_info"]["customerEmail"], "jane.doe@example.com")
        self.assertEqual(
            data["pax_info"]["paxDetails"][0]["adult"]["firstName"], ["John"]
        )

    def test_passport_required_when_mandatory_flag_set(self):
        payload = _valid_booking_payload(is_passport_mandatory=True)
        serializer = FlightBookingSerializer(data=payload)
        self.assertFalse(serializer.is_valid())
        self.assertIn("passengers", serializer.errors)

    def test_passport_fields_satisfy_mandatory_flag(self):
        payload = _valid_booking_payload(
            is_passport_mandatory=True,
            passengers=[
                _valid_passenger(
                    passport_no="A1234567",
                    passport_issue_country="NG",
                    passport_expiry_date="2031-01-01",
                )
            ],
        )
        serializer = FlightBookingSerializer(data=payload)
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_rejects_invalid_title_for_passenger_type(self):
        payload = _valid_booking_payload(
            passengers=[_valid_passenger(type="child", title="Mr")]
        )
        serializer = FlightBookingSerializer(data=payload)
        self.assertFalse(serializer.is_valid())

    def test_requires_at_least_one_adult(self):
        payload = _valid_booking_payload(
            passengers=[_valid_passenger(type="child", title="Miss", dob="2018-01-01")]
        )
        serializer = FlightBookingSerializer(data=payload)
        self.assertFalse(serializer.is_valid())
        self.assertIn("passengers", serializer.errors)

    def test_groups_mixed_passenger_types_into_parallel_arrays(self):
        payload = _valid_booking_payload(
            passengers=[
                _valid_passenger(),
                _valid_passenger(
                    type="child", title="Miss", first_name="Jess", dob="2018-01-01"
                ),
                _valid_passenger(
                    type="infant", title="Master", first_name="Baby", dob="2025-01-01"
                ),
            ]
        )
        serializer = FlightBookingSerializer(data=payload)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        pax = serializer.validated_data["pax_info"]["paxDetails"][0]
        self.assertEqual(set(pax.keys()), {"adult", "child", "infant"})
        self.assertEqual(pax["child"]["firstName"], ["Jess"])
        self.assertEqual(pax["infant"]["firstName"], ["Baby"])


class FlightCancelSerializerTests(SimpleTestCase):
    def test_requires_booking_id(self):
        serializer = FlightCancelSerializer(data={})
        self.assertFalse(serializer.is_valid())

    def test_accepts_our_own_booking_id_format(self):
        # booking_id is our own tx_reference (e.g. "PICAFLT..."), not a UUID
        # — it's a plain string, matching TxModel.tx_reference's format.
        serializer = FlightCancelSerializer(data={"booking_id": "PICAFLTAB12CD34EF56"})
        self.assertTrue(serializer.is_valid(), serializer.errors)


# ---------------------------------------------------------------------------
# Views: Search / Revalidate / Fare Rules / Airports
# ---------------------------------------------------------------------------


class FlightSearchViewTests(APITestCase):
    url = "/v1/flights/search/"

    def setUp(self):
        self.user = _create_user()
        self.client.force_authenticate(user=self.user)
        # LocMemCache is a process-wide singleton — TestCase only rolls back
        # the DB between tests, so a search cached by one test would
        # otherwise leak into the next one that happens to build the same
        # cache key.
        from django.core.cache import cache

        cache.clear()

    def _payload(self, **overrides):
        data = {
            "journey_type": "OneWay",
            "origin": "LOS",
            "destination": "LHR",
            "departure_date": "2026-09-15",
            "adults": 1,
        }
        data.update(overrides)
        return data

    def test_invalid_payload_returns_400_with_envelope(self):
        response = self.client.post(
            self.url, data=encrypt({"journey_type": "OneWay"}), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = decrypt(response.content)
        self.assertEqual(body["status"], "fail")
        self.assertEqual(body["message"], "Invalid request.")
        self.assertIn("data", body)

    def test_search_success_returns_provider_response(self):
        provider_response = {"session_id": "abc", "AirAvailabilityResponse": {}}
        with patch.object(
            FlightsLogic, "search", return_value=provider_response
        ) as mock_search:
            response = self.client.post(
                self.url, data=encrypt(self._payload()), format="json"
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.content)
        self.assertEqual(body["status"], "success")
        self.assertEqual(body["data"], provider_response)
        mock_search.assert_called_once()

    def test_search_result_is_cached_on_repeat_request(self):
        provider_response = {"session_id": "abc"}
        with patch.object(
            FlightsLogic, "search", return_value=provider_response
        ) as mock_search:
            first = self.client.post(
                self.url, data=encrypt(self._payload()), format="json"
            )
            second = self.client.post(
                self.url, data=encrypt(self._payload()), format="json"
            )

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        second_body = decrypt(second.content)
        self.assertEqual(second_body["message"], "Cached search results.")
        mock_search.assert_called_once()

    def test_search_surfaces_provider_error(self):
        with patch.object(
            FlightsLogic,
            "search",
            return_value={"Errors": {"ErrorCode": "X", "ErrorMessage": "boom"}},
        ):
            response = self.client.post(
                self.url, data=encrypt(self._payload()), format="json"
            )

        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        body = decrypt(response.content)
        self.assertEqual(body["status"], "fail")
        self.assertEqual(body["message"], "boom")
        self.assertEqual(body["data"]["ErrorCode"], "X")


class FlightRevalidateViewTests(APITestCase):
    url = "/v1/flights/revalidate/"

    def setUp(self):
        self.user = _create_user()
        self.client.force_authenticate(user=self.user)

    def test_revalidate_success(self):
        with patch.object(
            FlightsLogic, "revalidate", return_value=_revalidate_response()
        ):
            response = self.client.post(
                self.url,
                data=encrypt({"session_id": "s1", "fare_source_code": "f1"}),
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.content)
        self.assertEqual(body["status"], "success")
        self.assertTrue(body["data"]["IsValid"])

    def test_revalidate_stale_fare_returns_400(self):
        with patch.object(
            FlightsLogic,
            "revalidate",
            return_value=_revalidate_response(is_valid=False),
        ):
            response = self.client.post(
                self.url,
                data=encrypt({"session_id": "s1", "fare_source_code": "f1"}),
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = decrypt(response.content)
        self.assertEqual(body["status"], "fail")
        self.assertIn("no longer available", body["message"])


class FareRulesViewTests(APITestCase):
    url = "/v1/flights/fare-rules/"

    def setUp(self):
        self.user = _create_user()
        self.client.force_authenticate(user=self.user)

    def test_fare_rules_success(self):
        provider_response = {
            "FareRules1_1Response": {
                "FareRules1_1Result": {"BaggageInfos": [], "FareRules": []}
            }
        }
        with patch.object(FlightsLogic, "fare_rules", return_value=provider_response):
            response = self.client.post(
                self.url,
                data=encrypt({"session_id": "s1", "fare_source_code": "f1"}),
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.content)
        self.assertEqual(body["status"], "success")
        self.assertIn("BaggageInfos", body["data"])


class AirportSearchViewTests(APITestCase):
    url = "/v1/flights/airports/"

    def setUp(self):
        self.user = _create_user()
        self.client.force_authenticate(user=self.user)
        Airport.objects.create(
            airport_code="LOS",
            airport_name="Murtala Muhammed International",
            city="Lagos",
            country="Nigeria",
            country_code="NG",
        )
        Airport.objects.create(
            airport_code="LHR",
            airport_name="Heathrow",
            city="London",
            country="United Kingdom",
            country_code="GB",
        )

    def test_search_by_city(self):
        response = self.client.get(self.url, {"q": "lag"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.content)
        codes = [row["airport_code"] for row in body["data"]]
        self.assertEqual(codes, ["LOS"])

    def test_search_by_airport_code(self):
        response = self.client.get(self.url, {"q": "LHR"})
        body = decrypt(response.content)
        self.assertEqual([row["airport_code"] for row in body["data"]], ["LHR"])

    def test_query_shorter_than_two_chars_returns_empty(self):
        response = self.client.get(self.url, {"q": "l"})
        body = decrypt(response.content)
        self.assertEqual(body["data"], [])


# ---------------------------------------------------------------------------
# Views: Booking
# ---------------------------------------------------------------------------


class FlightBookingViewTests(APITestCase):
    url = "/v1/flights/book/"

    def setUp(self):
        self.user = _create_user()
        self.client.force_authenticate(user=self.user)
        self.wallet = WalletModel.objects.create(
            user=self.user,
            account_number="1234567890",
            balance="50000.00",
            walletType="INDIVIDUAL",
            pin=make_password("1234"),
        )

    def _mock_wallet_debit(self):
        return patch(
            "banking.controllers.Wallet.getWalletDetails",
            return_value=MagicMock(
                json=lambda: {
                    "status": "SUCCESS",
                    "data": {"availableBalance": 50000.00},
                }
            ),
        ), patch(
            "banking.controllers.Wallet.Debit", return_value=MagicMock(status_code=200)
        )

    def test_invalid_payload_returns_400(self):
        response = self.client.post(self.url, data=encrypt({}), format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = decrypt(response.content)
        self.assertEqual(body["message"], "Invalid request.")

    def test_guest_cannot_pay_by_wallet(self):
        self.client.force_authenticate(user=None)
        payload = _valid_booking_payload(payment_option="WALLET")
        response = self.client.post(
            self.url,
            data=encrypt(payload),
            format="json",
            HTTP_X_GUEST_ID=str(uuid.uuid4()),
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = decrypt(response.content)
        self.assertEqual(body["message"], "Guests must pay by card.")

    def test_stale_fare_blocks_booking(self):
        with patch.object(
            FlightsLogic,
            "revalidate",
            return_value=_revalidate_response(is_valid=False),
        ):
            response = self.client.post(
                self.url, data=encrypt(_valid_booking_payload()), format="json"
            )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = decrypt(response.content)
        self.assertIn("no longer available", body["message"])

    def test_wallet_booking_success(self):
        gwd, debit = self._mock_wallet_debit()
        with patch.object(
            FlightsLogic, "revalidate", return_value=_revalidate_response("1000.00")
        ), patch.object(
            FlightsLogic, "booking", return_value=_booking_success_response()
        ), patch(
            "flights.views.finalize_flight_booking.delay"
        ) as mock_delay, gwd, debit:
            response = self.client.post(
                self.url, data=encrypt(_valid_booking_payload()), format="json"
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.content)
        self.assertEqual(body["status"], "success")
        self.assertIn("booking_id", body["data"])

        booking = FlightBooking.objects.get(user=self.user)
        self.assertEqual(booking.status, "PENDING")
        self.assertEqual(booking.total_price, Decimal("1000.00"))
        tx = TxModel.objects.get(user=self.user, tx_type="Flight")
        self.assertEqual(tx.status, "SUCCESS")
        mock_delay.assert_called_once_with(str(booking.tx_reference))

    def test_wallet_booking_wrong_pin_is_rejected(self):
        with patch.object(
            FlightsLogic, "revalidate", return_value=_revalidate_response("1000.00")
        ):
            response = self.client.post(
                self.url,
                data=encrypt(_valid_booking_payload(pin="0000")),
                format="json",
            )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(FlightBooking.objects.count(), 0)

    def test_card_booking_success_skips_pin(self):
        FundWithCard.objects.create(
            user=self.user,
            txn_reference="card-ref-1",
            status="success",
            is_processed=False,
            amount="10000.00",
        )
        payload = _valid_booking_payload(
            payment_option="CARD", card_reference="card-ref-1", pin=""
        )
        with patch.object(
            FlightsLogic, "revalidate", return_value=_revalidate_response("1000.00")
        ), patch.object(
            FlightsLogic, "booking", return_value=_booking_success_response()
        ), patch(
            "flights.views.finalize_flight_booking.delay"
        ):
            response = self.client.post(self.url, data=encrypt(payload), format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(FlightBooking.objects.filter(user=self.user).count(), 1)
        tx = TxModel.objects.get(user=self.user, tx_type="Flight")
        self.assertEqual(tx.status, "SUCCESS")

    def test_provider_booking_failure_refunds_wallet_debit(self):
        gwd, debit = self._mock_wallet_debit()
        with patch.object(
            FlightsLogic, "revalidate", return_value=_revalidate_response("1000.00")
        ), patch.object(
            FlightsLogic,
            "booking",
            return_value={"Errors": {"ErrorCode": "X", "ErrorMessage": "boom"}},
        ), patch(
            "banking.controllers.Wallet.Credit", return_value=MagicMock(status_code=200)
        ) as mock_credit, gwd, debit:
            response = self.client.post(
                self.url, data=encrypt(_valid_booking_payload()), format="json"
            )

        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertEqual(FlightBooking.objects.count(), 0)
        mock_credit.assert_called_once()
        tx = TxModel.objects.get(user=self.user, tx_type="Flight")
        self.assertEqual(tx.status, "FAILED")


class FlightBookingWithPointsAndRewardsTests(APITestCase):
    """Covers the _book_with_points_or_rewards() path — cashback + points as
    payment, mirroring vas/views.py's hybrid pattern."""

    url = "/v1/flights/book/"

    def setUp(self):
        self.user = _create_user()
        self.client.force_authenticate(user=self.user)
        self.wallet = WalletModel.objects.create(
            user=self.user,
            account_number="1234567890",
            balance="0.00",
            cashback_balance="300.00",
            walletType="INDIVIDUAL",
            pin=make_password("1234"),
        )
        self.points = PointsModel.objects.create(
            user=self.user, balance=1000, tier="Champion"
        )
        self.tier_rate = TIER_VALUES["Champion"]

    def _payload(self, **overrides):
        return _valid_booking_payload(use_points=True, use_rewards=True, **overrides)

    def test_success_deducts_cashback_then_points(self):
        with patch.object(
            FlightsLogic, "revalidate", return_value=_revalidate_response("1000.00")
        ), patch.object(
            FlightsLogic, "booking", return_value=_booking_success_response()
        ), patch(
            "flights.views.finalize_flight_booking.delay"
        ):
            response = self.client.post(
                self.url, data=encrypt(self._payload()), format="json"
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.wallet.refresh_from_db()
        self.points.refresh_from_db()
        self.assertEqual(self.wallet.cashback_balance, Decimal("0.00"))

        remaining_after_cashback = Decimal("1000.00") - Decimal("300.00")
        expected_points_deducted = math.ceil(remaining_after_cashback / self.tier_rate)
        self.assertEqual(self.points.balance, 1000 - expected_points_deducted)

        tx = TxModel.objects.get(user=self.user, tx_type="Flight")
        self.assertEqual(tx.status, "SUCCESS")
        self.assertEqual(FlightBooking.objects.filter(user=self.user).count(), 1)

    def test_insufficient_points_and_rewards_blocks_booking(self):
        self.wallet.cashback_balance = Decimal("0.00")
        self.wallet.save(update_fields=["cashback_balance"])
        self.points.balance = 10
        self.points.save(update_fields=["balance"])

        with patch.object(
            FlightsLogic, "revalidate", return_value=_revalidate_response("1000.00")
        ):
            response = self.client.post(
                self.url, data=encrypt(self._payload()), format="json"
            )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = decrypt(response.content)
        self.assertIn("Insufficient points/rewards", body["message"])
        self.assertEqual(TxModel.objects.filter(user=self.user).count(), 0)
        self.assertEqual(FlightBooking.objects.count(), 0)

    def test_provider_failure_refunds_cashback_and_points(self):
        with patch.object(
            FlightsLogic, "revalidate", return_value=_revalidate_response("1000.00")
        ), patch.object(
            FlightsLogic,
            "booking",
            return_value={"Errors": {"ErrorCode": "X", "ErrorMessage": "boom"}},
        ):
            response = self.client.post(
                self.url, data=encrypt(self._payload()), format="json"
            )

        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)

        self.wallet.refresh_from_db()
        self.points.refresh_from_db()
        self.assertEqual(self.wallet.cashback_balance, Decimal("300.00"))
        self.assertEqual(self.points.balance, 1000)

        tx = TxModel.objects.get(user=self.user, tx_type="Flight")
        self.assertEqual(tx.status, "FAILED")
        self.assertEqual(FlightBooking.objects.count(), 0)

    def test_card_payment_ignores_points_and_rewards_flags(self):
        FundWithCard.objects.create(
            user=self.user,
            txn_reference="card-ref-2",
            status="success",
            is_processed=False,
            amount="10000.00",
        )
        payload = self._payload(
            payment_option="CARD", card_reference="card-ref-2", pin=""
        )
        with patch.object(
            FlightsLogic, "revalidate", return_value=_revalidate_response("1000.00")
        ), patch.object(
            FlightsLogic, "booking", return_value=_booking_success_response()
        ), patch(
            "flights.views.finalize_flight_booking.delay"
        ):
            response = self.client.post(self.url, data=encrypt(payload), format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.wallet.refresh_from_db()
        self.points.refresh_from_db()
        # Neither balance was touched — CARD path never consults points/rewards.
        self.assertEqual(self.wallet.cashback_balance, Decimal("300.00"))
        self.assertEqual(self.points.balance, 1000)


# ---------------------------------------------------------------------------
# Views: Cancel
# ---------------------------------------------------------------------------


class FlightCancelViewTests(APITestCase):
    url = "/v1/flights/cancel/"

    def setUp(self):
        self.user = _create_user()
        self.client.force_authenticate(user=self.user)
        self.booking = FlightBooking.objects.create(
            user=self.user,
            tx_reference=uuid.uuid4(),
            session_id="sess-1",
            fare_source_code="fsc-1",
            fare_type="Public",
            booking_reference="ABCDEF",
            status="SUCCESS",
            currency="NGN",
            total_price=Decimal("1000.00"),
            customer_email="jane.doe@example.com",
            customer_phone="+2348012345678",
        )

    def test_cancel_success(self):
        with patch.object(
            FlightsLogic, "cancel_booking", return_value=_cancel_response()
        ):
            response = self.client.post(
                self.url,
                data=encrypt({"booking_id": str(self.booking.tx_reference)}),
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.content)
        self.assertEqual(body["status"], "success")
        self.assertEqual(body["data"]["refund_amount"], "450.00")

        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, "CANCELLED")
        self.assertIsNotNone(self.booking.cancelled_at)

    def test_cancel_unknown_booking_returns_404(self):
        response = self.client.post(
            self.url,
            data=encrypt({"booking_id": str(uuid.uuid4())}),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_cancel_rejects_another_users_booking(self):
        other_user = _create_user()
        self.client.force_authenticate(user=other_user)
        response = self.client.post(
            self.url,
            data=encrypt({"booking_id": str(self.booking.tx_reference)}),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, "SUCCESS")

    def test_guest_can_cancel_own_booking(self):
        guest_id = uuid.uuid4()
        self.booking.user = None
        self.booking.guest_id = guest_id
        self.booking.save(update_fields=["user", "guest_id"])
        self.client.force_authenticate(user=None)

        with patch.object(
            FlightsLogic, "cancel_booking", return_value=_cancel_response()
        ):
            response = self.client.post(
                self.url,
                data=encrypt({"booking_id": str(self.booking.tx_reference)}),
                format="json",
                HTTP_X_GUEST_ID=str(guest_id),
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_cancelling_already_cancelled_booking_is_idempotent(self):
        self.booking.status = "CANCELLED"
        self.booking.save(update_fields=["status"])

        with patch.object(FlightsLogic, "cancel_booking") as mock_cancel:
            response = self.client.post(
                self.url,
                data=encrypt({"booking_id": str(self.booking.tx_reference)}),
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.content)
        self.assertIn("already cancelled", body["message"])
        mock_cancel.assert_not_called()

    def test_cannot_cancel_booking_not_yet_confirmed(self):
        self.booking.booking_reference = ""
        self.booking.status = "PENDING"
        self.booking.save(update_fields=["booking_reference", "status"])

        response = self.client.post(
            self.url,
            data=encrypt({"booking_id": str(self.booking.tx_reference)}),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = decrypt(response.content)
        self.assertIn("can't be cancelled", body["message"])

    def test_provider_declines_cancellation(self):
        with patch.object(
            FlightsLogic,
            "cancel_booking",
            return_value=_cancel_response(success=False),
        ):
            response = self.client.post(
                self.url,
                data=encrypt({"booking_id": str(self.booking.tx_reference)}),
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, "SUCCESS")


# ---------------------------------------------------------------------------
# Celery task: finalize_flight_booking
# ---------------------------------------------------------------------------


class ExtractUniqueIdTests(TestCase):
    def test_reads_unique_id_from_booking_result(self):
        response = _booking_success_response(unique_id="XYZ123")
        self.assertEqual(_extract_unique_id(response), "XYZ123")

    def test_falls_back_to_pnr(self):
        response = {"BookingResponse": {"BookingResult": {"PNR": "PNR001"}}}
        self.assertEqual(_extract_unique_id(response), "PNR001")

    def test_returns_none_when_absent(self):
        self.assertIsNone(_extract_unique_id({}))
        self.assertIsNone(
            _extract_unique_id({"BookingResponse": {"BookingResult": {}}})
        )


class FinalizeFlightBookingTaskTests(TestCase):
    def setUp(self):
        self.user = _create_user()

    def _make_booking(self, fare_type="Public", **overrides):
        defaults = dict(
            user=self.user,
            tx_reference=uuid.uuid4(),
            session_id="sess-1",
            fare_source_code="fsc-1",
            fare_type=fare_type,
            status="PENDING",
            currency="NGN",
            total_price=Decimal("1000.00"),
            customer_email="jane.doe@example.com",
            customer_phone="+2348012345678",
            provider_response=_booking_success_response(),
        )
        defaults.update(overrides)
        return FlightBooking.objects.create(**defaults)

    def test_webfare_is_marked_success_without_ticket_order(self):
        booking = self._make_booking(fare_type="WebFare")
        with patch.object(FlightsLogic, "ticket_order") as mock_ticket_order:
            finalize_flight_booking(str(booking.tx_reference))
        mock_ticket_order.assert_not_called()

        booking.refresh_from_db()
        self.assertEqual(booking.status, "SUCCESS")
        self.assertEqual(booking.booking_reference, "ABCDEF")

    def test_public_fare_tickets_via_ticket_order(self):
        booking = self._make_booking(fare_type="Public")
        with patch.object(
            FlightsLogic,
            "ticket_order",
            return_value={
                "TicketOrderResponse": {
                    "TicketOrderResult": {"Success": True, "Status": "Ticketed"}
                }
            },
        ) as mock_ticket_order:
            finalize_flight_booking(str(booking.tx_reference))

        mock_ticket_order.assert_called_once()
        booking.refresh_from_db()
        self.assertEqual(booking.status, "SUCCESS")

    def test_public_fare_ticket_failure_marks_booking_failed(self):
        booking = self._make_booking(fare_type="Public")
        with patch.object(
            FlightsLogic,
            "ticket_order",
            return_value={"Errors": {"ErrorCode": "X", "ErrorMessage": "boom"}},
        ):
            finalize_flight_booking(str(booking.tx_reference))

        booking.refresh_from_db()
        self.assertEqual(booking.status, "FAILED")

    def test_missing_unique_id_leaves_booking_pending(self):
        booking = self._make_booking(fare_type="WebFare", provider_response={})
        finalize_flight_booking(str(booking.tx_reference))

        booking.refresh_from_db()
        self.assertEqual(booking.status, "PENDING")

    def test_unknown_tx_reference_does_not_raise(self):
        finalize_flight_booking(str(uuid.uuid4()))
