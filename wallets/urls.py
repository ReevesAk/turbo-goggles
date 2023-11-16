from django.urls import path
from .views import (
    VitualAccountRequest,
    AccountDetails,
    FetchAllBanks,
    GetParentDetails,
    BankPayouts,
    FincraPayouts,
    FetchAllBalances,
    PicadailysTransfers,
    VerifYBVN,
)

urlpatterns = [
    path("verify-bvn/", VerifYBVN.as_view(), name="verify_bvn"),
    path(
        "create-virtual-account/",
        VitualAccountRequest.as_view(),
        name="create_virtual_account",
    ),
    path(
        "get-account-details/<str:acc_id>/",
        AccountDetails.as_view(),
        name="get_account_details",
    ),
    path("fetch-all-banks/", FetchAllBanks.as_view(), name="fetch_all_banks"),
    path("get_parent_details/", GetParentDetails.as_view(), name="parent_details"),
    path(
        "fetch-all-balances/<str:bus_id>/",
        FetchAllBalances.as_view(),
        name="fetch_all_balances",
    ),
    path("bank-payouts/", BankPayouts.as_view(), name="bank_payouts"),
    path("fincra-payouts/", FincraPayouts.as_view(), name="fincra_payouts"),
    path(
        "picadailys-payouts/", PicadailysTransfers.as_view(), name="picadailys_payouts"
    ),
]
