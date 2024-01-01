# Third party imports.
from rest_framework import serializers

# In project imports.
from accounts.models import User
from .models import BVNData, Address, Wallet


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
            "identity_expiration"
        ]


class CreateWalletPinSerializer(serializers.ModelSerializer):
    """Serailizers for first time wallet pin setting."""

    pin2 = serializers.CharField(max_length=4, min_length=6, write_only=True)

    class Meta:
        model = Wallet
        fields = ["id", "pin", "pin2"]

