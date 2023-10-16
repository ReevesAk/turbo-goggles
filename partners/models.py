from decouple import config

from django.db import models
from django.utils import timezone
from cloudinary.models import CloudinaryField

from accounts.models import User

# Create your models here.

PARTNERS_SERVICE_CATEGORY_CHOICES = (
    ("Hotels", "Hotels"),
    ("Cinema", "Cinema"),
    ("Gyms", "Gyms"),
    ("Restaurant", "Restaurant"),
    ("Distribution", "Distribution"),
    ("Land Transport", "Land Transport"),
    ("Cooking Gas Service", "Cooking Gas Service"),
    ("Courier Service", "Courier Service"),
    ("Air Travel", "Air Travel"),
    ("Dubai Visa", "Dubai Visa"),
)


class VerifyCAC(models.Model):
    """Model for verifying partner business."""

    users = models.ForeignKey(to=User, on_delete=models.CASCADE)
    is_cac_verified = models.BooleanField(default=False)
    cac = models.CharField(max_length=255, null=True)
    business_name = models.CharField(max_length=255, null=True)

    def __str__(self):
        return f"{self.id}"


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

    user = models.ForeignKey(PartnerServices, on_delete=models.CASCADE)
    image = CloudinaryField(null=True)
    timestamp = models.DateTimeField(default=timezone.now)

    @property
    def image_url(self):
        cloud_name = config("CLOUDINARY_CLOUD_NAME")
        return f"https://res.cloudinary.com/{cloud_name}/{self.image}"
