from django.db import models
import uuid

from basemodel import ItemPurchaseBaseModel
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
    ("Prepaid", "prepaid"),
    ("Postpaid", "postpaid"),
)

TV_SERVICE_ID_CHOICES = (
    ("dstv", "dstv"),
    ("gotv", "gotv"),
    ("startimes", "startimes"),
    ("showmax", "showmax"),
)

ELECTRICITY_SERVICE_ID_CHOICES = (
    ("ikeja-electric", "ikeja-electric"),
    ("eko-electric", "eko-electric"),
    ("kano-electric", "kano-electric"),
    ("portharcourt-electric", "portharcourt-electric"),
    ("jos-electric", "jos-electric"),
    ("ibadan-electric", "ibadan-electric"),
    ("kaduna-electric", "kaduna-electric"),
    ("abuja-electric", "abuja-electric"),
    ("enugu-electric", "enugu-electric"),
    ("benin-electric", "benin-electric"),
    ("aba-electric", "aba-electric"),
    ("yola-electric", "yola-electric"),
)


class AirtimeTopup(ItemPurchaseBaseModel):
    user = models.ForeignKey(to=User, null=True, on_delete=models.CASCADE)
    tx_reference = models.UUIDField(default=uuid.uuid4, editable=False)
    request_id = models.CharField(max_length=150, null=True)
    serviceID = models.CharField(
        choices=AIRTIME_SERVICE_ID_CHOICES, max_length=150, null=True
    )
    amount = models.CharField(max_length=150, null=True)
    product_type_id = models.CharField(max_length=150, null=True)
    phone = models.CharField(max_length=150, null=True)


class DataSubscription(ItemPurchaseBaseModel):
    user = models.ForeignKey(to=User, null=True, on_delete=models.CASCADE)
    tx_reference = models.UUIDField(default=uuid.uuid4, editable=False)
    request_id = models.CharField(max_length=150, null=True)
    serviceID = models.CharField(
        choices=DATA_SERVICE_ID_CHOICES, max_length=150, null=True
    )
    billersCode = models.CharField(max_length=150, null=True)
    variation_code = models.CharField(max_length=150, null=True)
    amount = models.CharField(max_length=150, null=True)
    phone = models.CharField(max_length=150, null=True)


class ElectricityBill(ItemPurchaseBaseModel):
    user = models.ForeignKey(to=User, null=True, on_delete=models.CASCADE)
    tx_reference = models.UUIDField(default=uuid.uuid4, editable=False)
    request_id = models.CharField(max_length=150, null=True)
    serviceID = models.CharField(
        choices=ELECTRICITY_SERVICE_ID_CHOICES, max_length=150, null=True
    )
    billersCode = models.CharField(max_length=150, null=True)
    type = models.CharField(choices=METER_TYPE_CHOICES, max_length=150, null=True)
    variation_code = models.CharField(max_length=150, null=True)
    amount = models.CharField(max_length=150, null=True)
    phone = models.CharField(max_length=150, null=True)


class TvSubscription(ItemPurchaseBaseModel):
    user = models.ForeignKey(to=User, null=True, on_delete=models.CASCADE)
    tx_reference = models.UUIDField(default=uuid.uuid4, editable=False)
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


class WaecRegistration(ItemPurchaseBaseModel):
    user = models.ForeignKey(to=User, null=True, on_delete=models.CASCADE)
    tx_reference = models.UUIDField(default=uuid.uuid4, editable=False)
    request_id = models.CharField(max_length=150, null=True)
    serviceID = models.CharField(max_length=150, null=True)
    amount = models.CharField(max_length=150, null=True)
    variation_code = models.CharField(max_length=150, null=True)
    quantity = models.CharField(max_length=150, null=True)
    phone = models.CharField(max_length=150, null=True)


class AccidentInsurance(ItemPurchaseBaseModel):
    user = models.ForeignKey(to=User, null=True, on_delete=models.CASCADE)
    tx_reference = models.UUIDField(default=uuid.uuid4, editable=False)
    request_id = models.CharField(max_length=150, null=True)
    serviceID = models.CharField(max_length=150, null=True)
    billersCode = models.CharField(max_length=150, null=True)
    variation_code = models.CharField(max_length=150, null=True)
    phone = models.CharField(max_length=150, null=True)
    full_name = models.CharField(max_length=250, null=True)
    address = models.CharField(max_length=250, null=True)
    dob = models.DateField(max_length=250, null=True)
    next_kin_name = models.CharField(max_length=250, null=True)
    next_kin_phone = models.CharField(max_length=250, null=True)
    business_occupation = models.CharField(max_length=250, null=True)


class VehicleInsurance(ItemPurchaseBaseModel):
    user = models.ForeignKey(to=User, null=True, on_delete=models.CASCADE)
    tx_reference = models.UUIDField(default=uuid.uuid4, editable=False)
    request_id = models.CharField(max_length=150, null=True)
    serviceID = models.CharField(max_length=150, null=True)
    billersCode = models.CharField(max_length=150, null=True)
    variation_code = models.CharField(max_length=150, null=True)
    phone = models.CharField(max_length=150, null=True)
    insured_name = models.CharField(max_length=200, null=True)
    engine_number = models.CharField(max_length=200, null=True)
    chasis_number = models.CharField(max_length=200, null=True)
    plate_number = models.CharField(max_length=200, null=True)
    vehicle_make = models.CharField(max_length=200, null=True)
    vehicle_color = models.CharField(max_length=200, null=True)
    vehicle_model = models.CharField(max_length=200, null=True)
    year_of_make = models.CharField(max_length=200, null=True)
    contact_address = models.CharField(max_length=200, null=True)


class HealthInsurance(ItemPurchaseBaseModel):
    user = models.ForeignKey(to=User, null=True, on_delete=models.CASCADE)
    tx_reference = models.UUIDField(default=uuid.uuid4, editable=False)
    request_id = models.CharField(max_length=150, null=True)
    serviceID = models.CharField(max_length=150, null=True)
    billersCode = models.CharField(max_length=150, null=True)
    variation_code = models.CharField(max_length=150, null=True)
    phone = models.CharField(max_length=150, null=True)
    full_name = models.CharField(max_length=250, null=True)
    address = models.CharField(max_length=250, null=True)
    selected_hospital = models.CharField(max_length=250, null=True)
    Passport_Photo = models.CharField(max_length=250, null=True)
    date_of_birth = models.CharField(max_length=250, null=True)
    extra_info = models.CharField(max_length=255, null=True)
