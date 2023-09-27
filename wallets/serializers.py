# Third party imports.
from rest_framework import serializers

# In project imports.
from .models import CreateWallet


class CreateWalletSerializer(serializers.ModelSerializer):
    """Serailizers for our Partners' first time registration"""

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
        first_name = attrs.get("first_name", "")
        last_name = attrs.get("last_name", "")
        currency = attrs.get("currency", "")
        channel = attrs.get("channel", "")
        accountInformation = attrs.get("accountInformation", "")
        accountNumber = attrs.get("accountNumber", "")
        accountType = attrs.get("accountType", "")
        bvn = attrs.get("bvn", "")

        if not bvn or bvn == 0:
            raise serializers.ValidationError("bvn is incomplete")

        return super().validate(attrs)
