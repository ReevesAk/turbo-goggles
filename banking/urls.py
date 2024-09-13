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
    UpdateCustomer,
    GetAllBanks,
    NotificationView,
)

from .virtual_cards import CreateCard, PayWithCard, FreezeCard, UnfreezeCard
from .transfers import (
    TransferWithinNG,
    TransferWithinPicadailys,
    InternationalTransfer,
    VerifyTransfer,
    FundWalletWithCard,
)
from .fx import GetQuotation, ConvertToDollar
from .tx import AllTransactions, RetrieveTransaction

urlpatterns = [
    path("notification", NotificationView.as_view(), name="notification"),
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
    path(
        "get-customers-wallets",
        GetCustomersWallets.as_view(),
        name="get_customers_wallets",
    ),
    path(
        "customers-history",
        CustomerTransctionHistory.as_view(),
        name="customers_history",
    ),
    path("update-customer", UpdateCustomer.as_view(), name="update_customer"),
    path("all-banks", GetAllBanks.as_view(), name="all_banks"),
    # Card Endpoints.
    path("card/create", CreateCard.as_view(), name="create_card"),
    path("card/pay", PayWithCard.as_view(), name="card_pay"),
    path("card/freeze", FreezeCard.as_view(), name="freeze_card"),
    path("card/unfreeze", UnfreezeCard.as_view(), name="unfreeze_card"),
    # Transfer Endpoints.
    path("transfer/local", TransferWithinNG.as_view(), name="transfer_local"),
    path(
        "transfer/picadailys",
        TransferWithinPicadailys.as_view(),
        name="transfer_picadailys",
    ),
    path(
        "transfer/international",
        InternationalTransfer.as_view(),
        name="transfer_international",
    ),
    path(
        "transfer/verify-tx/<int:transfer_id>/",
        VerifyTransfer.as_view(),
        name="verify_transfer",
    ),
    path(
        "transfer/fund_with_card/", FundWalletWithCard.as_view(), name="fund_with_card"
    ),
    # Fx Endpoints.
    path(
        "fx/convert-to-dollar", ConvertToDollar.as_view(), name="transfer_con_to_doll"
    ),
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
