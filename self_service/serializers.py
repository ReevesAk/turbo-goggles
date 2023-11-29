from rest_framework import serializers

from .models import RestaurantBooking, GymSubcription


class RestaurantBookingSerilaizers(serializers.ModelSerializer):
    "serializers for booking a restaurant table."

    pin = serializers.CharField(max_length=4, min_length=6, write_only=True)
    amount = serializers.CharField(max_length=4, min_length=6, write_only=True)

    class Meta:
        model = RestaurantBooking
        fields = ["id", "name", "table", "amount", "number_of_seats", "pin"]


class GymSubcriptionSerilaizers(serializers.ModelSerializer):
    "serializers for subscribing to a gym."

    pin = serializers.CharField(max_length=4, min_length=6, write_only=True)
    amount = serializers.CharField(max_length=4, min_length=6, write_only=True)

    class Meta:
        model = GymSubcription
        fields = [
            "id",
            "name",
            "personal_trainer",
            "amount",
            "number_of_persons",
            "pin",
        ]
