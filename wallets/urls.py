from django.urls import path
from .views import (
    VitualAccountRequest,
    SetWalletPin,
    ForgotWalletPin,
    PinResendOTP,
    ResetPin,
    PinVerifyOTP,
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
    path("set-wallet-pin/", SetWalletPin.as_view(), name="set_wallet_pin"),
    path("forgot-wallet-pin/", ForgotWalletPin.as_view(), name="forgot_wallet_pin"),
    path("resend-wallet-otp/", PinResendOTP.as_view(), name="resend_wallet_otp"),
    path("verify-wallet-otp/", PinVerifyOTP.as_view(), name="verify_wallet_otp"),
    path("reset-wallet-pin/", ResetPin.as_view(), name="reset_wallet_pin"),
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
