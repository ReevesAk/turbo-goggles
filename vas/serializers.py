from rest_framework import serializers

from .models import AirtimeTopup


class AirtimeTopupSerilizers(serializers.ModelSerializer):
    """Serializers for airtime topup."""

    class Meta:
        model = AirtimeTopup
        fields = [
            "id",
            "serviceID",
            "amount",
            "phone",
        ]

    def validate(self, attrs):
        amount = attrs.get("amount", "")
        phone = attrs.get("phone", "")

        if not phone or phone < 10:
            raise serializers.ValidationError("phone number is incomplete")

        if not amount or amount < 50:
            raise serializers.ValidationError("amount cannot be less than 50")

        return super().validate(attrs)
