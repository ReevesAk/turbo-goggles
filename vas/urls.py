from django.urls import path
from .views import (
    AirTimeTopUp, GetVaritaionCodes, DataSubscription
)


urlpatterns = [
    path(
        "airtime-topup/",
        AirTimeTopUp.as_view(),
        name="airtime_topup",
    ),
    path(
        "get-variation-codes/<str:service_ID>/",
        GetVaritaionCodes.as_view(),
        name="variation_codes",
    ),
    path("subscribe-data/", DataSubscription.as_view(), name="data_subscription"),
]
