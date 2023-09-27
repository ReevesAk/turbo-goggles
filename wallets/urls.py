from django.urls import path
from .views import VitualAccountRequest, AccountDetails

urlpatterns = [
    path(
        "create-virtual-account/",
        VitualAccountRequest.as_view(),
        name="create-virtual-account",
    ),
    path("get-account-details/", AccountDetails.as_view(), name="get-account-details"),
]
