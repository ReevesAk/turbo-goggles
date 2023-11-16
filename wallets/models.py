from django.db import models

from accounts.models import User


# Create your models here.
class BVNData(models.Model):
    user = models.OneToOneField(to=User, null=True, on_delete=models.CASCADE)
    number = models.CharField(max_length=155, null=True, unique=True)
    first_name = models.CharField(max_length=155, null=True)
    last_name = models.CharField(max_length=155, null=True)
    date_of_birth = models.CharField(max_length=255, null=True)
    phone_number = models.CharField(max_length=15, null=True)


class CreateWallet(models.Model):
    user = models.OneToOneField(User, null=True, on_delete=models.CASCADE)
    virtualAccountId = models.CharField(max_length=255, null=True)
    currency = models.CharField(max_length=255, null=True)
    bankName = models.CharField(max_length=255, null=True)
    first_name = models.CharField(max_length=255, null=True)
    last_name = models.CharField(max_length=255, null=True)
    accountNumber = models.CharField(max_length=255, null=True)
    accountInformation = models.TextField(null=True)
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
