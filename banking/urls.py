from django.urls import path

from .views import (
    VerifYBVN,
    CreateNGNAccount,
    UpgradeAccount,
    CreateUSDAccount,
    SetWalletPin,
    ForgotWalletPin,
    PinResendOTP,
    PinVerifyOTP,
    ResetPin,
)


urlpatterns = [
    path("verify-bvn/", VerifYBVN.as_view(), name="verify_bvn"),
    path("create-ngn-account", CreateNGNAccount.as_view(), name="ngn_create_account"),
    path("upgrade-account", UpgradeAccount.as_view(), name="upgrade_account"),
    path("create-USD-account", CreateUSDAccount.as_view(), name="create-_USD_account"),
    path("set-wallet-pin", SetWalletPin.as_view(), name="set_wallet_pin"),
    path("forgot-wallet-pin", ForgotWalletPin.as_view(), name="forgot_wallet_pin"),
    path("resend-otp", PinResendOTP.as_view(), name="resend-otp"),
    path("verify-otp", PinVerifyOTP.as_view(), name="verofy_otp"),
    path("reset-wallet-pin", ResetPin.as_view(), name="reset_wallet_pin"),
]
