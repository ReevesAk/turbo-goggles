from rest_framework import serializers

from .models import (
    AirtimeTopup,
    DataSubscription,
    ElectricityBill,
    TvSubscription,
    WaecRegistration,
    Insurance,
)


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


class WaecRegistrationSerializer(serializers.ModelSerializer):
    """Serializers for waec registration."""

    class Meta:
        model = WaecRegistration
        fields = [
            "id",
            "serviceID",
            "variation_code",
            "quantity",
            "phone",
        ]


class VehicleInsuranceSerializer(serializers.ModelSerializer):
    """Serializers for vehicle insurance."""

    class Meta:
        model = Insurance
        fields = [
            "id",
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
        ]


class AccidentInsuranceSerializer(serializers.ModelSerializer):
    """Serializers for accident insurance."""

    class Meta:
        model = Insurance
        fields = [
            "id",
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
        ]


class HomeCoverInsuranceSerializer(serializers.ModelSerializer):
    """Serializers for home cover insurance."""

    class Meta:
        model = Insurance
        fields = [
            "id",
            "serviceID",
            "billersCode",
            "variation_code",
            "phone",
            "full_name",
            "address",
            "type_building",
            "date_of_birth",
            "business_occupation",
        ]
