from basemodel import BaseModel

from decimal import Decimal

from django.db import models
from django.utils import timezone

from accounts.models import User, TxModel

ID_TYPE = (("1", "NIN"),)

CARD_BRAND = (("VISA", "VISA"), ("MASTERCARD", "MASTERCARD"), ("VERVE", "VERVE"))

CURRENCY = (
    ("NGN", "NGN"),
    ("USD", "USD"),
)

SEX = (
    ("0", "Male"),
    ("1", "Female"),
)


class UserKYC(models.Model):
    user = models.ForeignKey(to=User, on_delete=models.CASCADE, related_name="kyc")
    bvn = models.CharField(max_length=100, null=True, unique=True)
    nin = models.CharField(max_length=100, null=True, unique=True)
    nin_dob = models.CharField(max_length=40, null=True)
    bvn_phone = models.CharField(max_length=15, null=True)


class WalletModel(models.Model):
    user = models.OneToOneField(to=User, on_delete=models.CASCADE, null=True)
    transactionTrackingRef = models.CharField(max_length=50, null=True)
    account_number = models.CharField(max_length=100, null=True)
    otherNames = models.CharField(max_length=100, null=True)
    lastName = models.CharField(max_length=100, null=True)
    phoneNo = models.CharField(max_length=100, null=True)
    acct_name = models.CharField(max_length=100, null=True)
    walletType = models.CharField(max_length=100, null=True)
    gender = models.CharField(max_length=6, choices=SEX, null=True)
    email = models.CharField(max_length=100, null=True)
    dateOfBirth = models.CharField(max_length=100, null=True)
    address = models.CharField(max_length=150, null=True)
    active_role_on_creation = models.CharField(max_length=50, null=True)
    pin = models.CharField(max_length=155, null=True)
    balance = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00")
    )
    tier_level = models.IntegerField(default=1, null=True)
    status = models.BooleanField(default=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True)


class WalletUpgrade(WalletModel):
    wallet = models.ForeignKey(
        WalletModel, on_delete=models.CASCADE, related_name="wallet_upgrade", null=True
    )
    lga = models.CharField(max_length=100, null=True)
    state = models.CharField(max_length=100, null=True)
    nin = models.CharField(max_length=100, null=True)
    tier = models.CharField(max_length=5, null=True)
    userPhoto = models.CharField(max_length=150, null=True)
    idType = models.CharField(max_length=50, choices=ID_TYPE, null=True)
    idNumber = models.CharField(max_length=100, null=True)
    idIssueDate = models.DateField(null=True)
    idCardFront = models.CharField(max_length=150, null=True)
    houseNumber = models.CharField(max_length=100, null=True)
    streetName = models.CharField(max_length=100, null=True)
    city = models.CharField(max_length=100, null=True)
    pep = models.BooleanField(default=False, null=True)
    customerSignature = models.CharField(max_length=150, null=True)
    proofOfAddressVerification = models.CharField(max_length=150, null=True)


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
    wallet = models.ForeignKey(
        WalletModel,
        on_delete=models.CASCADE,
        related_name="wallet_ntfn",
        null=True,
        blank=True,
    )
    accountNumber = models.CharField(max_length=100, null=True)
    reference = models.CharField(max_length=150, null=True)
    narration = models.TextField(null=True)
    dateTime = models.CharField(max_length=150, null=True)
    amount = models.FloatField(null=True)
    transactionType = models.CharField(max_length=50, null=True)
    accountBalance = models.FloatField(null=True)


class TransferModel(models.Model):
    user = models.ForeignKey(
        to=User, on_delete=models.CASCADE, related_name="transfers"
    )
    tx = models.ForeignKey(
        to=TxModel,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transfers",
    )

    # Customer info
    beneficiary_bank_code = models.CharField(
        max_length=100, null=True, blank=True
    )  # "bank"
    beneficiary_account_number = models.CharField(
        max_length=30, null=True, blank=True
    )  # "number"
    sender_account_number = models.CharField(
        max_length=30, null=True, blank=True
    )  # "senderaccountnumber"
    beneficiary_name = models.CharField(max_length=150, null=True, blank=True)  # "name"
    sender_name = models.CharField(max_length=150, null=True, blank=True)

    # Order info
    amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )  # "order.amount"
    currency = models.CharField(max_length=10, default="NGN")
    description = models.TextField(null=True, blank=True)
    country = models.CharField(max_length=5, default="NG")

    # Transaction info
    tx_reference = models.CharField(max_length=100, unique=True, null=True)
    transaction_type = models.CharField(max_length=50, default="INTRA_BANK")
    narration = models.TextField(null=True, blank=True)

    # Balance tracking (optional)
    available_balance = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )

    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"Transfer {self.tx_reference} - {self.beneficiary_name or 'Unknown'}"


class FundWithCard(BaseModel):
    user = models.ForeignKey(to=User, on_delete=models.SET_NULL, null=True)
    txn_reference = models.CharField(max_length=200, null=True)
    status = models.CharField(max_length=100, null=True)
    email = models.EmailField(max_length=100, null=True)
    amount = models.FloatField(default=Decimal("0.00"))
