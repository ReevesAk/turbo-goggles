# Third party imports.
from rest_framework import serializers

# In project imports.
from .models import BVNData, Address, Wallet, Cards, Transfer


class BVNSerializer(serializers.Serializer):
    """Serailizers for our verify user bvn."""

    class Meta:
        model = BVNData
        fields = [
            "id",
            "bvn",
            "date_of_birth",
        ]

    def validate(self, attrs):
        bvn = attrs.get("bvn", "")

        if not bvn:
            raise serializers.ValidationError("bvn is required")

        return super().validate(attrs)


class CustomerUpgradeSerializers(serializers.ModelSerializer):
    """Serailizers for Tier1 and Tier2 customer upgrade."""

    type = serializers.CharField(max_length=150, write_only=True)
    image = serializers.CharField(max_length=150, write_only=True)
    number = serializers.CharField(max_length=100, write_only=True)
    country = serializers.CharField(max_length=68, write_only=True)
    phone = serializers.CharField(max_length=68, write_only=True)

    class Meta:
        model = Address
        fields = [
            "phone",
            "street",
            "street2",
            "city",
            "state",
            "type",
            "image",
            "number",
            "country",
            "postal_code",
        ]


class UpdateCustomerSerializers(serializers.ModelSerializer):
    """Serailizers for updating customer information.."""

    first_name = serializers.CharField(max_length=150, write_only=True)
    last_name = serializers.CharField(max_length=150, write_only=True)
    type = serializers.CharField(max_length=150, write_only=True)
    image = serializers.CharField(max_length=150, write_only=True)
    number = serializers.CharField(max_length=100, write_only=True)
    country = serializers.CharField(max_length=68, write_only=True)
    phone = serializers.CharField(max_length=68, write_only=True)

    class Meta:
        model = Address
        fields = [
            "first_name",
            "last_name",
            "phone",
            "type",
            "image",
            "number",
            "country",
        ]


class CreateUSDAccountSerializers(serializers.ModelSerializer):
    """Serailizers for creating a USD wallet."""

    class Meta:
        model = Wallet
        fields = [
            "occupation",
            "utility_bill",
            "bank_statement",
            "identity_number",
            "identity_issued_date",
            "identity_expiration",
        ]


class CreateWalletPinSerializer(serializers.ModelSerializer):
    """Serailizers for first time wallet pin setting."""

    pin2 = serializers.CharField(max_length=4, min_length=6, write_only=True)

    class Meta:
        model = Wallet
        fields = ["id", "pin", "pin2"]


class VerifyPinOTPSerializer(serializers.Serializer):
    otp = serializers.CharField()


class ResetPinSerializer(serializers.ModelSerializer):
    otp = serializers.CharField(max_length=50, min_length=4)
    pin2 = serializers.CharField(max_length=68, min_length=6, write_only=True)

    class Meta:
        model = Wallet
        fields = ("otp", "pin", "pin2")


class CreateCardSerializers(serializers.ModelSerializer):
    """Serailizers for creating an order for USD ."""

    pin = serializers.CharField(max_length=68, min_length=6, write_only=True)

    class Meta:
        model = Cards
        fields = ("pin", "type")


class FundCardSerializers(serializers.ModelSerializer):
    """Serailizers for funding a card."""

    pin = serializers.CharField(max_length=68, min_length=6, write_only=True)

    class Meta:
        model = Cards
        fields = ("pin", "amount")


class FreezeCardSerializers(serializers.ModelSerializer):
    """Serailizers for freezing a card."""

    pin = serializers.CharField(max_length=68, min_length=6, write_only=True)

    class Meta:
        model = Cards
        fields = ("pin", "amount")


class UnfreezeCardSerializers(serializers.ModelSerializer):
    """Serailizers for unfreezing a card."""

    pin = serializers.CharField(max_length=68, min_length=6, write_only=True)

    class Meta:
        model = Cards
        fields = ("pin", "amount")


class TransferWithinNigeriaSerializers(serializers.ModelSerializer):
    """Serailizers for making bank transfer within Nigeria from maplerad balance."""

    pin = serializers.CharField(max_length=68, min_length=6, write_only=True)

    class Meta:
        model = Transfer
        fields = [
            "pin",
            "bank_code",
            "acct_number",
            "amount",
            "reason",
        ]


class TransferWithinPicadailysSerializers(serializers.ModelSerializer):
    """Serailizers for making picadailys transfers."""

    pin = serializers.CharField(max_length=68, min_length=6, write_only=True)

    class Meta:
        model = Transfer
        fields = [
            "pin",
            "acct_number",
            "amount",
            "reason",
        ]


class InternationalTransfersSerializers(serializers.ModelSerializer):
    """Serailizers for making international transfers."""

    pin = serializers.CharField(max_length=68, min_length=6, write_only=True)

    class Meta:
        model = Transfer
        fields = [
            "pin",
            "acct_number",
            "amount",
            "reason",
            "postal_code",
            "id_type",
            "number",
            "issued_at",
            "issued_date",
            "expiration_date",
            "receiver_first_name",
            "receiver_last_name",
            "receiver_phone_number",
            "receiver_country",
            "receiver_address",
        ]


class BankingStatusSerializer(serializers.Serializer):
    message = serializers.CharField(max_length=200)


class VirtaulAccountDetailsSerializer(serializers.Serializer):
    message = serializers.CharField(max_length=200)


class VerifyTransferSerializer(serializers.Serializer):
    message = serializers.CharField(max_length=200)
