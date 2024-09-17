from django.db import models

from accounts.models import User


NGN_ID_TYPE = (
    ("NIN", "NIN"),
    ("PASSPORT", "PASSPORT"),
    ("VOTERS_CARD", "VOTERS_CARD"),
    ("DRIVERS_LICENSE", "DRIVERS_LICENSE"),
)

USD_ID_TYPE = (
    ("PASSPORT", "PASSPORT"),
    ("VOTERS_CARD", "VOTERS_CARD"),
    ("DRIVERS_LICENSE", "DRIVERS_LICENSE"),
)

CARD_BRAND = (("VISA", "VISA"), ("MASTERCARD", "MASTERCARD"), ("VERVE", "VERVE"))

CARD_TYPE = (
    ("VIRTUAL", "VIRTUAL"),
    ("PHYSICAL", "PHYSICAL"),
)

CURRENCY = (
    ("NGN", "NGN"),
    ("USD", "USD"),
)

CARD_CURRENCY = (
    ("NGN", "NGN"),
    ("USD", "USD"),
)

INTERNATIONAL_TRANSFER_SCHEME = (
    ("DOM", "DOM"),
    ("CASHPICKUP", "CASHPICKUP"),
    ("BANKACCOUNT", "BANKACCOUNT"),
    ("MOBILEMONEY", "MOBILEMONEY"),
)


class BVNData(models.Model):
    user = models.OneToOneField(to=User, on_delete=models.CASCADE)
    number = models.CharField(max_length=155, null=True, unique=True)
    first_name = models.CharField(max_length=155, null=True)
    last_name = models.CharField(max_length=155, null=True)
    date_of_birth = models.CharField(max_length=155, null=True)
    phone_number = models.CharField(max_length=15, null=True)


class AccountCreation(models.Model):
    user = models.ForeignKey(to=User, on_delete=models.CASCADE)
    customer_id = models.CharField(max_length=200, null=True)
    bank_name = models.CharField(max_length=150, null=True)
    account_number = models.CharField(max_length=100, null=True)
    currency = models.CharField(max_length=150, null=True)
    occupation = models.CharField(max_length=150, null=True)
    utility_bill = models.CharField(max_length=255, null=True)
    bank_statement = models.CharField(max_length=255, null=True)
    identity_type = models.CharField(max_length=150, null=True)
    identity_number = models.CharField(max_length=200, null=True)
    identity_issued_date = models.CharField(max_length=155, null=True)
    identity_expiration = models.CharField(max_length=155, null=True)
    pin = models.CharField(max_length=155, null=True)


class ForexModel(models.Model):
    user = models.ForeignKey(to=User, on_delete=models.CASCADE)
    source_currency = models.CharField(
        choices=CURRENCY, default="NGN", max_length=50, null=True
    )
    target_currency = models.CharField(
        choices=CURRENCY, default="USD", max_length=50, null=True
    )
    rate = models.CharField(max_length=150, null=True)
    reference = models.CharField(max_length=150, null=True)
    amount = models.FloatField(null=True)


class BankingNotificationModel(models.Model):
    accountNumber = models.CharField(max_length=100, null=True)
    reference = models.CharField(max_length=150, null=True)
    narration = models.TextField(null=True)
    dateTime = models.CharField(max_length=150, null=True)
    amount = models.FloatField(null=True)
    transactiontype = models.CharField(max_length=50, null=True)
    accountBalance = models.FloatField(null=True)
