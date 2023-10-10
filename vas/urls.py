from django.urls import path
from .views import (
    AirTimeTopUp,
    GetNetworkProvidersVaritaionCodes,
    DataSubscription,
    VerifyMeterNumber,
    ElectrcityBillPayment,
    GetTvVaritaionCodes,
    VerifySmartCardNumber,
    ProductStatus,
    NewTvSubscription,
    RenewTvSubscription,
    GetIntlAirtimeCountryCodes,
    GetIntlAirtimeProducts,
    GetIntlAirtimeOperators,
    GetIntlAirtimeVaraitionCodes,
    InternationalAirTimeTopUp,
    GetWaecVaritaionCodes,
    WaecRegistration,
)

urlpatterns = [
    path(
        "airtime-topup/",
        AirTimeTopUp.as_view(),
        name="airtime_topup",
    ),
    path(
        "get-variation-codes/<str:service_ID>/",
        GetNetworkProvidersVaritaionCodes.as_view(),
        name="variation_codes",
    ),
    path("subscribe-data/", DataSubscription.as_view(), name="data_subscription"),
    path("verify-meter-no/", VerifyMeterNumber.as_view(), name="verify-meter"),
    path(
        "pay-electricity-bill/",
        ElectrcityBillPayment.as_view(),
        name="pay_electric_bill",
    ),
    path(
        "get-tv-variation-codes/<str:service_ID>/",
        GetTvVaritaionCodes.as_view(),
        name="tv_variation_codes",
    ),
    path(
        "verify-smart-card-no/",
        VerifySmartCardNumber.as_view(),
        name="verify_smart_card",
    ),
    path("product-status/", ProductStatus.as_view(), name="check_product_status"),
    path("new-subscription/", NewTvSubscription.as_view(), name="new_subscription"),
    path("renew-exisitng-tv-plan/", RenewTvSubscription.as_view(), name="renew-tv-sub"),
    path(
        "get-intl-countries/",
        GetIntlAirtimeCountryCodes.as_view(),
        name="get_intl_countries",
    ),
    path(
        "get-intl-products/<str:country_code>/",
        GetIntlAirtimeProducts.as_view(),
        name="get_intl_products",
    ),
    path(
        "get-intl-operators/<str:country_code>/<str:product_type_id>/",
        GetIntlAirtimeOperators.as_view(),
        name="get_intl_ops",
    ),
    path(
        "get-intl-var-codes/<str:operator_id>/<str:product_type_id>/",
        GetIntlAirtimeVaraitionCodes.as_view(),
        name="get_intl_ops",
    ),
    path("intl-topup/", InternationalAirTimeTopUp.as_view(), name="intl_topup"),
    path("waec-variation-codes/<str:service_ID>/", GetWaecVaritaionCodes.as_view(), name="waec_codes"),
    path("waec-registration/", WaecRegistration.as_view(), name="waec_registration"),
]
