# Third party imports.
from rest_framework import serializers

from accounts.models import TxModel

# In project imports.
from .models import (
    BVNData,
    AccountCreation,
    BankingNotificationModel,
    TransferModel,
    FundWithCard,
)


class BankingStatusSerializer(serializers.Serializer):
    message = serializers.CharField(max_length=200)


class QuotationSerializer(serializers.Serializer):
    message = serializers.CharField(max_length=200)


class BVNSerializer(serializers.ModelSerializer):
    """Serailizers for our verify user bvn."""

    class Meta:
        model = BVNData
        fields = [
            "id",
            "bvn",
            "date_of_birth",
        ]


class BankAccountCreationSerializers(serializers.ModelSerializer):
    """Serailizers for creating a bank account for users."""

    passport = serializers.URLField(required=True)
    identity = serializers.URLField(required=True)
    utility = serializers.URLField(required=True)
    signature = serializers.URLField(required=True)
    tc = serializers.CharField(max_length=4, write_only=True, required=True)
    gn = serializers.CharField(max_length=4, write_only=True, required=True)
    bvn = serializers.CharField(max_length=20, write_only=True, required=True)
    accountType = serializers.CharField(max_length=4, write_only=True, required=True)
    ms = serializers.CharField(max_length=4, write_only=True, required=True)
    country = serializers.CharField(max_length=100, write_only=True, required=True)
    alt_email = serializers.CharField(max_length=100, write_only=True, required=True)
    alt_phone = serializers.CharField(max_length=100, write_only=True, required=True)

    class Meta:
        model = AccountCreation
        fields = [
            "id",
            "lga",
            "state",
            "tc",
            "bvn",
            "gn",
            "accountType",
            "country",
            "ms",
            "alt_email",
            "alt_phone",
            "religion",
            "nin",
            "sex",
            "address",
            "utility",
            "passport",
            "identity",
            "signature",
        ]


class CreateWalletPinSerializer(serializers.ModelSerializer):
    """Serailizers for first time wallet pin setting."""

    pin2 = serializers.CharField(max_length=4, write_only=True, required=True)

    class Meta:
        model = AccountCreation
        fields = ["id", "pin", "pin2"]


class VerifyPinOTPSerializer(serializers.Serializer):
    otp = serializers.CharField()


class ResetPinSerializer(serializers.ModelSerializer):
    otp = serializers.CharField(max_length=50, min_length=4)
    pin2 = serializers.CharField(max_length=4, write_only=True, required=True)

    class Meta:
        model = AccountCreation
        fields = ("otp", "pin", "pin2")


class TxModelSerializer(serializers.ModelSerializer):
    class Meta:
        model = TxModel
        fields = [
            "tx_reference",
            "tx_type",
            "tx_id",
            "amount",
            "description",
            "rwd",
            "date",
        ]


class BankNtfnSerializer(serializers.ModelSerializer):
    class Meta:
        model = BankingNotificationModel
        fields = [
            "accountNumber",
            "reference",
            "narration",
            "dateTime",
            "amount",
            "transactionType",
            "accountBalance",
        ]


class AccountDetailsSerializer(serializers.ModelSerializer):
    balance = serializers.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        model = AccountCreation
        fields = [
            "acct_name",
            "account_number",
            "customer_numnber",
            "balance",
        ]


class GetProvidusAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = AccountCreation
        fields = [
            "account_number",
        ]

    def validate_accountNumber(self, value):
        """Validate the account number format."""
        if (
            not value.isdigit() or len(value) != 10
        ):  # Assuming a 10-digit account number
            raise serializers.ValidationError(
                "Account number must be a 10-digit number."
            )
        return value


class GetAccountSerializer(serializers.ModelSerializer):
    bankCode = serializers.CharField(min_length=3, write_only=True, required=True)

    class Meta:
        model = AccountCreation
        fields = ["account_number", "bankCode"]

    def validate_accountNumber(self, value):
        """Validate the account number format."""
        if (
            not value.isdigit() or len(value) != 10
        ):  # Assuming a 10-digit account number
            raise serializers.ValidationError(
                "Account number must be a 10-digit number."
            )
        return value

    def validate_bankCode(self, value):
        """Validate the bank code format."""
        if not value.isdigit() or not (
            3 <= len(value) <= 6
        ):  # Bank code must be between 3 and 6 digits
            raise serializers.ValidationError(
                "Bank code must be a number between 3 and 6 digits."
            )
        return value


class IntraBankTransfersSerializer(serializers.ModelSerializer):
    transaction_reference = serializers.CharField(
        max_length=50, write_only=True, required=True
    )
    narration = serializers.CharField(max_length=50, write_only=True, required=True)
    credit_account = serializers.CharField(
        max_length=50, write_only=True, required=True
    )
    debit_account = serializers.CharField(max_length=50, write_only=True, required=True)
    pin = serializers.CharField(max_length=4, write_only=True, required=True)
    use_biometrics = serializers.BooleanField(required=False)

    class Meta:
        model = TransferModel
        fields = [
            "id",
            "pin",
            "use_biometrics",
            "credit_account",
            "debit_account",
            "narration",
            "transaction_amount",
            "transaction_reference",
        ]


class InterBankTransfersSerializer(serializers.ModelSerializer):
    transaction_reference = serializers.CharField(
        max_length=50, write_only=True, required=True
    )
    narration = serializers.CharField(max_length=50, write_only=True, required=True)
    pin = serializers.CharField(max_length=4, write_only=True, required=True)
    use_biometrics = serializers.BooleanField(required=False)

    class Meta:
        model = TransferModel
        fields = [
            "id",
            "pin",
            "use_biometrics",
            "beneficiary_account_name",
            "beneficiary_account_number",
            "beneficiary_bank",
            "source_account_name",
            "narration",
            "transaction_amount",
            "transaction_reference",
        ]


class GetTransferStatusSerializer(serializers.Serializer):
    class Meta:
        fields = [
            "transaction_reference",
        ]


class WalletStatusSerializer(serializers.ModelSerializer):
    status = serializers.SerializerMethodField()

    class Meta:
        model = AccountCreation
        fields = [
            "account_number",
            "acct_name",
            "balance",
            "status",
            "created_at",
        ]

    def get_status(self, obj):
        return "Open" if obj.status else "Blocked"


class PaymentURLSerializers(serializers.ModelSerializer):
    class Meta:
        model = FundWithCard
        fields = ["id", "amount", "email"]


class VerifyCardDepositSerializers(serializers.ModelSerializer):
    class Meta:
        model = FundWithCard
        fields = ["id", "txn_reference"]


class RefundSerializers(serializers.ModelSerializer):
    guest_id = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = FundWithCard
        fields = ["guest_id", "txn_reference"]


class CustomerSerializer(serializers.Serializer):
    email = serializers.EmailField()


class DataSerializer(serializers.Serializer):
    id = serializers.CharField()
    reference = serializers.CharField()
    customer = CustomerSerializer()
    status = serializers.CharField()
    amount = serializers.IntegerField()


class WebhookSerializer(serializers.Serializer):
    event = serializers.CharField()
    data = DataSerializer()


class FundWalletSerializers(serializers.Serializer):
    class Meta:
        model = FundWithCard
        fields = ["id", "amount", "email", "tx_ref"]
