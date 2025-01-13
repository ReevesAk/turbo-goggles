from django.urls import path
from .views import (
    ProductStatus,
    AirTimeTopUp,
    GetNetworkProvidersVaritaionCodes,
    DataSubscriptionView,
    VerifyMeterNumber,
    ElectrcityBillPayment,
    ElectricityServiceIDListView,
    CableServiceIDListView,
    GetTvVaritaionCodes,
    VerifySmartCardNumber,
    NewTvSubscription,
    RenewTvSubscription,
    GetWaecVaritaionCodes,
    WaecRegistration,
    GetVehicleInsuranceVaritaionCodes,
    GetVehicleInsuranceModelCodes,
    GetVehicleInsuranceMakeCodes,
    GetVehicleInsuranceAreaCodes,
    GetVehicleInsuranceStateCodes,
    GetVehicleEngineCapacityCodes,
    GetVehicleInsuranceColorCodes,
    VehicleInsuranceView,
    GetAccidentVaritaionCodes,
    AccidentInsuranceView,
    GetHealthInsuranceVaritaionCodes,
    GetHealthInsuranceOptions,
    HealthInsuranceView,
)


app_name = "vas"


urlpatterns = [
    path("product-status", ProductStatus.as_view(), name="check_product_status"),
    path(
        "airtime-topup",
        AirTimeTopUp.as_view(),
        name="airtime_topup",
    ),
    path(
        "get-variation-codes/<str:service_ID>/",
        GetNetworkProvidersVaritaionCodes.as_view(),
        name="variation_codes",
    ),
    path("subscribe-data", DataSubscriptionView.as_view(), name="data_subscription"),
    path(
        "electricty-serviceIds",
        ElectricityServiceIDListView.as_view(),
        name="electricity_serviceIds",
    ),
    path("verify-meter-no", VerifyMeterNumber.as_view(), name="verify-meter"),
    path(
        "pay-electricity-bill",
        ElectrcityBillPayment.as_view(),
        name="pay_electric_bill",
    ),
    path(
        "cableTv-serviceIds",
        CableServiceIDListView.as_view(),
        name="cableTv_serviceIds",
    ),
    path(
        "get-tv-variation-codes/<str:service_ID>/",
        GetTvVaritaionCodes.as_view(),
        name="tv_variation_codes",
    ),
    path(
        "verify-smart-card-no",
        VerifySmartCardNumber.as_view(),
        name="verify_smart_card",
    ),
    path("new-tv-subscription", NewTvSubscription.as_view(), name="new_subscription"),
    path("renew-exisitng-tv-plan", RenewTvSubscription.as_view(), name="renew-tv-sub"),
    path("waec-variation-codes/", GetWaecVaritaionCodes.as_view(), name="waec_codes"),
    path("waec-registration/", WaecRegistration.as_view(), name="waec_registration"),
    path(
        "vehicle-insurance-codes/",
        GetVehicleInsuranceVaritaionCodes.as_view(),
        name="vehicle_insurance_codes",
    ),
    path(
        "vehicle-model-codes/<str:vehicle_make_code>/",
        GetVehicleInsuranceModelCodes.as_view(),
        name="vehicle_model_codes",
    ),
    path(
        "vehicle-make-codes",
        GetVehicleInsuranceMakeCodes.as_view(),
        name="vehicle_make_codes",
    ),
    path(
        "vehicle-state-codes",
        GetVehicleInsuranceStateCodes.as_view(),
        name="vehicle_state_codes",
    ),
    path(
        "vehicle-area-codes/<str:state_code>/",
        GetVehicleInsuranceAreaCodes.as_view(),
        name="vehicle_insurance_codes",
    ),
    path(
        "vehicle-capacity-codes",
        GetVehicleEngineCapacityCodes.as_view(),
        name="vehicle_capacity_codes",
    ),
    path(
        "vehicle-color-codes",
        GetVehicleInsuranceColorCodes.as_view(),
        name="vehicle_color_codes",
    ),
    path("insure-vehicle/", VehicleInsuranceView.as_view(), name="insure_vehicle"),
    path(
        "accident-insurance-codes/",
        GetAccidentVaritaionCodes.as_view(),
        name="accident_insurance_codes",
    ),
    path(
        "accident-insuracnce/",
        AccidentInsuranceView.as_view(),
        name="accident_insurance",
    ),
    path(
        "health-insurance-codes",
        GetHealthInsuranceVaritaionCodes.as_view(),
        name="health_insurance_codes",
    ),
    path(
        "health-insurance-options",
        GetHealthInsuranceOptions.as_view(),
        name="health_insurance_options",
    ),
    path("health-insurance", HealthInsuranceView.as_view(), name="health_insurance"),
]
