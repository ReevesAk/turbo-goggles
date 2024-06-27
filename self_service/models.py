import uuid
from django.db import models

from basemodel import ItemPurchaseBaseModel
from accounts.models import User, PurchaseModel

TRIP_TYPE = (
    ("Local Trip", "Local Trip"),
    ("Internataional Trip", "Internataional Trip"),
    ("E-hailing", "E-hailing"),
)

TRIP_PATTERN = (("One Way", "One Way"), ("Round Trip", "Round Trip"))

PRODUCT_STATUS = (("Success", "Success"), ("Pending", "Pending"), ("Fail", "Fail"))


class TransactionStatus(models.Model):
    txn_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    status = models.CharField(
        choices=PRODUCT_STATUS, max_length=50, null=True
    )  # Success, Pending, Failed)
    details = models.TextField(blank=True, null=True)
    date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.transaction_id


class RestaurantBooking(ItemPurchaseBaseModel):
    user = models.ForeignKey(
        to=User, on_delete=models.CASCADE, related_name="restaurant"
    )
    purchase = models.ForeignKey(
        to=PurchaseModel,
        on_delete=models.CASCADE,
        related_name="restaurant_purchase",
        null=True,
    )
    name = models.CharField(max_length=155, null=True)
    table = models.CharField(max_length=155, null=True)
    number_of_seats = models.CharField(max_length=150, null=True)
    amount_per_seat = models.FloatField(null=True)
    product_tag = models.CharField(max_length=255, blank=True, null=True)
    transaction_status = models.ForeignKey(
        to=TransactionStatus, on_delete=models.SET_NULL, null=True
    )


class GymSubcription(ItemPurchaseBaseModel):
    user = models.ForeignKey(
        to=User, on_delete=models.CASCADE, related_name="gym_subcription"
    )
    purchase = models.ForeignKey(
        to=PurchaseModel,
        on_delete=models.CASCADE,
        related_name="gym_purchase",
        null=True,
    )
    name = models.CharField(max_length=155, null=True)
    personal_trainer = models.CharField(max_length=155, blank=True, null=True)
    number_of_persons = models.CharField(max_length=150, null=True)
    product_tag = models.CharField(max_length=255, blank=True, null=True)
    transaction_status = models.ForeignKey(
        to=TransactionStatus, on_delete=models.SET_NULL, null=True
    )


class CinemaBooking(ItemPurchaseBaseModel):
    user = models.ForeignKey(
        to=User, on_delete=models.CASCADE, related_name="cinema_booking"
    )
    purchase = models.ForeignKey(
        to=PurchaseModel,
        on_delete=models.CASCADE,
        related_name="cinema_purchase",
        null=True,
    )
    name = models.CharField(max_length=155, null=True)
    available_seats = models.CharField(max_length=100, null=True)
    number_of_persons = models.CharField(max_length=100, null=True)
    product_tag = models.CharField(max_length=255, blank=True, null=True)
    transaction_status = models.ForeignKey(
        to=TransactionStatus, on_delete=models.SET_NULL, null=True
    )


class CourierService(ItemPurchaseBaseModel):
    user = models.ForeignKey(
        to=User, on_delete=models.CASCADE, related_name="courier_service"
    )
    purchase = models.ForeignKey(
        to=PurchaseModel,
        on_delete=models.CASCADE,
        related_name="courier_purchase",
        null=True,
    )
    pickup = models.CharField(max_length=155, null=True)
    destination = models.CharField(max_length=155, null=True)
    price_per_kg = models.CharField(max_length=155, null=True)
    product_tag = models.CharField(max_length=255, blank=True, null=True)
    transaction_status = models.ForeignKey(
        to=TransactionStatus, on_delete=models.SET_NULL, null=True
    )


class ConsumableService(ItemPurchaseBaseModel):
    user = models.ForeignKey(
        to=User, on_delete=models.CASCADE, related_name="consumable_services"
    )
    purchase = models.ForeignKey(
        to=PurchaseModel,
        on_delete=models.CASCADE,
        related_name="comsumable_purchase",
        null=True,
    )
    price = models.CharField(max_length=155, null=True)
    contact = models.CharField(max_length=155, null=True)
    product_tag = models.CharField(max_length=255, blank=True, null=True)
    transaction_status = models.ForeignKey(
        to=TransactionStatus, on_delete=models.SET_NULL, null=True
    )


class LandTravels(ItemPurchaseBaseModel):
    user = models.ForeignKey(
        to=User, on_delete=models.CASCADE, related_name="land_travels"
    )
    purchase = models.ForeignKey(
        to=PurchaseModel,
        on_delete=models.CASCADE,
        related_name="landtravel_purchase",
        null=True,
    )
    trip_date = models.DateField(null=True, blank=True)
    return_date = models.DateField(null=True, blank=True)
    departure_state = models.CharField(max_length=150, null=True)
    terminal = models.CharField(max_length=150, null=True)
    destination = models.CharField(max_length=150, null=True)
    no_of_adults = models.CharField(max_length=150, null=True)
    no_of_children = models.CharField(max_length=150, null=True)
    trip_type = models.CharField(choices=TRIP_TYPE, max_length=100, null=True)
    trip_pattern = models.CharField(choices=TRIP_PATTERN, max_length=100, null=True)
    product_tag = models.CharField(max_length=255, blank=True, null=True)
    transaction_status = models.ForeignKey(
        to=TransactionStatus, on_delete=models.SET_NULL, null=True
    )


class Hotels(ItemPurchaseBaseModel):
    user = models.ForeignKey(to=User, on_delete=models.CASCADE, related_name="hotel")
    purchase = models.ForeignKey(
        to=PurchaseModel,
        on_delete=models.CASCADE,
        related_name="hotel_purchase",
        null=True,
    )
    amount = models.FloatField(null=True)
    product_tag = models.CharField(max_length=255, blank=True, null=True)
    transaction_status = models.ForeignKey(
        to=TransactionStatus, on_delete=models.SET_NULL, null=True
    )


class ProductTag(models.Model):
    user = models.ForeignKey(to=User, on_delete=models.CASCADE)
    tag = models.CharField(max_length=155, null=True)

    def __str__(self):
        return self.tag
