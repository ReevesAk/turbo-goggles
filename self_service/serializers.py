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

    pin = serializers.CharField(max_length=4, min_length=6, write_only=True)
    amount = serializers.CharField(max_length=4, min_length=6, write_only=True)
    number = serializers.CharField(max_length=4, min_length=6, write_only=True)
    expiryMonth = serializers.CharField(max_length=4, min_length=6, write_only=True)
    expiryYear = serializers.CharField(max_length=4, min_length=6, write_only=True)
    card_pin = serializers.CharField(max_length=4, min_length=6, write_only=True)
    cvv = serializers.CharField(max_length=4, min_length=6, write_only=True)
    tokenId = serializers.CharField(max_length=4, min_length=6, write_only=True)
    token = serializers.CharField(max_length=4, min_length=6, write_only=True)

    class Meta:
        model = RestaurantBooking
        fields = [
            "id",
            "name",
            "table",
            "amount",
            "number_of_seats",
            "pin",
            "payment_option",
            "number",
            "expiryMonth",
            "expiryYear",
            "card_pin",
            "cvv",
            "tokenId",
            "token",
        ]


class GymSubcriptionSerializers(serializers.ModelSerializer):
    "serializers for subscribing to a gym."

    pin = serializers.CharField(max_length=4, min_length=6, write_only=True)
    amount = serializers.CharField(max_length=4, min_length=6, write_only=True)
    number = serializers.CharField(max_length=4, min_length=6, write_only=True)
    expiryMonth = serializers.CharField(max_length=4, min_length=6, write_only=True)
    expiryYear = serializers.CharField(max_length=4, min_length=6, write_only=True)
    card_pin = serializers.CharField(max_length=4, min_length=6, write_only=True)
    cvv = serializers.CharField(max_length=4, min_length=6, write_only=True)
    tokenId = serializers.CharField(max_length=4, min_length=6, write_only=True)
    token = serializers.CharField(max_length=4, min_length=6, write_only=True)

    class Meta:
        model = GymSubcription
        fields = [
            "id",
            "name",
            "personal_trainer",
            "amount",
            "number_of_persons",
            "pin",
            "payment_option",
            "number",
            "expiryMonth",
            "expiryYear",
            "card_pin",
            "cvv",
            "tokenId",
            "token",
        ]


class CinemaBookingSerializers(serializers.ModelSerializer):
    "serializers for booking cinema seats."

    pin = serializers.CharField(max_length=4, min_length=6, write_only=True)
    amount = serializers.CharField(max_length=4, min_length=6, write_only=True)
    number = serializers.CharField(max_length=4, min_length=6, write_only=True)
    expiryMonth = serializers.CharField(max_length=4, min_length=6, write_only=True)
    expiryYear = serializers.CharField(max_length=4, min_length=6, write_only=True)
    card_pin = serializers.CharField(max_length=4, min_length=6, write_only=True)
    cvv = serializers.CharField(max_length=4, min_length=6, write_only=True)
    tokenId = serializers.CharField(max_length=4, min_length=6, write_only=True)
    token = serializers.CharField(max_length=4, min_length=6, write_only=True)

    class Meta:
        model = CinemaBooking
        fields = [
            "id",
            "name",
            "available_seats",
            "amount",
            "number_of_persons",
            "pin",
            "payment_option",
            "number",
            "expiryMonth",
            "expiryYear",
            "card_pin",
            "cvv",
            "tokenId",
            "token",
        ]


class CourierBookingSerializers(serializers.ModelSerializer):
    "serializers for booking courier service."

    pin = serializers.CharField(max_length=4, min_length=6, write_only=True)
    number = serializers.CharField(max_length=4, min_length=6, write_only=True)
    expiryMonth = serializers.CharField(max_length=4, min_length=6, write_only=True)
    expiryYear = serializers.CharField(max_length=4, min_length=6, write_only=True)
    card_pin = serializers.CharField(max_length=4, min_length=6, write_only=True)
    cvv = serializers.CharField(max_length=4, min_length=6, write_only=True)
    tokenId = serializers.CharField(max_length=4, min_length=6, write_only=True)
    token = serializers.CharField(max_length=4, min_length=6, write_only=True)

    class Meta:
        model = CourierService
        fields = [
            "id",
            "pickup",
            "destination",
            "price_per_kg",
            "pin",
            "payment_option",
            "number",
            "expiryMonth",
            "expiryYear",
            "card_pin",
            "cvv",
            "tokenId",
            "token",
        ]


class ConsumableSerializers(serializers.ModelSerializer):
    "serializers for booking consumable  service."

    class Meta:
        model = ConsumableService
        fields = ["id", "price", "contact"]  # contact the seller


class LandTravelsSerilaizers(serializers.ModelSerializer):
    class Meta:
        model = LandTravels
        fields = [
            "id",
            "trip_date",
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


class GetTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = None
        fields = ["payment_tag"]
