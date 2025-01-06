from django.db import models
import uuid

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

    users = models.ForeignKey(to=User, on_delete=models.CASCADE, null=True)
    rc_number = models.CharField(max_length=255, null=True)
    business_name = models.CharField(max_length=255, null=True)

    def __str__(self):
        return f"{self.id}"


class PartnerServices(models.Model):
    """Model for partner services."""

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="related_services"
    )
    business = models.CharField(choices=BUSINESS_CATEGORY, max_length=255, null=True)
    service = models.CharField(max_length=255, null=True)
    service_star = models.CharField(max_length=50, null=True, blank=True)
    price = models.FloatField(null=True)
    description = models.TextField(null=True)
    from_station = models.CharField(max_length=255, null=True, blank=True)
    destination = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True)


class CustomerRating(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    service = models.ForeignKey(
        PartnerServices, on_delete=models.CASCADE, related_name="customer_rating"
    )
    rating = models.CharField(max_length=50, null=True, blank=True)
    review = models.TextField(null=True, blank=True)
    slug = models.SlugField(default="", max_length=155, null=False)


class PartnerServicePhotos(models.Model):
    """Model for partner service photos."""

    partner = models.ForeignKey(
        PartnerServices,
        on_delete=models.CASCADE,
        related_name="service_photos",
        null=True,
    )
    photo = models.CharField(max_length=255, null=True)


class AvailablePartnerGymTrainers(models.Model):
    """Model for gym partner service photos."""

    partner = models.ForeignKey(
        PartnerServices,
        on_delete=models.CASCADE,
        related_name="gym_trainers",
        null=True,
    )
    trainer_name = models.CharField(max_length=255, null=True)
    trainer_price = models.FloatField(null=True)
    trainer_photo = models.CharField(max_length=255, null=True)
