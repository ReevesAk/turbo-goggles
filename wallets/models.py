from django.db import models

from accounts.models import User


# Create your models here.
class CreateWallet(models.Model):
    user = models.OneToOneField(User, null=True, on_delete=models.CASCADE)
    _id = models.CharField(max_length=255, null=True)
    currency = models.CharField(max_length=255, null=True)
    channel = models.CharField(max_length=255, null=True)
    first_name = models.CharField(max_length=255, null=True)
    last_name = models.CharField(max_length=255, null=True)
    accountNumber = models.CharField(max_length=255, null=True)
    accountInformation = models.TextField(null=True)
    bvn = models.IntegerField(null=True, unique=True)
    accountType = models.CharField(max_length=255, null=True)

    def __str__(self) -> str:
        return self.user
