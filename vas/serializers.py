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


class AirtimeTopupSerializer(serializers.ModelSerializer):
    """Serializers for airtime topup."""

    pin = serializers.CharField(max_length=4, min_length=6, write_only=True)
    number = serializers.CharField(max_length=4, min_length=6, write_only=True)
    expiryMonth = serializers.CharField(max_length=4, min_length=6, write_only=True)
    expiryYear = serializers.CharField(max_length=4, min_length=6, write_only=True)
    card_pin = serializers.CharField(max_length=4, min_length=6, write_only=True)
    cvv = serializers.CharField(max_length=4, min_length=6, write_only=True)
    tokenId = serializers.CharField(max_length=4, min_length=6, write_only=True)
    token = serializers.CharField(max_length=4, min_length=6, write_only=True)

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
            "token"
        ]


class DataSubscriptionSerializer(serializers.ModelSerializer):
    """Serializers for data subscription."""

    pin = serializers.CharField(max_length=4, min_length=6, write_only=True)
    number = serializers.CharField(max_length=4, min_length=6, write_only=True)
    expiryMonth = serializers.CharField(max_length=4, min_length=6, write_only=True)
    expiryYear = serializers.CharField(max_length=4, min_length=6, write_only=True)
    card_pin = serializers.CharField(max_length=4, min_length=6, write_only=True)
    cvv = serializers.CharField(max_length=4, min_length=6, write_only=True)
    tokenId = serializers.CharField(max_length=4, min_length=6, write_only=True)
    token = serializers.CharField(max_length=4, min_length=6, write_only=True)

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
            "token"
        ]


class ElectricityBillSerializer(serializers.ModelSerializer):
    """Serializers for electriicty payment."""

    pin = serializers.CharField(max_length=4, min_length=6, write_only=True)
    number = serializers.CharField(max_length=4, min_length=6, write_only=True)
    expiryMonth = serializers.CharField(max_length=4, min_length=6, write_only=True)
    expiryYear = serializers.CharField(max_length=4, min_length=6, write_only=True)
    card_pin = serializers.CharField(max_length=4, min_length=6, write_only=True)
    cvv = serializers.CharField(max_length=4, min_length=6, write_only=True)
    tokenId = serializers.CharField(max_length=4, min_length=6, write_only=True)
    token = serializers.CharField(max_length=4, min_length=6, write_only=True)

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
            "token"
        ]


class TvSubscriptionSerializer(serializers.ModelSerializer):
    """Serializers for tv subscription."""

    pin = serializers.CharField(max_length=4, min_length=6, write_only=True)
    number = serializers.CharField(max_length=4, min_length=6, write_only=True)
    expiryMonth = serializers.CharField(max_length=4, min_length=6, write_only=True)
    expiryYear = serializers.CharField(max_length=4, min_length=6, write_only=True)
    card_pin = serializers.CharField(max_length=4, min_length=6, write_only=True)
    cvv = serializers.CharField(max_length=4, min_length=6, write_only=True)
    tokenId = serializers.CharField(max_length=4, min_length=6, write_only=True)
    token = serializers.CharField(max_length=4, min_length=6, write_only=True)

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
            "token"
        ]


class IntlAirtimeSerializer(serializers.ModelSerializer):
    """Serializers for international airtime topup."""

    pin = serializers.CharField(max_length=4, min_length=6, write_only=True)
    number = serializers.CharField(max_length=4, min_length=6, write_only=True)
    expiryMonth = serializers.CharField(max_length=4, min_length=6, write_only=True)
    expiryYear = serializers.CharField(max_length=4, min_length=6, write_only=True)
    card_pin = serializers.CharField(max_length=4, min_length=6, write_only=True)
    cvv = serializers.CharField(max_length=4, min_length=6, write_only=True)
    tokenId = serializers.CharField(max_length=4, min_length=6, write_only=True)
    token = serializers.CharField(max_length=4, min_length=6, write_only=True)

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
            "token"
        ]


