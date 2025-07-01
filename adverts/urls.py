from django.urls import path
from .views import (
    OnboardBrandAdvertsAccount,
    ListAllBrandAds,
    SingleAdDetailView,
    GetBrandAdDetails,
    UpdateBrandAdProfile,
    CreateAdView,
    PromoteBrand,
)

app_name = "adverts"


urlpatterns = [
    path("onboard", OnboardBrandAdvertsAccount.as_view(), name="onboard"),
    path(
        "list-all-ads",
        ListAllBrandAds.as_view(),
        name="list_all_ads",
    ),
    path("get/<int:id>/", SingleAdDetailView.as_view(), name="get_ad"),
    path("profile", GetBrandAdDetails.as_view(), name="profile"),
    path("update-profile", UpdateBrandAdProfile.as_view(), name="update_profile"),
    path("create", CreateAdView.as_view(), name="create"),
    path("promote", PromoteBrand.as_view(), name="promote"),
]
