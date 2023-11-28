from django.db import models

# Create your models here.
from accounts.models import User


class RestaurantBooking(models.Model):
    user = models.ForeignKey(
        to=User, on_delete=models.CASCADE, related_name="restaurant"
    )
    name = models.CharField(max_length=155, null=True)
    table = models.CharField(max_length=155, null=True)
    number_of_seats = models.CharField(max_length=150, null=True)
    amount_per_seat = models.FloatField(null=True)


class GymSubcription(models.Model):
    user = models.ForeignKey(
        to=User, on_delete=models.CASCADE, related_name="gym_subcription"
    )
    name = models.CharField(max_length=155, null=True)
    personal_trainer = models.CharField(max_length=155, blank=True, null=True)
    number_of_persons = models.CharField(max_length=150, null=True)
