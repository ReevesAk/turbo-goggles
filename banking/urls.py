from django.urls import path
from django.urls import path, include

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
    path("kyc/", include("banking.urls_kyc")),
    path("wallet/", include("banking.urls_wallet")),
    path("transfers/", include("banking.urls_transfers")),
    path("card/", include("banking.urls_card")),
    path("transactions/", include("banking.urls_transactions")),
    path("fx/", include("banking.urls_fx")),
    path("webhook/", include("banking.urls_webhook")),
    path("account/", include("banking.urls_account")),
]

urlpatterns = [
    path("verify-bvn", VerifYBVN.as_view(), name="verify_bvn"),
    path("verify-nin", VerifYNIN.as_view(), name="verify_nin"),
]

urlpatterns = [
    path("create-wallet", CreateUserWallet.as_view(), name="create_wallet"),
    path("upgrade-to-tier2", UpgradeToTier2Wallet.as_view(), name="upgrade_to_tier2"),
    path("upgrade-from-tier2-to-tier3", UpgradeToTier3Wallet.as_view(), name="upgrade_from_tier2_to_tier3"),
    path("set-wallet-pin", SetWalletPin.as_view(), name="set_wallet_pin"),
    path("forgot-wallet-pin", ForgotWalletPin.as_view(), name="forgot_wallet_pin"),
    path("resend-otp", PinResendOTP.as_view(), name="resend_otp"),
    path("verify-otp", PinVerifyOTP.as_view(), name="verify_otp"),
    path("reset-wallet-pin", ResetPin.as_view(), name="reset_wallet_pin"),
]

urlpatterns = [
    path("get-all-banks", GetAllBanks.as_view(), name="get_all_banks"),
    path("intra-bank", IntraBankTransfer.as_view(), name="intra_bank"),
    path("inter-bank", InterBankTransfer.as_view(), name="inter_bank"),
    path("<int:tx_reference>/status", TransactionStatus.as_view(), name="intra_bank_status"),
]

urlpatterns = [
    path("pay-with-card", PayWithCard.as_view(), name="fund_with_card"),
    path("fund-picadailys-wallet-with-other-cards-yesandyes", FundWallet.as_view(), name="fund"),
    path("create-refund", RefundFailedCardTransaction.as_view(), name="create_refund"),
]

urlpatterns = [
    path("get-all", AllTransactions.as_view(), name="get_all_transactions"),
    path("get-single/<uuid:tx_reference>/", RetrieveTransaction.as_view(), name="retrieve_transaction"),
]

urlpatterns = [
    path("get-quotation", GetQuotation.as_view(), name="get_quotation"),
]

urlpatterns = [
    path("", CardDepositPaystackWebhook.as_view(), name="paystack_webhook"),
    path("transfer", InflowsWebhookNotificationView.as_view(), name="webhook_transfer"),
    path("verify-card-deposit", VerifyCardPaymentTransaction.as_view(), name="verify_card_deposit"),
    path("redirecting/", RedirectingPageView.as_view(), name="redirecting"),
]

urlpatterns = [
    path("account-details", GetAccountDetails.as_view(), name="account_details"),
    path("notification", NotificationView.as_view(), name="notification"),
]
