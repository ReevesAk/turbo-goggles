from rest_framework import serializers

from .models import AirtimeTopup, DataSubscription, ElectricityBill, TvSubscription


class AirtimeTopupSerializer(serializers.ModelSerializer):
    """Serializers for airtime topup."""

    class Meta:
        model = AirtimeTopup
        fields = [
            "id",
            "serviceID",
            "amount",
            "phone",
        ]


class DataSubscriptionSerializer(serializers.ModelSerializer):
    """Serializers for data subscription."""

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


class ElectricityBillSerializer(serializers.ModelSerializer):
    """Serializers for electriicty payment."""

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


class TvSubscriptionSerializer(serializers.ModelSerializer):
    """Serializers for tv subscription."""

    class Meta:
        model = TvSubscription
        fields = [
            "id",
            "serviceID",
            "amount",
            "phone",
            "billersCode",
            "subscription_type",
            "quantity",
            "variation_code",
        ]


class IntlAirtimeSerializer(serializers.ModelSerializer):
    """Serializers for international airtime topup."""

    class Meta:
        model = AirtimeTopup
        fields = [
            "serviceID",
            "amount",
            "phone",
            "billersCode",
            "operator_id",
            "variation_code",
            "country_code",
            "email",
            "product_type_id",
        ]
