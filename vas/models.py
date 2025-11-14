from django.db import models
import uuid

from basemodel import ItemPurchaseBaseModel
from accounts.models import User

NETWORK_CHOICES = (
    ("MTN", "MTN"),
    ("GLO", "GLO"),
    ("AIRTEL", "AIRTEL"),
    ("9MOBILE", "9MOBILE"),
)

DATA_SERVICE_ID_CHOICES = (
    ("mtn-data", "mtn-data"),
    ("glo-data", "glo-data"),
    ("airtel-data", "airtel-data"),
    ("etisalat-data", "etisalat-data"),
)

METER_TYPE_CHOICES = (
    ("prepaid", "prepaid"),
    ("postpaid", "postpaid"),
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


class ValueAddedServices(ItemPurchaseBaseModel):
    user = models.ForeignKey(to=User, null=True, on_delete=models.CASCADE)
    guest_id = models.UUIDField(null=True, blank=True)
    phone_number = models.CharField(max_length=150, null=True, blank=True)
    debit_account = models.CharField(max_length=20, null=True)
    network = models.CharField(choices=NETWORK_CHOICES, max_length=150, null=True)
    tx_reference = models.UUIDField(default=uuid.uuid4, editable=False)
    amount = models.CharField(max_length=150, null=True)
    product_id = models.CharField(max_length=150, null=True)
    categoryId = models.CharField(max_length=5, null=True)
    itemId = models.CharField(max_length=100, null=True)
    itemName = models.CharField(max_length=200, null=True)
    customerName = models.CharField(max_length=255, null=True)
    customerId = models.CharField(max_length=100, null=True)
    billerId = models.CharField(max_length=100, null=True)
    category_name = models.CharField(max_length=100, null=True)
    otherField = models.CharField(max_length=255, null=True, blank=True)
    status = models.CharField(max_length=50, default="pending", null=True)
