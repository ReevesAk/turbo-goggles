from django.db import models

from accounts.models import User


SERVICE_ID_CHOICES = (
    ("MTN", "mtn"),
    ("Glo", "glo"),
    ("Airtel", "airtel"),
    ("Etisalat", "etisalat"),
)


class AirtimeTopup(models.Model):
    user = models.ForeignKey(to=User, null=True, on_delete=models.CASCADE)
    request_id = models.CharField(max_length=150, null=True)
    serviceID = models.CharField(choices=SERVICE_ID_CHOICES, max_length=150)
    amount = models.IntegerField()
    phone = models.IntegerField()
