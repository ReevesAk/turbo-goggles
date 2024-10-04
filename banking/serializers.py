# Third party imports.
from rest_framework import serializers

from accounts.models import TxModel

# In project imports.
from .models import BVNData, AccountCreation, BankingNotificationModel, TransferModel


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

    passport = serializers.FileField(required=True)
    identity = serializers.FileField(required=True)
    utility = serializers.FileField(required=True)
    signature = serializers.FileField(required=True)
    # tc = serializers.CharField(max_length=4, write_only=True, required=True)
    # accountType = serializers.CharField(max_length=4, write_only=True, required=True)
    # ms = serializers.CharField(max_length=4, write_only=True, required=True)
    # country = serializers.CharField(max_length=4, write_only=True, required=True)
    # alt_email = serializers.CharField(max_length=4, write_only=True, required=True)
    # alt_phone = serializers.CharField(max_length=4, write_only=True, required=True)
    # currentAddress = serializers.CharField(max_length=4, write_only=True, required=True)

    class Meta:
        model = AccountCreation
        fields = [
            "id",
            "lga",
            "state",
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
            "transactiontype",
            "accountBalance",
        ]


class GetProvidusAccountSerializer(serializers.Serializer):
    class Meta:
        fields = [
            "accountNumber",
        ]


class GetAccountSerializer(serializers.Serializer):
    class Meta:
        fields = [
            "accountNumber",
            "bankCode"
        ]


class IntraBankTransfersSerializer(serializers.ModelSerializer):
    transaction_reference = serializers.CharField(max_length=50, write_only=True, required=True)
    narration = serializers.CharField(max_length=50, write_only=True, required=True)
    credit_account = serializers.CharField(max_length=50, write_only=True, required=True)
    debit_account = serializers.CharField(max_length=50, write_only=True, required=True)

    class Meta:
        model = TransferModel
        fields = [
            "id",
            "credit_account",
            "debit_account",
            "narration",
            "transaction_amount"
            "transaction_reference"
        ]


class InterBankTransfersSerializer(serializers.ModelSerializer):
    transaction_reference = serializers.CharField(max_length=50, write_only=True, required=True)
    narration = serializers.CharField(max_length=50, write_only=True, required=True)

    class Meta:
        model = TransferModel
        fields = [
            "id",
            "beneficiary_account_name",
            "beneficiary_account_number",
            "beneficiary_bank",
            "source_account_name",
            "narration",
            "transaction_amount"
            "transaction_reference"
        ]


class GetTransferStatusSerializer(serializers.Serializer):
    class Meta:
        fields = [
            "transaction_reference",
        ]
