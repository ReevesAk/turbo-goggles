from django.db import models
from cloudinary.models import CloudinaryField

from decouple import config

from accounts.models import User
# Create your models here.

PARTNERS_SERVICE_CATEGORY_CHOICES = (
    ("Hotel and Accomodation", "Hotel and Accomodation"),
    ("Fast food and restaurant", "Fast food and restaurant"),
    ("Land Transport", "Land Transport"),
    ("Cooking Gas Service", "Cooking Gas Service"),
    ("Air Transport", "Air Transport"),
    ("Dubai Visa", "Dubai Visa"),
    ("Cinema and Gym", "Cinema and Gym")
)


class PartnerServices(models.Model):
    """Model for partner services."""

    users = models.ForeignKey(User, on_delete=models.CASCADE)
    service_offered = models.CharField(
        choices=PARTNERS_SERVICE_CATEGORY_CHOICES, max_length=255
    )
    service_category = models.CharField(max_length=255, null=True)


class ServiceAndCharge(models.Model):
    """Model for partner service and charge/price."""

    partner = models.ForeignKey(PartnerServices, on_delete=models.CASCADE)
    service = models.CharField(max_length=255, null=True)
    price = models.FloatField(null=True)
    description = models.TextField(null=True)

    def __str__(self):
        return f"{self.service}: {self.price}"
    

class PartnerServiceImageUploads(models.Model):
    """Model for partner service file uploads."""

    user = models.ForeignKey(
        PartnerServices, on_delete=models.CASCADE
    )
    image = CloudinaryField(null=True)
    timestamp = models.DateTimeField(default=timezone.now)

    @property
    def image_url(self):
        cloud_name = config('CLOUDINARY_CLOUD_NAME')
        return (
            f"https://res.cloudinary.com/{cloud_name}/{self.image}"
        )