from rest_framework import serializers

from .models import (
    RestaurantBooking,
    GymSubcription,
    CinemaBooking,
    CourierService,
    ConsumableService,
    LandTravels,
    Hotels,
)
from partners.models import CustomerRating


class RestaurantBookingSerializers(serializers.ModelSerializer):
    "serializers for booking a restaurant table."

    pin = serializers.CharField(
        max_length=4, min_length=4, required=False, allow_blank=True
    )
    use_biometrics = serializers.BooleanField(write_only=True, required=False)
    payment_option = serializers.CharField(max_length=255, write_only=True)
    use_points = serializers.BooleanField(write_only=True, required=False)

    class Meta:
        model = RestaurantBooking
        fields = [
            "id",
            "partner_service",
            "name",
            "table",
            "amount",
            "number_of_seats",
            "pin",
            "use_biometrics",
            "payment_option",
            "use_points",
        ]


class GymSubcriptionSerializers(serializers.ModelSerializer):
    "serializers for subscribing to a gym."

    pin = serializers.CharField(
        max_length=4, min_length=4, required=False, allow_blank=True
    )
    amount = serializers.CharField(max_length=255, write_only=True, required=True)
    use_biometrics = serializers.BooleanField(required=False)

    class Meta:
        model = GymSubcription
        fields = [
            "id",
            "partner_service",
            "name",
            "personal_trainer",
            "amount",
            "number_of_persons",
            "pin",
            "use_biometrics",
            "payment_option",
        ]


class CinemaBookingSerializers(serializers.ModelSerializer):
    "serializers for booking cinema seats."

    pin = serializers.CharField(
        max_length=4, min_length=4, required=False, allow_blank=True
    )
    amount = serializers.CharField(max_length=255, write_only=True, required=True)
    use_biometrics = serializers.BooleanField(required=False)

    class Meta:
        model = CinemaBooking
        fields = [
            "id",
            "partner_service",
            "name",
            "available_seats",
            "amount",
            "number_of_persons",
            "pin",
            "use_biometrics",
            "payment_option",
        ]


class CourierBookingSerializers(serializers.ModelSerializer):
    "serializers for booking courier service."

    pin = serializers.CharField(
        max_length=4, min_length=4, required=False, allow_blank=True
    )
    use_biometrics = serializers.BooleanField(required=False)

    class Meta:
        model = CourierService
        fields = [
            "id",
            "partner_service",
            "pickup",
            "destination",
            "price_per_kg",
            "pin",
            "use_biometrics",
            "payment_option",
        ]


class ConsumableSerializers(serializers.ModelSerializer):
    "serializers for booking consumable  service."

    class Meta:
        model = ConsumableService
        fields = ["id", "partner_service", "price", "contact"]  # contact the seller


class LandTravelsSerilaizers(serializers.ModelSerializer):
    class Meta:
        model = LandTravels
        fields = [
            "id",
            "partner_service",
            "trip_date",
            "return_date",
            "departure_state",
            "terminal",
            "destination",
            "no_of_adults",
            "no_of_children",
            "trip_type",
            "trip_pattern",
        ]


class HotelSerializers(serializers.ModelSerializer):
    class Meta:
        model = Hotels
        fields = [
            "id",
            "partner_service",
            "payment_option",
            "amount",
        ]


class CustomerRatingSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomerRating
        fields = [
            "rating",
            "review",
        ]


class GetTransactionSerializer(serializers.Serializer):
    payment_tag = serializers.CharField()