class WaecRegistrationSerializer(serializers.ModelSerializer):
    """Serializers for waec registration."""

    pin = serializers.CharField(max_length=4, min_length=6, write_only=True)
    number = serializers.CharField(max_length=4, min_length=6, write_only=True)
    expiryMonth = serializers.CharField(max_length=4, min_length=6, write_only=True)
    expiryYear = serializers.CharField(max_length=4, min_length=6, write_only=True)
    card_pin = serializers.CharField(max_length=4, min_length=6, write_only=True)
    cvv = serializers.CharField(max_length=4, min_length=6, write_only=True)
    tokenId = serializers.CharField(max_length=4, min_length=6, write_only=True)
    token = serializers.CharField(max_length=4, min_length=6, write_only=True)

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
            "token"
        ]


class VehicleInsuranceSerializer(serializers.ModelSerializer):
    """Serializers for vehicle insurance."""

    pin = serializers.CharField(max_length=4, min_length=6, write_only=True)
    number = serializers.CharField(max_length=4, min_length=6, write_only=True)
    expiryMonth = serializers.CharField(max_length=4, min_length=6, write_only=True)
    expiryYear = serializers.CharField(max_length=4, min_length=6, write_only=True)
    card_pin = serializers.CharField(max_length=4, min_length=6, write_only=True)
    cvv = serializers.CharField(max_length=4, min_length=6, write_only=True)
    tokenId = serializers.CharField(max_length=4, min_length=6, write_only=True)
    token = serializers.CharField(max_length=4, min_length=6, write_only=True)

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
            "token"
        ]


class AccidentInsuranceSerializer(serializers.ModelSerializer):
    """Serializers for accident insurance."""

    pin = serializers.CharField(max_length=4, min_length=6, write_only=True)
    number = serializers.CharField(max_length=4, min_length=6, write_only=True)
    expiryMonth = serializers.CharField(max_length=4, min_length=6, write_only=True)
    expiryYear = serializers.CharField(max_length=4, min_length=6, write_only=True)
    card_pin = serializers.CharField(max_length=4, min_length=6, write_only=True)
    cvv = serializers.CharField(max_length=4, min_length=6, write_only=True)
    tokenId = serializers.CharField(max_length=4, min_length=6, write_only=True)
    token = serializers.CharField(max_length=4, min_length=6, write_only=True)

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
            "token"
        ]


class HomeCoverInsuranceSerializer(serializers.ModelSerializer):
    """Serializers for home cover insurance."""

    pin = serializers.CharField(max_length=4, min_length=6, write_only=True)
    number = serializers.CharField(max_length=4, min_length=6, write_only=True)
    expiryMonth = serializers.CharField(max_length=4, min_length=6, write_only=True)
    expiryYear = serializers.CharField(max_length=4, min_length=6, write_only=True)
    card_pin = serializers.CharField(max_length=4, min_length=6, write_only=True)
    cvv = serializers.CharField(max_length=4, min_length=6, write_only=True)
    tokenId = serializers.CharField(max_length=4, min_length=6, write_only=True)
    token = serializers.CharField(max_length=4, min_length=6, write_only=True)

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
            "token"
        ]


class HealthInsuranceSerializer(serializers.ModelSerializer):
    """Serializers for home cover insurance."""

    pin = serializers.CharField(max_length=4, min_length=6, write_only=True)
    number = serializers.CharField(max_length=4, min_length=6, write_only=True)
    expiryMonth = serializers.CharField(max_length=4, min_length=6, write_only=True)
    expiryYear = serializers.CharField(max_length=4, min_length=6, write_only=True)
    card_pin = serializers.CharField(max_length=4, min_length=6, write_only=True)
    cvv = serializers.CharField(max_length=4, min_length=6, write_only=True)
    tokenId = serializers.CharField(max_length=4, min_length=6, write_only=True)
    token = serializers.CharField(max_length=4, min_length=6, write_only=True)

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
            "token"
        ]


class VasStatusSerializer(serializers.Serializer):
    message = serializers.CharField(max_length=200)
