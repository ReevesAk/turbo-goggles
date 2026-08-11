from basemodel import BaseModel

from decimal import Decimal

from django.db import models
from django.utils import timezone

from accounts.models import User, TxModel
from banking.encryption import encrypt_field, decrypt_field


class EncryptedCharField(models.CharField):
    """CharField that transparently encrypts/decrypts its value at the DB layer."""

    def from_db_value(self, value, expression, connection):
        return decrypt_field(value)

    def to_python(self, value):
        return decrypt_field(value)

    def get_prep_value(self, value):
        if value is None:
            return value
        return encrypt_field(value)


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

ADDRESS_VERIFICATION_STATUS = (
    ("Pending", "Pending"),
    ("Failed", "Failed"),
    ("Successful", "Successful"),
    ("Approved", "Approved"),
)


class UserKYC(models.Model):
    user = models.OneToOneField(to=User, on_delete=models.CASCADE, related_name="kyc")
    bvn = EncryptedCharField(max_length=100, null=True, unique=True)
    is_bvn_img_a_match = models.BooleanField(default=False, null=True)
    nin = EncryptedCharField(max_length=100, null=True, unique=True)
    is_nin_img_a_match = models.BooleanField(default=False, null=True)
    nin_dob = models.CharField(max_length=40, null=True)
    nin_name = models.CharField(max_length=200, null=True)
    bvn_phone = EncryptedCharField(max_length=100, null=True)


class CashbackRule(models.Model):

    SERVICE_TYPE = (
        ("airtime", "Airtime"),
        ("data", "Data"),
        ("electricity", "Electricity"),
        ("cable", "Cable"),
    )

    service_type = models.CharField(max_length=50, choices=SERVICE_TYPE)
    percentage = models.DecimalField(max_digits=5, decimal_places=2)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)


class Cashback(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    service_type = models.CharField(max_length=50)
    transaction_reference = models.CharField(max_length=120)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class WalletModel(models.Model):
    user = models.ForeignKey(
        to=User, on_delete=models.CASCADE, null=True, related_name="wallets"
    )
    transactionTrackingRef = models.CharField(max_length=50, null=True)
    account_number = models.CharField(max_length=100, null=True, db_index=True)
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
    cashback_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tier_level = models.IntegerField(default=1, null=True)
    status = models.BooleanField(default=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True)

    # PIN security fields
    pin_attempts = models.IntegerField(default=0, null=True)
    pin_locked_until = models.DateTimeField(null=True, blank=True)

    UPGRADE_STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("APPROVED", "Approved"),
        ("DECLINED", "Declined"),
    ]
    tier2_upgrade_status = models.CharField(
        max_length=10,
        choices=UPGRADE_STATUS_CHOICES,
        null=True,
        blank=True,
    )

    # Corporate wallet fields (only populated when walletType="CORPORATE")
    tax_id_no = models.CharField(max_length=50, null=True, blank=True, unique=True)
    registration_number = models.CharField(max_length=100, null=True, blank=True)
    business_type = models.CharField(max_length=60, null=True, blank=True)
    CORPORATE_STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("APPROVED", "Approved"),
        ("DECLINED", "Declined"),
    ]
    corporate_status = models.CharField(
        max_length=20,
        choices=CORPORATE_STATUS_CHOICES,
        null=True,
        blank=True,
    )
    documents = models.JSONField(null=True, blank=True)
    submission_data = models.JSONField(null=True, blank=True)


class WalletUpgrade(WalletModel):
    wallet = models.ForeignKey(
        WalletModel, on_delete=models.CASCADE, related_name="wallet_upgrade", null=True
    )

    nin = EncryptedCharField(max_length=100, null=True)
    tier = models.CharField(max_length=5, null=True, default="2")
    userPhoto = models.CharField(max_length=200, null=True)

    idType = models.CharField(max_length=50, choices=ID_TYPE, null=True)
    idNumber = models.CharField(max_length=100, null=True)
    idIssueDate = models.DateField(null=True)
    idExpiryDate = models.DateField(null=True)

    idCardFront = models.CharField(max_length=200, null=True)
    idCardBack = models.CharField(max_length=200, null=True)

    houseNumber = models.CharField(max_length=100, null=True)
    streetName = models.CharField(max_length=100, null=True)
    city = models.CharField(max_length=100, null=True)
    state = models.CharField(max_length=100, null=True)
    localGovernment = models.CharField(max_length=150, null=True)

    pep = models.CharField(max_length=10, null=True)  # API expects YES/NO text
    utilityBill = models.CharField(max_length=200, null=True)
    nearestLandmark = models.CharField(max_length=200, null=True)
    placeOfBirth = models.CharField(max_length=200, null=True)
    customerSignature = models.CharField(max_length=200, null=True)
    proofOfAddressVerification = models.FileField(
        upload_to="banking_address", max_length=200, null=True
    )


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
        max_length=30, null=True, blank=True, db_index=True
    )  # "number"
    sender_account_number = models.CharField(
        max_length=30, null=True, blank=True, db_index=True
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

    class Meta:
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["beneficiary_account_number", "created_at"]),
        ]

    def __str__(self):
        return f"Transfer {self.tx_reference} - {self.beneficiary_name or 'Unknown'}"


FUND_WITH_CARD_PURPOSE_CHOICES = (
    ("wallet_topup", "Wallet top-up"),
    ("purchase", "Purchase (spent via verify_card_payment, wallet never credited)"),
)


class FundWithCard(BaseModel):
    txn_reference = models.CharField(max_length=200, unique=True, null=True)
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="card_fundings",
    )
    status = models.CharField(max_length=100, null=True)
    email = models.EmailField(null=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2, null=True)
    is_processed = models.BooleanField(default=False)
    purpose = models.CharField(
        max_length=20,
        choices=FUND_WITH_CARD_PURPOSE_CHOICES,
        default="wallet_topup",
        help_text=(
            "Set at checkout-URL generation time (PayWithCard). Lets the "
            "Paystack webhook know whether this charge is a genuine wallet "
            "top-up (send the funding notification) or earmarked for "
            "immediate spend elsewhere via verify_card_payment (skip it - "
            "the consuming flow sends its own success notification)."
        ),
    )


class AddressVerificationModel(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="address_verifications",
    )
    reference_id = models.CharField(
        max_length=100, null=True, blank=True, unique=True
    )  # Third-party webhook reference ID
    has_verified_address = models.BooleanField(default=False)
    status = models.CharField(
        max_length=20, choices=ADDRESS_VERIFICATION_STATUS, default="Pending"
    )
    created_at = models.DateTimeField(auto_now_add=True, null=True)
