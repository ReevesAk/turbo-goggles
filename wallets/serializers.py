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


class CreateWalletPinSerializer(serializers.ModelSerializer):
    """Serailizers for our Partners' first time wallet pin creation."""

    pin2 = serializers.CharField(max_length=4, min_length=6, write_only=True)

    class Meta:
        model = CreateWallet
        fields = ["id", "pin", "pin2"]


class BankAcccPayoutSerializers(serializers.ModelSerializer):
    """Serailizers for bank account payouts."""

    pin = serializers.CharField(max_length=4, min_length=6, write_only=True)

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
            "pin",
        ]

    def validate(self, attrs):
        accountNumber = attrs.get("accountNumber", "")

        if not accountNumber or accountNumber == 0:
            raise serializers.ValidationError("accountNumber is incomplete")

        return super().validate(attrs)


class FincraPayoutSerializers(serializers.ModelSerializer):
    """Serailizers for mobile money payouts."""

    pin = serializers.CharField(max_length=4, min_length=6, write_only=True)

    class Meta:
        model = Payouts
        fields = [
            "id",
            "amount",
            "description",
            "customerReference",
            "beneficiaryWalletNumber",
            "pin",
        ]

    def validate(self, attrs):
        return super().validate(attrs)


class PicadailysPayoutSerializers(serializers.ModelSerializer):
    """Serailizers for picadilys users."""

    pin = serializers.CharField(max_length=4, min_length=6, write_only=True)

    class Meta:
        model = Payouts
        fields = [
            "id",
            "virtualAccountId",
            "amount",
            "description",
            "customerReference",
            "pin",
        ]


class ResetPinSerializer(serializers.ModelSerializer):
    otp = serializers.CharField(max_length=50, min_length=4)
    pin = serializers.CharField(max_length=68, min_length=6, write_only=True)
    pin2 = serializers.CharField(max_length=68, min_length=6, write_only=True)

    class Meta:
        model = CreateWallet
        fields = ("otp", "pin", "pin2")
