from django.urls import path
from .views import (
    RegisterBrandAdverts,
    ListAllBrandAds,
    GetBrandAdDetails,
    UpdateBrandAdProfile,
    BrandSurveyView,
    BrandPromote,
)

urlpatterns = [
    path("register/", RegisterBrandAdverts.as_view(), name="register_ads"),
    path(
        "list-all-ads/",
        ListAllBrandAds.as_view(),
        name="list_all_ads",
    ),
    path("profile/", GetBrandAdDetails.as_view(), name="profile"),
    path("update-profile/", UpdateBrandAdProfile.as_view(), name="update_profile"),
    path("survey/", BrandSurveyView.as_view(), name="survey"),
    path("promote/", BrandPromote.as_view(), name="promote"),
]
