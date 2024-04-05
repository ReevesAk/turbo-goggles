from rest_framework import serializers

from .models import (
    AirtimeTopup,
    DataSubscription,
    ElectricityBill,
    TvSubscription,
    WaecRegistration,
    HomeCoverInsurance,
    AccidentInsurance,
    VehicleInsurance,
    HealthInsurance,
)


def check_provider(number):
    mtn_numbers = ["0703", "0706", "0803", "0806", "0810", "0813", "0814", "0816", "0903", "0906", "0913"]
    glo_numbers = ["0705", "0805", "0807", "0811", "0815", "0905"]
    airtel_numbers = ["0701", "0708", "0802", "0808", "0812", "0902", "0907", "0912"]
    etisalat_numbers = ["0809", "0817", "0818", "0908", "0909"]

    if number.startswith(tuple(mtn_numbers)):
        return ["mtn","mtn-data"]
    elif number.startswith(tuple(glo_numbers)):
        return ["glo", "glo-data"]
    elif number.startswith(tuple(airtel_numbers)):
        return ["airtel", "airtel-data"]
    elif number.startswith(tuple(etisalat_numbers)):
        return ["etisalat", "etisalat-data"]
    else:
        return ["Unknown"]


class AirtimeTopupSerializer(serializers.ModelSerializer):
    """Serializers for airtime topup."""

    pin = serializers.CharField(max_length=4, min_length=6, write_only=True)
    number = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
    expiryMonth = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
    expiryYear = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
    card_pin = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
    cvv = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
    tokenId = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
    token = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
    use_bonus = serializers.BooleanField(write_only=True, required=False)
    use_points = serializers.BooleanField(write_only=True, required=False)
    use_rewards = serializers.BooleanField(write_only=True, required=False)

    class Meta:
        model = AirtimeTopup
        fields = [
            "id",
            "serviceID",
            "amount",
            "phone",
            "pin",
            "payment_option",
            "number",
            "expiryMonth",
            "expiryYear",
            "card_pin",
            "cvv",
            "tokenId",
            "token",
            "use_bonus",
            "use_points",
            "use_rewards",
        ]

    def validate(self, attrs):
        serviceID = attrs.get("serviceID", "")
        number = attrs.get("number", "")

        if serviceID and number:
            provider, _ = check_provider(number)
            if serviceID != provider:
                raise serializers.ValidationError(f"This number, {number} does not belong to the service provider, {serviceID}")
        else:
            serializers.ValidationError("serviceID and phone number are required")

        return attrs

class DataSubscriptionSerializer(serializers.ModelSerializer):
    """Serializers for data subscription."""

    pin = serializers.CharField(max_length=4, min_length=6, write_only=True)
    number = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
    expiryMonth = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
    expiryYear = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
    card_pin = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
    cvv = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
    tokenId = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
    token = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
    use_bonus = serializers.BooleanField(write_only=True, required=False)
    use_points = serializers.BooleanField(write_only=True, required=False)
    use_rewards = serializers.BooleanField(write_only=True, required=False)

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
            "number",
            "expiryMonth",
            "expiryYear",
            "card_pin",
            "cvv",
            "tokenId",
            "token",
            "use_bonus",
            "use_points",
            "use_rewards",
        ]

    def validate(self, attrs):
        serviceID = attrs.get("serviceID", "")
        billersCode = attrs.get("billersCode", "")

        if serviceID and billersCode:
            _, provider_data = check_provider(billersCode)
            if serviceID != provider_data:
                raise serializers.ValidationError(f"This number, {billersCode} does not belong to the service provider, {serviceID}")
        else:
            serializers.ValidationError("serviceID and billerscode(phone number) are required")

        return attrs


class ElectricityBillSerializer(serializers.ModelSerializer):
    """Serializers for electriicty payment."""

    pin = serializers.CharField(max_length=4, min_length=6, write_only=True)
    number = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
    expiryMonth = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
    expiryYear = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
    card_pin = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
    cvv = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
    tokenId = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
    token = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
    use_bonus = serializers.BooleanField(write_only=True, required=False)
    use_points = serializers.BooleanField(write_only=True, required=False)
    use_rewards = serializers.BooleanField(write_only=True, required=False)

    class Meta:
        model = ElectricityBill
        fields = [
            "id",
            "payment_option",
            "serviceID",
            "amount",
            "phone",
            "billersCode",
            "type",
            "variation_code",
            "pin",
            "number",
            "expiryMonth",
            "expiryYear",
            "card_pin",
            "cvv",
            "tokenId",
            "token",
            "use_bonus",
            "use_points",
            "use_rewards",
        ]


class TvSubscriptionSerializer(serializers.ModelSerializer):
    """Serializers for tv subscription."""

    pin = serializers.CharField(max_length=4, min_length=6, write_only=True)
    number = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
    expiryMonth = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
    expiryYear = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
    card_pin = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
    cvv = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
    tokenId = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
    token = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
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
            "subscription_type",
            "quantity",
            "variation_code",
            "pin",
            "number",
            "expiryMonth",
            "expiryYear",
            "card_pin",
            "cvv",
            "tokenId",
            "token",
            "use_points",
            "use_rewards",
        ]


