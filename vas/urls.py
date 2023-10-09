from django.urls import path
from .views import (
    AirTimeTopUp,
    GetNetworkProvidersVaritaionCodes,
    DataSubscription,
    VerifyMeterNumber,
    ElectrcityBillPayment,
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
]
