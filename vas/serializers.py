from rest_framework import serializers

from .models import AirtimeTopup, DataSubscription, ElectricityBill


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


class DataSubscriptionSerilizers(serializers.ModelSerializer):
    """Serializers for airtime topup."""

    class Meta:
        model = DataSubscription
        fields = [
            "id",
            "serviceID",
            "amount",
            "phone",
            "billersCode",
            "variation_code",
        ]


class ElectricityBillSerilizers(serializers.ModelSerializer):
    """Serializers for airtime topup."""

    class Meta:
        model = ElectricityBill
        fields = [
            "id",
            "serviceID",
            "amount",
            "phone",
            "billersCode",
            "type",
            "variation_code",
        ]
