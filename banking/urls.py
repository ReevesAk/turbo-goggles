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
    GetCustomer,
    GetCustomersWallets,
    CustomerTransctionHistory,
    UpdateCustomer
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
    path("get-customer", GetCustomer.as_view(), name="get_customer"),
    path("get-customers-wallets", GetCustomersWallets.as_view(), name="get_customers_wallets"),
    path("customers-history", CustomerTransctionHistory.as_view(), name="customers_history"),
    path("update-customer", UpdateCustomer.as_view(), name="update_customer")
    
]
