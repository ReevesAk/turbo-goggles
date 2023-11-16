# Third party imports.
from rest_framework import serializers

# In project imports.
from .models import CreateWallet, Payouts, BVNData


class BVNSerializer(serializers.Serializer):
    """Serailizers for our verify user bvn."""

    class Meta:
        model = BVNData
        fields = [
            "id",
            "bvn",
            "first_name",
            "last_name",
            "date_of_birth",
            "phone_number",
        ]

    def validate(self, attrs):
        bvn = attrs.get("bvn", "")

        if not bvn:
            raise serializers.ValidationError("bvn is required")

        return super().validate(attrs)


class CreateWalletSerializer(serializers.ModelSerializer):
    """Serailizers for our Partners' first time registration."""

    class Meta:
        model = CreateWallet
        fields = [
            "id",
            "virtualAccountId",
            "currency",
            "bankName",
            "accountType",
            "accountInformation",
            "accountNumber",
        ]


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
