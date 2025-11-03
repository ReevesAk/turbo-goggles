from django.urls import path

from .views import (
    VerifYBVN,
    VerifYNIN,
    CreateUserWallet,
    UpgradeToTier2Wallet,
    UpgradeToTier3Wallet,
    SetWalletPin,
    ForgotWalletPin,
    PinResendOTP,
    PinVerifyOTP,
    ResetPin,
    NotificationView,
    GetAccountDetails,
    RefundFailedCardTransaction,
)
from .transfers import (
    GetAllBanks,
    IntraBankTransfer,
    InterBankTransfer,
    TransactionStatus,
    PayWithCard,
    FundWallet,
)
from .fx import GetQuotation
from .tx import AllTransactions, RetrieveTransaction
from .webhooks import (
    CardDepositPaystackWebhook,
    VerifyCardPaymentTransaction,
    RedirectingPageView,
    InflowsWebhookNotificationView,
)


app_name = "banking"


urlpatterns = [
    path("notification", NotificationView.as_view(), name="notification"),
    path(
        "webhook/transfer",
        InflowsWebhookNotificationView.as_view(),
        name="webhook_transfer",
    ),
    path("account-details", GetAccountDetails.as_view(), name="account_details"),
    path("verify-bvn", VerifYBVN.as_view(), name="verify_bvn"),
    path("verify-nin", VerifYNIN.as_view(), name="verify_nin"),
    path("upgrade-to-tier2", UpgradeToTier2Wallet.as_view(), name="upgrade_to_tier2"),
    path(
        "upgrade-from-tier2-to-tier3",
        UpgradeToTier3Wallet.as_view(),
        name="upgrade_from_tier2_to_tier3",
    ),
    path("create-wallet", CreateUserWallet.as_view(), name="create_wallet"),
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
    path("transfers/intra-bank", IntraBankTransfer.as_view(), name="intra_bank"),
    path(
        "transfers/<int:tx_reference>/status",
        TransactionStatus.as_view(),
        name="intra_bank_status",
    ),
    path("transfers/inter-bank", InterBankTransfer.as_view(), name="inter_bank"),
    path("pay-with-card", PayWithCard.as_view(), name="fund_with_card"),
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
    path("redirecting/", RedirectingPageView.as_view(), name="redirecting"),
    path(
        "fund-picadailys-wallet-with-other-cards-yesandyes",
        FundWallet.as_view(),
        name="fund",
    ),
    path("create-refund", RefundFailedCardTransaction.as_view(), name="create_refund"),
]
