# Third party imports.
from rest_framework import serializers

from accounts.models import TxModel

# In project imports.
from .models import BVNData, AccountCreation, BankingNotificationModel


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

    utility = serializers.FileField(max_length=155)
    passport = serializers.FileField(max_length=155)
    identity = serializers.FileField(max_length=155)
    signature = serializers.FileField(max_length=155)

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
