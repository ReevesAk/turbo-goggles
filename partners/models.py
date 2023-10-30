from django.db import models
from cloudinary.models import CloudinaryField

from accounts.models import User


BUSINESS_CATEGORY = (
    ("Travel and Leisure", "Travel and Leisure"),
    ("Food and Drinks", "Food and Drinks"),
    ("Fitness and Entertainment", "Fitness and Entertainment"),
    ("Delivery Services", "Delivery Services"),
    ("Consumable Services", "Consumable Services"),
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

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="related_services")
    business = models.CharField(choices=BUSINESS_CATEGORY, max_length=255, null=True)
    service = models.CharField(max_length=255, null=True)
    service_star = models.CharField(max_length=50, null=True)
    price = models.FloatField(null=True)
    description = models.TextField(null=True)
    service_photos = models.CharField(max_length=255, null=True)
    from_station = models.CharField(max_length=255, null=True)
    destination = models.CharField(max_length=255, null=True)
    trainers = models.CharField(max_length=255, null=True)
    trainer_price = models.CharField(max_length=255, null=True)
    trainer_photo = models.CharField(max_length=255, null=True)
