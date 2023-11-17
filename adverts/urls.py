from django.urls import path
from .views import (
    RegisterBrandAdverts,
    ListAllBrandAds,
)

urlpatterns = [
    path(
        "register-adverts/", RegisterBrandAdverts.as_view(), name="register_ads"
    ),
    path(
        "list-all-ads/",
        ListAllBrandAds.as_view(),
        name="list_all_ads",
    ),
]
