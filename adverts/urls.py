from django.urls import path
from .views import (
    CreateBrandAdvertsAccount,
    ListAllBrandAds,
    GetBrandAdDetails,
    UpdateBrandAdProfile,
    BrandSurveyView,
    BrandPromote,
)

app_name = "adverts"


urlpatterns = [
    path("create-ad", CreateBrandAdvertsAccount.as_view(), name="create_ad"),
    path(
        "list-all-ads",
        ListAllBrandAds.as_view(),
        name="list_all_ads",
    ),
    path("profile", GetBrandAdDetails.as_view(), name="profile"),
    path("update-profile", UpdateBrandAdProfile.as_view(), name="update_profile"),
    path("survey", BrandSurveyView.as_view(), name="survey"),
    path("promote", BrandPromote.as_view(), name="promote"),
]
