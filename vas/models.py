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

METER_TYPE_CHOICES = (
    ("Prepaid", "Prepaid"),
    ("Postpaid", "Postpaid"),
)

TV_SERVICE_ID_CHOICES = (
    ("dstv", "dstv"),
    ("gotv", "gotv"),
    ("startimes", "startimes"),
    ("showmax", "showmax"),
)

ELECTRICITY_SERVICE_ID_CHOICES = (
    ("IKEDC", "ikeja-electric"),
    ("EKEDC", "eko-electric"),
    ("KEDCO", "kano-electric"),
    ("PHED", "portharcourt-electric"),
    ("JED", "jos-electric"),
    ("IBEDC", "ibadan-electric"),
    ("KAEDCO", "kaduna-electric"),
    ("AEDC", "abuja-electric"),
    ("EEDC", "enugu-electric"),
    ("BEDC", "benin-electric"),
)


class AirtimeTopup(models.Model):
    user = models.ForeignKey(to=User, null=True, on_delete=models.CASCADE)
    request_id = models.CharField(max_length=150, null=True)
    serviceID = models.CharField(
        choices=AIRTIME_SERVICE_ID_CHOICES, max_length=150, null=True
    )
    amount = models.CharField(max_length=150, null=True)
    phone = models.CharField(max_length=150, null=True)


class DataSubscription(models.Model):
    user = models.ForeignKey(to=User, null=True, on_delete=models.CASCADE)
    request_id = models.CharField(max_length=150, null=True)
    serviceID = models.CharField(
        choices=DATA_SERVICE_ID_CHOICES, max_length=150, null=True
    )
    billersCode = models.CharField(max_length=150, null=True)
    variation_code = models.CharField(max_length=150, null=True)
    amount = models.CharField(max_length=150, null=True)
    phone = models.CharField(max_length=150, null=True)


class ElectricityBill(models.Model):
    user = models.ForeignKey(to=User, null=True, on_delete=models.CASCADE)
    request_id = models.CharField(max_length=150, null=True)
    serviceID = models.CharField(
        choices=ELECTRICITY_SERVICE_ID_CHOICES, max_length=150, null=True
    )
    billersCode = models.CharField(
        choices=METER_TYPE_CHOICES, max_length=150, null=True
    )
    type = models.CharField(max_length=150, null=True)
    variation_code = models.CharField(max_length=150, null=True)
    amount = models.CharField(max_length=150, null=True)
    phone = models.CharField(max_length=150, null=True)


class TvSubscription(models.Model):
    user = models.ForeignKey(to=User, null=True, on_delete=models.CASCADE)
    request_id = models.CharField(max_length=150, null=True)
    serviceID = models.CharField(
        choices=TV_SERVICE_ID_CHOICES, max_length=150, null=True
    )
    billersCode = models.CharField(max_length=150, null=True)
    subscription_type = models.CharField(max_length=150, null=True)
    variation_code = models.CharField(max_length=150, null=True)
    quantity = models.CharField(max_length=150, null=True)
    amount = models.CharField(max_length=150, null=True)
    phone = models.CharField(max_length=150, null=True)
