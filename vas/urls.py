from django.urls import path
from .views import AirTimeTopUp

urlpatterns = [
    path(
        "airtime-topup/",
        AirTimeTopUp.as_view(),
        name="airtime_topup",
    ),
]
