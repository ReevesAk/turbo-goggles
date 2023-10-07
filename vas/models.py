from django.db import models

from accounts.models import User


AIRTIME_SERVICE_ID_CHOICES = (
    ("MTN", "mtn"),
    ("Glo", "glo"),
    ("Airtel", "airtel"),
    ("Etisalat", "etisalat"),
)

DATA_SERVICE_ID_CHOICES = (
    ("MTN", "mtn-data"),
    ("Glo", "glo-data"),
    ("Airtel", "airtel-data"),
    ("Etisalat", "etisalat-data"),
)


class AirtimeTopup(models.Model):
    user = models.ForeignKey(to=User, null=True, on_delete=models.CASCADE)
    request_id = models.CharField(max_length=150, null=True)
    serviceID = models.CharField(choices=AIRTIME_SERVICE_ID_CHOICES, max_length=150)
    amount = models.CharField(max_length=150, null=True)
    phone = models.CharField(max_length=150, null=True)


class DataSubscription(models.Model):
    user = models.ForeignKey(to=User, null=True, on_delete=models.CASCADE)
    request_id = models.CharField(max_length=150, null=True)
    serviceID = models.CharField(choices=DATA_SERVICE_ID_CHOICES, max_length=150)
    billersCode = models.CharField(max_length=150, null=True)
    variation_code = models.CharField(max_length=150, null=True)
    amount = models.CharField(max_length=150, null=True)
    phone = models.CharField(max_length=150, null=True)
