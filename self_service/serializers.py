from rest_framework import serializers

from .models import RestaurantBooking, GymSubcription, CinemaBooking


class RestaurantBookingSerilaizers(serializers.ModelSerializer):
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
            "token"
        ]


class GymSubcriptionSerilaizers(serializers.ModelSerializer):
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
            "token"
        ]


class CinemaBookingSerilaizers(serializers.ModelSerializer):
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
            "token"
        ]
