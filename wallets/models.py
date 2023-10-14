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
    bvn = models.CharField(null=True, unique=True)
    accountType = models.CharField(max_length=255, null=True)

    def __str__(self) -> str:
        return self.user


class Payouts(models.Model):
    user = models.ForeignKey(to=User, null=True, on_delete=models.CASCADE)
    business = models.CharField(max_length=255, null=True)
    sourceCurrency = models.CharField(max_length=50, null=True)
    destinationCurrency = models.CharField(max_length=50, null=True)
    virtualAccountId = models.CharField(max_length=255, null=True)
    amount = models.CharField(max_length=255, null=True)
    description = models.CharField(max_length=255, null=True)
    firstName = models.CharField(max_length=255, null=True)
    lastName = models.CharField(max_length=255, null=True)
    accountholdername = models.CharField(max_length=255, null=True)
    customerReference = models.CharField(max_length=255, null=True)
    beneficiaryWalletNumber = models.CharField(max_length=255, null=True)
    acoountType = models.CharField(max_length=255, null=True)
    accountNumber = models.CharField(max_length=255, null=True)
    bankCode = models.CharField(max_length=255, null=True)
    paymentDestination = models.CharField(max_length=255, null=True)

    def __str__(self) -> str:
        return self.description
