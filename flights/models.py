from django.core.serializers.json import DjangoJSONEncoder
from django.db import models

from accounts.models import User
from basemodel import ItemPurchaseBaseModel

STATUS_CHOICES = (
    ("PENDING", "PENDING"),
    ("SUCCESS", "SUCCESS"),
    ("FAILED", "FAILED"),
    ("CANCELLED", "CANCELLED"),
)

FARE_TYPE_CHOICES = (
    ("WebFare", "WebFare"),
    ("Public", "Public"),
    ("Private", "Private"),
)


class FlightBooking(ItemPurchaseBaseModel):
    user = models.ForeignKey(to=User, null=True, on_delete=models.CASCADE)
    guest_id = models.UUIDField(null=True, blank=True)
    tx_reference = models.CharField(max_length=100, unique=True, editable=False)

    session_id = models.CharField(max_length=255, null=True, blank=True)
    fare_source_code = models.TextField(null=True, blank=True)
    fare_type = models.CharField(choices=FARE_TYPE_CHOICES, max_length=20, null=True)
    booking_reference = models.CharField(max_length=100, null=True, blank=True)

    status = models.CharField(choices=STATUS_CHOICES, max_length=20, default="PENDING")

    currency = models.CharField(max_length=10, null=True, blank=True)
    total_price = models.DecimalField(max_digits=12, decimal_places=2, null=True)
    refund_amount = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)

    customer_email = models.EmailField()
    customer_phone = models.CharField(max_length=20)

    segments = models.JSONField(default=list, encoder=DjangoJSONEncoder)
    passengers = models.JSONField(default=list, encoder=DjangoJSONEncoder)
    provider_response = models.JSONField(
        default=dict, encoder=DjangoJSONEncoder, blank=True
    )

    def __str__(self):
        return f"FlightBooking {self.booking_reference or self.tx_reference} for {self.customer_email}"


class Airport(models.Model):
    airport_code = models.CharField(max_length=10, unique=True, db_index=True)
    airport_name = models.CharField(max_length=255, null=True, blank=True)
    city = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    country = models.CharField(max_length=100, null=True, blank=True)
    country_code = models.CharField(max_length=10, null=True, blank=True)
    latitude = models.CharField(max_length=50, null=True, blank=True)
    longitude = models.CharField(max_length=50, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.airport_code} - {self.airport_name}"
