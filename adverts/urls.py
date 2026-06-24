from django.urls import path
from .views import (
    ListAllBrandAds,
    ListAllBrandAdsUsers,
    SingleAdDetailView,
    GetBrandAdDetails,
    UpdateBrandAdProfile,
    CreateAdAndOnboardBrandView,
    AdCostPreviewView,
    BrandAdAnalyticsView,
)

app_name = "adverts"


urlpatterns = [
    path(
        "onboard-and-create",
        CreateAdAndOnboardBrandView.as_view(),
        name="onboard_and_create",
    ),
    path(
        "list-all-ads",
        ListAllBrandAds.as_view(),
        name="list_all_ads",
    ),
    path(
        "list-all-ads-users",
        ListAllBrandAdsUsers.as_view(),
        name="list_all_ads_users",
    ),
    path("get/<int:ad_id>/", SingleAdDetailView.as_view(), name="get_ad"),
    path("profile", GetBrandAdDetails.as_view(), name="profile"),
    path("update-profile", UpdateBrandAdProfile.as_view(), name="update_profile"),
    path("cost-preview/", AdCostPreviewView.as_view(), name="ad_cost_preview"),
    path("analytics/<int:ad_id>/", BrandAdAnalyticsView.as_view(), name="ad_analytics"),
]
