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

# ============ KYC Endpoints ============
kyc_urlpatterns = [
    path("verify-bvn", VerifYBVN.as_view(), name="verify_bvn"),
    path("verify-nin", VerifYNIN.as_view(), name="verify_nin"),
]

# ============ Wallet Endpoints ============
wallet_urlpatterns = [
    path("create-wallet", CreateUserWallet.as_view(), name="create_wallet"),
    path("upgrade-to-tier2", UpgradeToTier2Wallet.as_view(), name="upgrade_to_tier2"),
    path(
        "upgrade-from-tier2-to-tier3",
        UpgradeToTier3Wallet.as_view(),
        name="upgrade_from_tier2_to_tier3",
    ),
    path("set-wallet-pin", SetWalletPin.as_view(), name="set_wallet_pin"),
    path("forgot-wallet-pin", ForgotWalletPin.as_view(), name="forgot_wallet_pin"),
    path("resend-otp", PinResendOTP.as_view(), name="resend_otp"),
    path("verify-otp", PinVerifyOTP.as_view(), name="verify_otp"),
    path("reset-wallet-pin", ResetPin.as_view(), name="reset_wallet_pin"),
]

# ============ Transfer Endpoints ============
transfer_urlpatterns = [
    path("transfers/get-all-banks", GetAllBanks.as_view(), name="get_all_banks"),
    path("transfers/intra-bank", IntraBankTransfer.as_view(), name="intra_bank"),
    path(
        "transfers/<int:tx_reference>/status",
        TransactionStatus.as_view(),
        name="intra_bank_status",
    ),
    path("transfers/inter-bank", InterBankTransfer.as_view(), name="inter_bank"),
]

# ============ Card Payment Endpoints ============
card_urlpatterns = [
    path("pay-with-card", PayWithCard.as_view(), name="fund_with_card"),
    path(
        "fund-picadailys-wallet-with-other-cards-yesandyes",
        FundWallet.as_view(),
        name="fund",
    ),
    path("create-refund", RefundFailedCardTransaction.as_view(), name="create_refund"),
]

# ============ Transaction Endpoints ============
transaction_urlpatterns = [
    path(
        "transactions/get-all", AllTransactions.as_view(), name="get_all_transactions"
    ),
    path(
        "transactions/get-single/<uuid:tx_reference>/",
        RetrieveTransaction.as_view(),
        name="retrieve_transaction",
    ),
]

# ============ FX Endpoints ============
fx_urlpatterns = [
    path("fx/get-quotation", GetQuotation.as_view(), name="get_quotation"),
]

# ============ Webhook Endpoints ============
webhook_urlpatterns = [
    path(
        "webhook/",
        CardDepositPaystackWebhook.as_view(),
        name="paystack_webhook",
    ),
    path(
        "webhook/transfer",
        InflowsWebhookNotificationView.as_view(),
        name="webhook_transfer",
    ),
    path(
        "verify-card-deposit",
        VerifyCardPaymentTransaction.as_view(),
        name="verify_card_deposit",
    ),
    path("redirecting/", RedirectingPageView.as_view(), name="redirecting"),
]

# ============ Account & Notification Endpoints ============
account_urlpatterns = [
    path("account-details", GetAccountDetails.as_view(), name="account_details"),
    path("notification", NotificationView.as_view(), name="notification"),
]

# ============ Combine All URL Patterns ============
urlpatterns = (
    kyc_urlpatterns
    + wallet_urlpatterns
    + transfer_urlpatterns
    + card_urlpatterns
    + transaction_urlpatterns
    + fx_urlpatterns
    + webhook_urlpatterns
    + account_urlpatterns
)
