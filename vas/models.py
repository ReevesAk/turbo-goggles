from django.db import models

from accounts.models import User


AIRTIME_SERVICE_ID_CHOICES = (
    ("MTN", "mtn"),
    ("Glo", "glo"),
    ("Airtel", "airtel"),
    ("Etisalat", "etisalat"),
    ("International recharge", "foreign-airtime"),
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
    billersCode = models.CharField(max_length=150, null=True)
    variation_code = models.CharField(max_length=150, null=True)
    operator_id = models.CharField(max_length=150, null=True)
    country_code = models.CharField(max_length=150, null=True)
    product_type_id = models.CharField(max_length=150, null=True)
    email = models.CharField(max_length=150, null=True)
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


class WaecRegistration(models.Model):
    user = models.ForeignKey(to=User, null=True, on_delete=models.CASCADE)
    request_id = models.CharField(max_length=150, null=True)
    serviceID = models.CharField(max_length=150, null=True)
    amount = models.CharField(max_length=150, null=True)
    variation_code = models.CharField(max_length=150, null=True)
    quantity = models.CharField(max_length=150, null=True)
    phone = models.CharField(max_length=150, null=True)


class Insurance(models.Model):
    user = models.ForeignKey(to=User, null=True, on_delete=models.CASCADE)
    request_id = models.CharField(max_length=150, null=True)
    serviceID = models.CharField(max_length=150, null=True)
    billersCode = models.CharField(max_length=150, null=True)
    variation_code = models.CharField(max_length=150, null=True)
    amount = models.CharField(max_length=150, null=True)
    phone = models.CharField(max_length=150, null=True)
    full_name = models.CharField(max_length=250, null=True)
    address = models.CharField(max_length=250, null=True)
    dob = models.DateField(max_length=250, null=True)
    date_of_birth = models.DateField(max_length=250, null=True)
    next_kin_name = models.CharField(max_length=250, null=True)
    next_kin_phone = models.CharField(max_length=250, null=True)
    business_occupation = models.CharField(max_length=250, null=True)
    type_building = models.CharField(max_length=250, null=True)
    Insured_Name = models.CharField(max_length=200, null=True)
    Engine_Number = models.CharField(max_length=200, null=True)
    Chasis_Number = models.CharField(max_length=200, null=True)
    Plate_Number = models.CharField(max_length=200, null=True)
    Vehicle_Make = models.CharField(max_length=200, null=True)
    Vehicle_Color = models.CharField(max_length=200, null=True)
    Vehicle_Model = models.CharField(max_length=200, null=True)
    Year_of_Make = models.CharField(max_length=200, null=True)
    Contact_Address = models.CharField(max_length=200, null=True)