class IntlAirtimeSerializer(serializers.ModelSerializer):
    """Serializers for international airtime topup."""

    pin = serializers.CharField(max_length=4, min_length=6, write_only=True)
    number = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
    expiryMonth = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
    expiryYear = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
    card_pin = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
    cvv = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
    tokenId = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
    token = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
    use_points = serializers.BooleanField(write_only=True, required=False)
    use_rewards = serializers.BooleanField(write_only=True, required=False)

    class Meta:
        model = AirtimeTopup
        fields = [
            "payment_option",
            "serviceID",
            "amount",
            "phone",
            "billersCode",
            "operator_id",
            "variation_code",
            "country_code",
            "email",
            "product_type_id",
            "pin",
            "number",
            "expiryMonth",
            "expiryYear",
            "card_pin",
            "cvv",
            "tokenId",
            "token",
            "use_points",
            "use_rewards",
        ]


class WaecRegistrationSerializer(serializers.ModelSerializer):
    """Serializers for waec registration."""

    pin = serializers.CharField(max_length=4, min_length=6, write_only=True)
    number = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
    expiryMonth = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
    expiryYear = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
    card_pin = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
    cvv = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
    tokenId = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
    token = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
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
            "number",
            "expiryMonth",
            "expiryYear",
            "card_pin",
            "cvv",
            "tokenId",
            "token",
            "use_points",
            "use_rewards",
        ]


class VehicleInsuranceSerializer(serializers.ModelSerializer):
    """Serializers for vehicle insurance."""

    pin = serializers.CharField(max_length=4, min_length=6, write_only=True)
    number = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
    expiryMonth = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
    expiryYear = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
    card_pin = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
    cvv = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
    tokenId = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
    token = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
    use_points = serializers.BooleanField(write_only=True, required=False)
    use_rewards = serializers.BooleanField(write_only=True, required=False)

    class Meta:
        model = VehicleInsurance
        fields = [
            "id",
            "payment_option",
            "serviceID",
            "billersCode",
            "variation_code",
            "phone",
            "Insured_Name",
            "Engine_Number",
            "Chasis_Number",
            "Plate_Number",
            "Vehicle_Make",
            "Vehicle_Color",
            "Vehicle_Model",
            "Year_of_Make",
            "Contact_Address",
            "pin",
            "number",
            "expiryMonth",
            "expiryYear",
            "card_pin",
            "cvv",
            "tokenId",
            "token",
            "use_points",
            "use_rewards",
        ]


class AccidentInsuranceSerializer(serializers.ModelSerializer):
    """Serializers for accident insurance."""

    pin = serializers.CharField(max_length=4, min_length=6, write_only=True)
    number = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
    expiryMonth = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
    expiryYear = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
    card_pin = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
    cvv = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
    tokenId = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
    token = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
    use_points = serializers.BooleanField(write_only=True, required=False)
    use_rewards = serializers.BooleanField(write_only=True, required=False)

    class Meta:
        model = AccidentInsurance
        fields = [
            "id",
            "payment_option",
            "serviceID",
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
            "number",
            "expiryMonth",
            "expiryYear",
            "card_pin",
            "cvv",
            "tokenId",
            "token",
            "use_points",
            "use_rewards",
        ]


class HomeCoverInsuranceSerializer(serializers.ModelSerializer):
    """Serializers for home cover insurance."""

    pin = serializers.CharField(max_length=4, min_length=6, write_only=True)
    number = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
    expiryMonth = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
    expiryYear = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
    card_pin = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
    cvv = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
    tokenId = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
    token = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
    use_points = serializers.BooleanField(write_only=True, required=False)
    use_rewards = serializers.BooleanField(write_only=True, required=False)

    class Meta:
        model = HomeCoverInsurance
        fields = [
            "id",
            "payment_option",
            "serviceID",
            "billersCode",
            "variation_code",
            "phone",
            "full_name",
            "address",
            "date_of_birth",
            "business_occupation",
            "pin",
            "number",
            "expiryMonth",
            "expiryYear",
            "card_pin",
            "cvv",
            "tokenId",
            "token",
            "use_points",
            "use_rewards",
        ]


class HealthInsuranceSerializer(serializers.ModelSerializer):
    """Serializers for home cover insurance."""

    pin = serializers.CharField(max_length=4, min_length=6, write_only=True)
    number = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
    expiryMonth = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
    expiryYear = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
    card_pin = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
    cvv = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
    tokenId = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
    token = serializers.CharField(
        max_length=4, min_length=6, write_only=True, required=False
    )
    use_points = serializers.BooleanField(write_only=True, required=False)
    use_rewards = serializers.BooleanField(write_only=True, required=False)

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
            "number",
            "expiryMonth",
            "expiryYear",
            "card_pin",
            "cvv",
            "tokenId",
            "token",
            "use_points",
            "use_rewards",
        ]


class VasStatusSerializer(serializers.Serializer):
    message = serializers.CharField(max_length=200)
