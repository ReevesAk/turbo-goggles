from django.urls import path
from .views import (
    ProductStatus,
    AirTimeTopUp,
    GetNetworkProvidersVariationCodes,
    DataSubscriptionView,
    VerifyMeterNumber,
    ElectrcityBillPayment,
    ElectricityServiceIDListView,
    CableServiceIDListView,
    GetTvVariationCodes,
    VerifySmartCardNumber,
    NewTvSubscription,
    RenewTvSubscription,
    GetWaecVaritaionCodes,
    WaecRegistration,
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
        GetNetworkProvidersVariationCodes.as_view(),
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
        GetTvVariationCodes.as_view(),
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
]
