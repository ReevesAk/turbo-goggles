from django.db import models

from accounts.models import User


NGN_ID_TYPE = (
    ("NIN", "NIN"),
    ("PASSPORT", "PASSPORT"),
    ("VOTERS_CARD", "VOTERS_CARD"),
    ("DRIVERS_LICENSE", "DRIVERS_LICENSE")
)

USD_ID_TYPE = (
    ("PASSPORT", "PASSPORT"),
    ("VOTERS_CARD", "VOTERS_CARD"),
    ("DRIVERS_LICENSE", "DRIVERS_LICENSE")
)


class CustomerData(models.Model):
    user = models.ForeignKey(to=User, on_delete=models.CASCADE)
    first_name = models.CharField(max_length=255, null=True)
    last_name = models.CharField(max_length=255, null=True)
    country = models.CharField(max_length=255, null=True)
    customer_id = models.CharField(max_length=255, null=True)
    email = models.CharField(max_length=150, null=True)


class BVNData(models.Model):
    user = models.OneToOneField(to=User, null=True, on_delete=models.CASCADE)
    number = models.CharField(max_length=155, null=True, unique=True)
    first_name = models.CharField(max_length=155, null=True)
    last_name = models.CharField(max_length=155, null=True)
    date_of_birth = models.CharField(max_length=155, null=True)
    phone_number = models.CharField(max_length=15, null=True)


class Phone(models.Model):
    user = models.OneToOneField(to=CustomerData, on_delete=models.CASCADE)
    country_code = models.CharField(max_length=50, null=True)
    phone_number = models.CharField(max_length=50, null=True)


class Address(models.Model):
    user = models.ForeignKey(to=CustomerData, on_delete=models.CASCADE, related_name='banking_address')
    street = models.CharField(max_length=150, null=True)
    street2 = models.CharField(max_length=50, null=True, blank=True)
    city = models.CharField(max_length=100, null=True)
    state = models.CharField(max_length=150, null=True)
    country = models.CharField(max_length=150, null=True)
    postal_code = models.CharField(max_length=50, null=True)


class Identity(models.Model):
    user = models.ForeignKey(to=CustomerData, on_delete=models.CASCADE)
    type = models.CharField(choices=NGN_ID_TYPE,  max_length=150, null=True, default="NIN")
    image = models.CharField(max_length=150, null=True) # image url of the document.
    number = models.CharField(max_length=200, null=True) # document number.
    country = models.CharField(max_length=150, null=True)


class Wallet(models.Model):
    user = models.ForeignKey(to=User, on_delete=models.CASCADE)
    customer_id = models.CharField(max_length=200, null=True)
    bank_name = models.CharField(max_length=150, null=True)
    currency = models.CharField(max_length=150, null=True)
    occupation = models.CharField(max_length=150, null=True)
    utility_bill = models.CharField(max_length=255, null=True)
    bank_statement = models.CharField(max_length=255, null=True)
    identity_type = models.CharField(max_length=150, null=True)
    identity_number = models.CharField(max_length=200, null=True)
    identity_issued_date = models.CharField(max_length=155, null=True)
    identity_expiration = models.CharField(max_length=155, null=True)
    pin = models.CharField(max_length=50, null=True)
