from decimal import Decimal

from django.db import models
from django.utils import timezone

from basemodel import BaseModel
from accounts.models import User, TxModel

SEX = (
    ("0", "Male"),
    ("1", "Female"),
)

TRANSFER_TYPE = (
    ("INTERNAL", "Internal"),   # sub-account to sub-account within Anchor
    ("EXTERNAL", "External"),   # NIP/NIBSS to any Nigerian bank
)

TRANSFER_STATUS = (
    ("PENDING", "Pending"),
    ("SUCCESS", "Success"),
    ("FAILED", "Failed"),
)

TRANSACTION_TYPE = (
    ("CREDIT", "Credit"),
    ("DEBIT", "Debit"),
)

UPGRADE_STATUS = (
    ("PENDING", "Pending"),
    ("APPROVED", "Approved"),
)


class TreasuryAccount(models.Model):
    """
    Anchor deposit account for each user.
    Equivalent to WalletModel in banking.
    """

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="treasury_account")

    # Anchor identifiers
    anchor_customer_id = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    anchor_account_id = models.CharField(max_length=100, null=True, blank=True, db_index=True)

    # NUBAN details
    account_number = models.CharField(max_length=20, null=True, blank=True, db_index=True)
    bank_name = models.CharField(max_length=100, null=True, blank=True)
    acct_name = models.CharField(max_length=150, null=True, blank=True)

    # Balances (cached — source of truth is Anchor)
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    cashback_balance = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    # Security
    pin = models.CharField(max_length=155, null=True, blank=True)
    pin_attempts = models.IntegerField(default=0)
    pin_locked_until = models.DateTimeField(null=True, blank=True)

    # KYC / tier
    tier_level = models.IntegerField(default=1)
    tier2_upgrade_status = models.CharField(
        max_length=10, choices=UPGRADE_STATUS, null=True, blank=True
    )

    status = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} — {self.account_number or 'No account'}"


class TreasuryTransfer(models.Model):
    """
    Record of every transfer initiated through Anchor.
    Equivalent to TransferModel in banking.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="treasury_transfers")
    tx = models.ForeignKey(
        TxModel, on_delete=models.SET_NULL, null=True, blank=True, related_name="treasury_transfers"
    )

    # Anchor's own transfer/payout ID (returned in the API response)
    anchor_transfer_id = models.CharField(max_length=100, null=True, blank=True, db_index=True)

    transfer_type = models.CharField(max_length=10, choices=TRANSFER_TYPE, default="EXTERNAL")
    status = models.CharField(max_length=10, choices=TRANSFER_STATUS, default="PENDING")

    # Beneficiary
    beneficiary_account_number = models.CharField(max_length=30, null=True, blank=True, db_index=True)
    beneficiary_bank_code = models.CharField(max_length=20, null=True, blank=True)
    beneficiary_name = models.CharField(max_length=150, null=True, blank=True)

    # Sender
    sender_account_number = models.CharField(max_length=30, null=True, blank=True, db_index=True)
    sender_name = models.CharField(max_length=150, null=True, blank=True)

    # Transaction details
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    currency = models.CharField(max_length=10, default="NGN")
    narration = models.TextField(null=True, blank=True)
    tx_reference = models.CharField(max_length=100, unique=True, null=True)

    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["beneficiary_account_number", "created_at"]),
        ]

    def __str__(self):
        return f"Transfer {self.tx_reference} — {self.beneficiary_name or 'Unknown'}"


class TreasuryNotification(models.Model):
    """
    Anchor webhook events (credits and debits on sub-accounts).
    Equivalent to BankingNotificationModel in banking.
    """

    account = models.ForeignKey(
        TreasuryAccount,
        on_delete=models.CASCADE,
        related_name="notifications",
        null=True,
        blank=True,
    )
    account_number = models.CharField(max_length=20, null=True, blank=True)
    reference = models.CharField(max_length=150, null=True, blank=True)
    narration = models.TextField(null=True, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2, null=True)
    transaction_type = models.CharField(max_length=10, choices=TRANSACTION_TYPE, null=True)
    balance_after = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.transaction_type} {self.amount} on {self.account_number}"


class TreasuryCardFunding(BaseModel):
    """
    Tracks Paystack card payments that fund a user's Anchor sub-account.
    Equivalent to FundWithCard in banking.
    """

    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="treasury_card_fundings"
    )
    txn_reference = models.CharField(max_length=200, unique=True, null=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2, null=True)
    status = models.CharField(max_length=100, null=True)
    email = models.EmailField(null=True, blank=True)
    is_processed = models.BooleanField(default=False)

    def __str__(self):
        return f"CardFunding {self.txn_reference} — {self.amount}"
