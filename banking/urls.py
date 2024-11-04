from django.urls import path

from .views import (
    VerifYBVN,
    CreateBankAccount,
    SetWalletPin,
    ForgotWalletPin,
    PinResendOTP,
    PinVerifyOTP,
    ResetPin,
    NotificationView,
    GetAccountDetails,
)
from .transfers import (
    GetAllBanks,
    GetProvidusAccount,
    GetAccount,
    IntraBankTransfer,
    InterBankTransfer,
    InterBankTransactionStatus,
    IntraBankTransactionStatus,
)
from .fx import GetQuotation
from .tx import AllTransactions, RetrieveTransaction
from .webhooks import CardDepositPaystackWebhook, VerifyCardPaymentTransaction

urlpatterns = [
    path("notification", NotificationView.as_view(), name="notification"),
    path("account-details", GetAccountDetails.as_view(), name="account_details"),
    path("verify-bvn", VerifYBVN.as_view(), name="verify_bvn"),
    path("open-account", CreateBankAccount.as_view(), name="open_account"),
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
    # Transfer Endpoints.
    path("transfers/get-all-banks", GetAllBanks.as_view(), name="get_all_banks"),
    path(
        "transfers/get-providus-account",
        GetProvidusAccount.as_view(),
        name="get_providus_account",
    ),
    path("transfers/get-account", GetAccount.as_view(), name="get_account"),
    path("transfers/intra-bank", IntraBankTransfer.as_view(), name="intra_bank"),
    path(
        "transfers/intra-bank/<int:tx_reference>/status",
        IntraBankTransactionStatus.as_view(),
        name="intra_bank_status",
    ),
    path("transfers/inter-bank", InterBankTransfer.as_view(), name="inter_bank"),
    path(
        "transfers/inter-bank/<int:tx_reference>/status",
        InterBankTransactionStatus.as_view(),
        name="inter_bank_status",
    ),
    path(
        "webhook/",
        CardDepositPaystackWebhook.as_view(),
        name="paystack-webhook",
    ),
    path(
        "verify-card-deposit",
        VerifyCardPaymentTransaction.as_view(),
        name="verify_card_deposit",
    ),
]
