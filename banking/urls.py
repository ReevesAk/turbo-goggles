from django.urls import path

from .views import (
    VerifYBVN,
    SetWalletPin,
    ForgotWalletPin,
    PinResendOTP,
    PinVerifyOTP,
    ResetPin,
    NotificationView,
)
from .fx import GetQuotation
from .tx import AllTransactions, RetrieveTransaction

urlpatterns = [
    path("notification", NotificationView.as_view(), name="notification"),
    path("verify-bvn/", VerifYBVN.as_view(), name="verify_bvn"),
    path("set-wallet-pin", SetWalletPin.as_view(), name="set_wallet_pin"),
    path("forgot-wallet-pin", ForgotWalletPin.as_view(), name="forgot_wallet_pin"),
    path("resend-otp", PinResendOTP.as_view(), name="resend-otp"),
    path("verify-otp", PinVerifyOTP.as_view(), name="verofy_otp"),
    path("reset-wallet-pin", ResetPin.as_view(), name="reset_wallet_pin"),
    # Fx Endpoints.
    path("fx/get-quotation", GetQuotation.as_view(), name="get_quotation"),
    # Transactions Endpoints.
    path(
        "transactions/get-all", AllTransactions.as_view(), name="get-all-transactions"
    ),
    path(
        "transactions/get-single/<uuid:tx_reference>/",
        RetrieveTransaction.as_view(),
        name="retrieve-transaction",
    ),
]
