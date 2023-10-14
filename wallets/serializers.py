# Third party imports.
from rest_framework import serializers

# In project imports.
from .models import CreateWallet, Payouts


class CreateWalletSerializer(serializers.ModelSerializer):
    """Serailizers for our Partners' first time registration."""

    class Meta:
        model = CreateWallet
        fields = [
            "id",
            "_id",
            "first_name",
            "last_name",
            "currency",
            "channel",
            "accountType",
            "accountInformation",
            "accountNumber",
            "bvn",
        ]

    def validate(self, attrs):
        _id = attrs.get("_id", "")
        accountNumber = attrs.get("accountNumber", "")
        bvn = attrs.get("bvn", "")

        if not bvn:
            raise serializers.ValidationError("bvn is required")

        return super().validate(attrs)


class BankAcccPayoutSerializers(serializers.ModelSerializer):
    """Serailizers for bank account payouts."""

    class Meta:
        model = Payouts
        fields = [
            "id",
            "amount",
            "description",
            "firstName",
            "lastName",
            "customerReference",
            "accountNumber",
            "bankCode",
        ]

    def validate(self, attrs):
        accountNumber = attrs.get("accountNumber", "")

        if not accountNumber or accountNumber == 0:
            raise serializers.ValidationError("accountNumber is incomplete")

        return super().validate(attrs)


class FincraPayoutSerializers(serializers.ModelSerializer):
    """Serailizers for mobile money payouts."""

    class Meta:
        model = Payouts
        fields = [
            "id",
            "amount",
            "description",
            "customerReference",
            "beneficiaryWalletNumber",
        ]

    def validate(self, attrs):
        amount = attrs.get("amount", "")
        description = attrs.get("description", "")
        customerReference = attrs.get("customerReference", "")
        accountNumber = attrs.get("accountNumber", "")
        beneficiaryWalletNumber = attrs.get("beneficiaryWalletNumber", "")

        return super().validate(attrs)


class PicadailysPayoutSerializers(serializers.ModelSerializer):
    """Serailizers for picadilys users."""

    class Meta:
        model = Payouts
        fields = [
            "id",
            "virtualAccountId",
            "amount",
            "description",
            "customerReference",
        ]
