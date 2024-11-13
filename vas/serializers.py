import uuid
from rest_framework import serializers

from .models import (
    AirtimeTopup,
    DataSubscription,
    ElectricityBill,
    TvSubscription,
    WaecRegistration,
    AccidentInsurance,
    VehicleInsurance,
    HealthInsurance,
)


def check_provider(number):
    mtn_numbers = [
        "0703",
        "0706",
        "0707",
        "0803",
        "0806",
        "0810",
        "0813",
        "0814",
        "0816",
        "0903",
        "0906",
        "0913",
    ]
    glo_numbers = ["0705", "0805", "0807", "0811", "0815", "0905"]
    airtel_numbers = ["0701", "0708", "0802", "0808", "0812", "0902", "0907", "0912"]
    etisalat_numbers = ["0809", "0817", "0818", "0908", "0909"]

    if number.startswith(tuple(mtn_numbers)):
        return "MTN"
    elif number.startswith(tuple(glo_numbers)):
        return "Glo"
    elif number.startswith(tuple(airtel_numbers)):
        return "Airtel"
    elif number.startswith(tuple(etisalat_numbers)):
        return "Etisalat"
    else:
        return "Unknown"


class AirtimeTopupSerializer(serializers.ModelSerializer):
    """Serializers for airtime topup."""

    pin = serializers.CharField(
        max_length=4, min_length=4, required=False, allow_blank=True
    )
    use_biometrics = serializers.BooleanField(write_only=True, required=False)
    payment_option = serializers.CharField(max_length=255, write_only=True)
    use_bonus = serializers.BooleanField(write_only=True, required=False)
    use_points = serializers.BooleanField(write_only=True, required=False)
    use_rewards = serializers.BooleanField(write_only=True, required=False)
    tx_reference = serializers.UUIDField(default=uuid.uuid4, read_only=False)

    class Meta:
        model = AirtimeTopup
        fields = [
            "id",  # Assuming the model has a default 'id' field.
            "serviceID",
            "amount",
            "phone",
            "pin",
            "use_biometrics",
            "payment_option",
            "use_bonus",
            "use_points",
            "use_rewards",
            "tx_reference",
        ]

    def validate(self, attrs):
        serviceID = attrs.get("serviceID", "")
        phone = attrs.get("phone", "")

        if serviceID and phone:
            provider = check_provider(phone)
            if serviceID != provider:
                raise serializers.ValidationError(
                    f"This phone number, {phone}, does not belong to the service provider, {serviceID}"
                )
        else:
            raise serializers.ValidationError("serviceID and phone number are required")

        return attrs

    def create(self, validated_data):
        # Exclude non-model fields
        validated_data.pop("pin", None)
        validated_data.pop("use_biometrics", None)
        airtime_instance = AirtimeTopup.objects.create(**validated_data)
        return airtime_instance


class DataSubscriptionSerializer(serializers.ModelSerializer):
    """Serializers for data subscription."""

    pin = serializers.CharField(
        max_length=4, min_length=4, required=False, allow_blank=True
    )
    use_biometrics = serializers.BooleanField(write_only=True, required=False)
    payment_option = serializers.CharField(max_length=255, write_only=True)
    use_bonus = serializers.BooleanField(write_only=True, required=False)
    use_points = serializers.BooleanField(write_only=True, required=False)
    use_rewards = serializers.BooleanField(write_only=True, required=False)
    tx_reference = serializers.UUIDField(default=uuid.uuid4, read_only=False)

    class Meta:
        model = DataSubscription
        fields = [
            "id",
            "payment_option",
            "serviceID",
            "amount",
            "phone",
            "billersCode",
            "variation_code",
            "pin",
            "use_biometrics",
            "use_bonus",
            "use_points",
            "use_rewards",
            "tx_reference",
        ]

    def validate(self, attrs):
        serviceID = attrs.get("serviceID", "")
        billersCode = attrs.get("billersCode", "")

        if serviceID and billersCode:
            provider_data = check_provider(billersCode)
            if serviceID != provider_data:
                raise serializers.ValidationError(
                    f"This number, {billersCode} does not belong to the service provider, {serviceID}"
                )
        else:
            serializers.ValidationError(
                "serviceID and billerscode(phone number) are required"
            )

        return attrs

    def create(self, validated_data):
        # Exclude non-model fields
        validated_data.pop("pin", None)
        validated_data.pop("use_biometrics", None)
        data_instance = DataSubscription.objects.create(**validated_data)
        return data_instance


