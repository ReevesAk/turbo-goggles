from django.urls import path
from .views import (
    VitualAccountRequest, AccountDetails, FetchAllBanks
)

urlpatterns = [
    path(
        "create-virtual-account/",
        VitualAccountRequest.as_view(),
        name="create_virtual_account",
    ),
    path("get-account-details/<str:acc_id>/", AccountDetails.as_view(), name="get_account_details"),
    path("fetch-all-banks/", FetchAllBanks.as_view(), name="fetch_all_banks"),
]
