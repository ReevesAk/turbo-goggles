import uuid

from rest_framework import serializers

from basemodel import PAYMENT_OPTIONS
from .models import Airport

MAX_TRIP_LEGS = 5

FARE_TYPE_CHOICES = (
    ("WebFare", "WebFare"),
    ("Public", "Public"),
    ("Private", "Private"),
)

PASSENGER_TYPE_CHOICES = (
    ("adult", "adult"),
    ("child", "child"),
    ("infant", "infant"),
)

TITLE_CHOICES_BY_TYPE = {
    "adult": ("Mr", "Mrs", "Miss", "Lord", "Sir"),
    "child": ("Miss", "Master"),
    "infant": ("Miss", "Master"),
}

JOURNEY_TYPE_CHOICES = (
    ("OneWay", "OneWay"),
    ("Return", "Return"),
    ("MultiCity", "MultiCity"),
    ("OpenJaw", "OpenJaw"),
    ("Circle", "Circle"),
)


class FlightSearchSerializer(serializers.Serializer):
    journey_type = serializers.ChoiceField(choices=JOURNEY_TYPE_CHOICES)
    origin = serializers.CharField(required=False)
    destination = serializers.CharField(required=False)
    departure_date = serializers.DateField(required=False)
    return_date = serializers.DateField(required=False)
    legs = serializers.ListField(child=serializers.DictField(), required=False)
    adults = serializers.IntegerField(min_value=1)
    childs = serializers.IntegerField(min_value=0, default=0)
    infants = serializers.IntegerField(min_value=0, default=0)
    cabin_class = serializers.CharField(default="Economy")
    required_currency = serializers.CharField(default="NGN")

    def validate(self, attrs):
        journey_type = attrs["journey_type"]

        if journey_type == "OneWay":
            self._require(attrs, ["origin", "destination", "departure_date"])
            attrs["origin_destination_info"] = [
                self._leg(
                    attrs["origin"], attrs["destination"], attrs["departure_date"]
                )
            ]

        elif journey_type == "Return":
            self._require(
                attrs, ["origin", "destination", "departure_date", "return_date"]
            )
            attrs["origin_destination_info"] = [
                self._leg(
                    attrs["origin"], attrs["destination"], attrs["departure_date"]
                ),
                self._leg(attrs["destination"], attrs["origin"], attrs["return_date"]),
            ]

        else:  # MultiCity, OpenJaw, Circle
            legs = attrs.get("legs") or []
            if len(legs) < 2:
                raise serializers.ValidationError(
                    {"legs": f"{journey_type} requires at least 2 trip legs."}
                )
            if len(legs) > MAX_TRIP_LEGS:
                raise serializers.ValidationError(
                    {"legs": f"{journey_type} supports at most {MAX_TRIP_LEGS} legs."}
                )
            attrs["origin_destination_info"] = [
                self._leg(leg["origin"], leg["destination"], leg["departure_date"])
                for leg in legs
            ]

        return attrs

    @staticmethod
    def _require(attrs, fields):
        missing = [field for field in fields if not attrs.get(field)]
        if missing:
            raise serializers.ValidationError(
                {field: "This field is required." for field in missing}
            )

    @staticmethod
    def _leg(origin, destination, departure_date):
        return {
            "departureDate": str(departure_date),
            "airportOriginCode": origin,
            "airportDestinationCode": destination,
        }


class FlightRevalidateSerializer(serializers.Serializer):
    session_id = serializers.CharField()
    fare_source_code = serializers.CharField()


class FlightCancelSerializer(serializers.Serializer):
    booking_id = serializers.CharField()


class FareRulesSerializer(serializers.Serializer):
    session_id = serializers.CharField()
    fare_source_code = serializers.CharField()


class AirportSerializer(serializers.ModelSerializer):
    class Meta:
        model = Airport
        fields = [
            "airport_code",
            "airport_name",
            "city",
            "country",
            "country_code",
        ]


class FlightPassengerSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=PASSENGER_TYPE_CHOICES)
    title = serializers.CharField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    dob = serializers.DateField()
    nationality = serializers.CharField()
    passport_no = serializers.CharField(required=False, allow_blank=True)
    passport_issue_country = serializers.CharField(required=False, allow_blank=True)
    passport_expiry_date = serializers.DateField(required=False)

    def validate(self, attrs):
        allowed_titles = TITLE_CHOICES_BY_TYPE[attrs["type"]]
        if attrs["title"] not in allowed_titles:
            raise serializers.ValidationError(
                {
                    "title": f"{attrs['type']} title must be one of {', '.join(allowed_titles)}."
                }
            )
        return attrs


class FlightBookingSerializer(serializers.Serializer):
    session_id = serializers.CharField()
    fare_source_code = serializers.CharField()
    fare_type = serializers.ChoiceField(choices=FARE_TYPE_CHOICES)
    is_passport_mandatory = serializers.BooleanField(default=False)
    area_code = serializers.CharField(required=False, allow_blank=True, default="")
    country_code = serializers.CharField(required=False, allow_blank=True, default="")
    client_ref = serializers.CharField(required=False)
    customer_email = serializers.EmailField()
    customer_phone = serializers.CharField()
    booking_note = serializers.CharField(required=False, allow_blank=True, default="")
    passengers = FlightPassengerSerializer(many=True)

    payment_option = serializers.ChoiceField(choices=PAYMENT_OPTIONS)
    pin = serializers.CharField(required=False, allow_blank=True, write_only=True)
    use_biometrics = serializers.BooleanField(default=False)
    card_reference = serializers.CharField(required=False, allow_blank=True)
    use_points = serializers.BooleanField(default=False)
    use_rewards = serializers.BooleanField(default=False)

    def validate_passengers(self, value):
        if not value:
            raise serializers.ValidationError("At least one passenger is required.")
        if not any(passenger["type"] == "adult" for passenger in value):
            raise serializers.ValidationError(
                "At least one adult passenger is required."
            )
        return value

    def validate(self, attrs):
        if attrs.get("is_passport_mandatory"):
            missing = [
                f"passengers[{index}].{field}"
                for index, passenger in enumerate(attrs["passengers"])
                for field in (
                    "passport_no",
                    "passport_issue_country",
                    "passport_expiry_date",
                )
                if not passenger.get(field)
            ]
            if missing:
                raise serializers.ValidationError(
                    {
                        "passengers": f"Passport details are required for this fare: {', '.join(missing)}"
                    }
                )

        if not attrs.get("client_ref"):
            attrs["client_ref"] = f"PICA{uuid.uuid4().hex[:12].upper()}"

        attrs["flight_booking_info"] = {
            "flight_session_id": attrs["session_id"],
            "fare_source_code": attrs["fare_source_code"],
            "IsPassportMandatory": (
                "true" if attrs["is_passport_mandatory"] else "false"
            ),
            "fareType": attrs["fare_type"],
            "areaCode": attrs.get("area_code", ""),
            "countryCode": attrs.get("country_code", ""),
        }
        attrs["pax_info"] = self._build_pax_info(attrs)
        return attrs

    @staticmethod
    def _build_pax_info(attrs):
        grouped = {"adult": [], "child": [], "infant": []}
        for passenger in attrs["passengers"]:
            grouped[passenger["type"]].append(passenger)

        pax_type_block = {}
        for pax_type, passengers in grouped.items():
            if not passengers:
                continue
            block = {
                "title": [p["title"] for p in passengers],
                "firstName": [p["first_name"] for p in passengers],
                "lastName": [p["last_name"] for p in passengers],
                "dob": [str(p["dob"]) for p in passengers],
                "nationality": [p["nationality"] for p in passengers],
            }
            if any(p.get("passport_no") for p in passengers):
                block["passportNo"] = [p.get("passport_no", "") for p in passengers]
                block["passportIssueCountry"] = [
                    p.get("passport_issue_country", "") for p in passengers
                ]
                block["passportExpiryDate"] = [
                    (
                        str(p["passport_expiry_date"])
                        if p.get("passport_expiry_date")
                        else ""
                    )
                    for p in passengers
                ]
            pax_type_block[pax_type] = block

        return {
            "clientRef": attrs["client_ref"],
            "postCode": "",
            "customerEmail": attrs["customer_email"],
            "customerPhone": attrs["customer_phone"],
            "bookingNote": attrs.get("booking_note", ""),
            "paxDetails": [pax_type_block],
        }