class ElectricityBillSerializer(serializers.ModelSerializer):
    """Serializers for electriicty payment."""

    pin = serializers.CharField(
        max_length=4, min_length=4, required=False, allow_blank=True
    )
    use_biometrics = serializers.BooleanField(write_only=True, required=False)
    payment_option = serializers.CharField(max_length=255, write_only=True)
    use_bonus = serializers.BooleanField(write_only=True, required=False)
    use_points = serializers.BooleanField(write_only=True, required=False)
    use_rewards = serializers.BooleanField(write_only=True, required=False)
    tx_reference = serializers.UUIDField(default=uuid.uuid4, read_only=False)

    class Meta:
        model = ElectricityBill
        fields = [
            "id",
            "pin",
            "use_biometrics",
            "payment_option",
            "serviceID",
            "amount",
            "phone",
            "billersCode",
            "type",
            "variation_code",
            "use_bonus",
            "use_points",
            "use_rewards",
            "tx_reference",
        ]

    def create(self, validated_data):
        # Exclude non-model fields
        validated_data.pop("pin", None)
        validated_data.pop("use_biometrics", None)
        electricity_instance = ElectricityBill.objects.create(**validated_data)
        return electricity_instance


class TvSubscriptionSerializer(serializers.ModelSerializer):
    """Serializers for tv subscription."""

    pin = serializers.CharField(
        max_length=4, min_length=4, required=False, allow_blank=True
    )
    use_biometrics = serializers.BooleanField(write_only=True, required=False)
    payment_option = serializers.CharField(max_length=50, write_only=True)
    tx_reference = serializers.UUIDField(default=uuid.uuid4, read_only=False)
    use_points = serializers.BooleanField(write_only=True, required=False)
    use_rewards = serializers.BooleanField(write_only=True, required=False)

    class Meta:
        model = TvSubscription
        fields = [
            "id",
            "payment_option",
            "serviceID",
            "amount",
            "phone",
            "billersCode",
            "quantity",
            "variation_code",
            "pin",
            "use_biometrics",
            "use_points",
            "use_rewards",
            "tx_reference",
        ]

    def create(self, validated_data):
        validated_data.pop("pin", None)
        validated_data.pop("use_biometrics", None)
        return super().create(validated_data)


class WaecRegistrationSerializer(serializers.ModelSerializer):
    """Serializers for waec registration."""

    pin = serializers.CharField(
        max_length=4, min_length=4, required=False, allow_blank=True
    )
    use_biometrics = serializers.BooleanField(required=False)
    use_points = serializers.BooleanField(write_only=True, required=False)
    use_rewards = serializers.BooleanField(write_only=True, required=False)

    class Meta:
        model = WaecRegistration
        fields = [
            "id",
            "serviceID",
            "payment_option",
            "variation_code",
            "quantity",
            "phone",
            "pin",
            "use_biometrics",
            "use_points",
            "use_rewards",
            "tx_reference",
        ]

    def create(self, validated_data):
        validated_data.pop("pin", None)
        validated_data.pop("use_biometrics", None)
        return super().create(validated_data)


class VehicleInsuranceSerializer(serializers.ModelSerializer):
    """Serializers for vehicle insurance."""

    pin = serializers.CharField(
        max_length=4, min_length=4, required=False, allow_blank=True
    )
    use_biometrics = serializers.BooleanField(required=False)

    class Meta:
        model = VehicleInsurance
        fields = [
            "id",
            "payment_option",
            "billersCode",
            "variation_code",
            "phone",
            "insured_name",
            "engine_number",
            "chasis_number",
            "plate_number",
            "vehicle_make",
            "vehicle_color",
            "vehicle_model",
            "year_of_make",
            "contact_address",
            "pin",
            "use_biometrics",
            "tx_reference",
        ]


class AccidentInsuranceSerializer(serializers.ModelSerializer):
    """Serializers for accident insurance."""

    pin = serializers.CharField(
        max_length=4, min_length=4, required=False, allow_blank=True
    )
    use_biometrics = serializers.BooleanField(required=False)

    class Meta:
        model = AccidentInsurance
        fields = [
            "id",
            "payment_option",
            "billersCode",
            "variation_code",
            "phone",
            "full_name",
            "address",
            "dob",
            "next_kin_name",
            "next_kin_phone",
            "business_occupation",
            "pin",
            "use_biometrics",
            "tx_reference",
        ]


class HealthInsuranceSerializer(serializers.ModelSerializer):
    """Serializers for home cover insurance."""

    pin = serializers.CharField(
        max_length=4, min_length=4, required=False, allow_blank=True
    )
    use_biometrics = serializers.BooleanField(required=False)

    class Meta:
        model = HealthInsurance
        fields = [
            "id",
            "payment_option",
            "serviceID",
            "billersCode",
            "variation_code",
            "phone",
            "full_name",
            "address",
            "selected_hospital",
            "Passport_Photo",
            "date_of_birth",
            "extra_info",
            "pin",
            "use_biometrics",
            "tx_reference",
        ]


class VasStatusSerializer(serializers.Serializer):
    message = serializers.CharField(max_length=200)


class ProductStatusSerializer(serializers.Serializer):
    request_id = serializers.CharField(max_length=200)

    class Meta:
        model = ElectricityBill
        fields = ["request_id"]


class VerifyMeterSerializer(serializers.ModelSerializer):
    class Meta:
        model = ElectricityBill
        fields = ["serviceID", "billersCode", "type"]


class VerifyCardNumberSerializer(serializers.ModelSerializer):
    class Meta:
        model = TvSubscription
        fields = ["serviceID", "billersCode"]
