from django.db import models

from basemodel import ItemPurchaseBaseModel
from accounts.models import User

TRIP_TYPE = (
    ("Local Trip", "Local Trip"),
    ("Internataional Trip", "Internataional Trip"),
    ("E-hailing", "E-hailing"),
)

TRIP_PATTERN = (("One Way", "One Way"), ("Round Trip", "Round Trip"))


class RestaurantBooking(ItemPurchaseBaseModel):
    user = models.ForeignKey(
        to=User, on_delete=models.CASCADE, related_name="restaurant"
    )
    name = models.CharField(max_length=155, null=True)
    table = models.CharField(max_length=155, null=True)
    number_of_seats = models.CharField(max_length=150, null=True)
    amount_per_seat = models.FloatField(null=True)


class GymSubcription(ItemPurchaseBaseModel):
    user = models.ForeignKey(
        to=User, on_delete=models.CASCADE, related_name="gym_subcription"
    )
    name = models.CharField(max_length=155, null=True)
    personal_trainer = models.CharField(max_length=155, blank=True, null=True)
    number_of_persons = models.CharField(max_length=150, null=True)


class CinemaBooking(ItemPurchaseBaseModel):
    user = models.ForeignKey(
        to=User, on_delete=models.CASCADE, related_name="cinema_booking"
    )
    name = models.CharField(max_length=155, null=True)
    available_seats = models.CharField(max_length=100, null=True)
    number_of_persons = models.CharField(max_length=100, null=True)


class CourierService(ItemPurchaseBaseModel):
    user = models.ForeignKey(
        to=User, on_delete=models.CASCADE, related_name="courier_service"
    )
    pickup = models.CharField(max_length=155, null=True)
    destination = models.CharField(max_length=155, null=True)
    price_per_kg = models.CharField(max_length=155, null=True)


class ConsumableService(ItemPurchaseBaseModel):
    user = models.ForeignKey(
        to=User, on_delete=models.CASCADE, related_name="consumable_services"
    )
    price = models.CharField(max_length=155, null=True)
    contact = models.CharField(max_length=155, null=True)


class LandTravels(ItemPurchaseBaseModel):
    user = models.ForeignKey(
        to=User, on_delete=models.CASCADE, related_name="land_travels"
    )
    trip_date = models.DateField()
    departure_state = models.CharField(max_length=150, null=True)
    terminal = models.CharField(max_length=150, null=True)
    destination = models.CharField(max_length=150, null=True)
    no_of_adults = models.CharField(max_length=150, null=True)
    no_of_children = models.CharField(max_length=150, null=True)
    trip_type = models.CharField(choices=TRIP_TYPE, max_length=100, null=True)
    trip_pattern = models.CharField(choices=TRIP_PATTERN, max_length=100, null=True)


class Hotels(ItemPurchaseBaseModel):
    user = models.ForeignKey(
        to=User, on_delete=models.CASCADE, related_name="hotel"
    )
    amount = models.FloatField(null=True)
