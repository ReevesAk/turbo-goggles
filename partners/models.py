
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
    ("Distribution", "Distribution")
    ("Land Transport", "Land Transport"),
    ("Cooking Gas Service", "Cooking Gas Service"),
    ("Courier Service", "Courier Service"),
    ("Air Travel", "Air Travel"),
    ("Dubai Visa", "Dubai Visa"),   
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
    

class Wallet(models.Model):
    user = models.OneToOneField(
        User, null=True, on_delete=models.CASCADE)
    currency = models.CharField(max_length=50, default='NGN')
    created_at = models.DateTimeField(default=timezone.now, null=True)


    def __str__(self):
        return self.user.__str__()
    

class WalletTransaction(models.Model):

    TRANSACTION_TYPES = (
        ('deposit', 'deposit'),
        ('transfer', 'transfer'),
        ('withdraw', 'withdraw'),
    )
    wallet = models.ForeignKey(Wallet, null=True, on_delete=models.CASCADE)
    transaction_type = models.CharField(
        max_length=200, null=True,  choices=TRANSACTION_TYPES)
    amount = models.DecimalField(max_digits=100, null=True, decimal_places=2)
    timestamp = models.DateTimeField(default=timezone.now, null=True)
    status = models.CharField(max_length=100, default="pending")
    paystack_payment_reference = models.CharField(max_length=100, default='', blank=True)

    def __str__(self):
        return self.wallet.user.__str__()
