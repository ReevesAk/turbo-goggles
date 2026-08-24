from rest_framework import serializers

from .models import ValueAddedServices


class AirtimeTopupSerializer(serializers.ModelSerializer):
    """Serializers for airtime topup."""

    pin = serializers.CharField(
        max_length=4, min_length=4, required=False, allow_blank=True
    )
    use_biometrics = serializers.BooleanField(write_only=True, required=False)
    payment_option = serializers.CharField(max_length=255, write_only=True)
    card_reference = serializers.CharField(write_only=True, required=False)
    use_points = serializers.BooleanField(write_only=True, required=False)
    use_cashback = serializers.BooleanField(write_only=True, required=False)

    class Meta:
        model = ValueAddedServices
        fields = [
            "id",
            "network",
            "amount",
            "phone_number",
            "pin",
            "use_biometrics",
            "payment_option",
            "card_reference",
            "use_points",
            "use_cashback",
        ]

    def validate(self, attrs):
        return attrs

    def create(self, validated_data):

        validated_data.pop("pin", None)
        validated_data.pop("use_biometrics", None)
        validated_data.pop("use_cashback", None)
        validated_data.pop("card_reference", None)

        airtime_instance = ValueAddedServices.objects.create(**validated_data)

        return airtime_instance


class DataSubscriptionSerializer(serializers.ModelSerializer):
    """Serializers for data subscription."""

    pin = serializers.CharField(
        max_length=4, min_length=4, required=False, allow_blank=True
    )
    use_biometrics = serializers.BooleanField(write_only=True, required=False)
    payment_option = serializers.CharField(max_length=255, write_only=True)
    card_reference = serializers.CharField(write_only=True, required=False)
    use_points = serializers.BooleanField(write_only=True, required=False)
    use_cashback = serializers.BooleanField(write_only=True, required=False)

    class Meta:
        model = ValueAddedServices
        fields = [
            "id",
            "network",
            "product_id",
            "amount",
            "phone_number",
            "pin",
            "use_biometrics",
            "payment_option",
            "card_reference",
            "use_points",
            "use_cashback",
        ]

    def validate(self, attrs):
        return attrs

    def create(self, validated_data):
        # Exclude non-model fields
        validated_data.pop("pin", None)
        validated_data.pop("use_biometrics", None)
        validated_data.pop("use_cashback", None)
        validated_data.pop("card_reference", None)

        data_instance = ValueAddedServices.objects.create(**validated_data)
        return data_instance


class BillPaymentSerializer(serializers.ModelSerializer):
    """Serializers for electriicty payment."""

    pin = serializers.CharField(
        max_length=4, min_length=4, required=False, allow_blank=True
    )
    use_biometrics = serializers.BooleanField(write_only=True, required=False)
    payment_option = serializers.CharField(max_length=255, write_only=True)
    card_reference = serializers.CharField(write_only=True, required=False)
    use_points = serializers.BooleanField(write_only=True, required=False)
    use_cashback = serializers.BooleanField(write_only=True, required=False)
    customerId = serializers.CharField(required=True)
    billerId = serializers.CharField(required=True)
    itemId = serializers.CharField(required=True)
    amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=True,
        error_messages={"invalid": "Amount must be a valid number."},
    )

    class Meta:
        model = ValueAddedServices
        fields = [
            "id",
            "pin",
            "use_biometrics",
            "payment_option",
            "card_reference",
            "customerId",
            "billerId",
            "itemId",
            "amount",
            "phone_number",
            "customerName",
            "otherField",
            "use_points",
            "use_cashback",
        ]

    def create(self, validated_data):
        # Exclude non-model fields
        validated_data.pop("pin", None)
        validated_data.pop("use_biometrics", None)
        validated_data.pop("use_cashback", None)
        validated_data.pop("card_reference", None)
        utility_bill_instance = ValueAddedServices.objects.create(**validated_data)
        return utility_bill_instance


class VasStatusSerializer(serializers.Serializer):
    message = serializers.CharField(max_length=200)


class VerifyBillerSerializer(serializers.ModelSerializer):
    class Meta:
        model = ValueAddedServices
        fields = ["billerId", "customerId", "itemId", "amount"]
