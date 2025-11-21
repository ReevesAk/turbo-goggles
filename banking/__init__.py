# banking/views/__init__.py OR banking/views.py

from .schema_tags import apply_tag

# === KYC ===
from .views import VerifYBVN, VerifYNIN
apply_tag("KYC", [VerifYBVN, VerifYNIN])


# === Wallet ===
from .views import (
    CreateUserWallet, UpgradeToTier2Wallet, UpgradeToTier3Wallet,
    SetWalletPin, ForgotWalletPin, PinResendOTP, PinVerifyOTP, ResetPin
)

apply_tag("Wallet", [
    CreateUserWallet,
    UpgradeToTier2Wallet,
    UpgradeToTier3Wallet,
    SetWalletPin,
    ForgotWalletPin,
    PinResendOTP,
    PinVerifyOTP,
    ResetPin
])


# === Transfers ===
from .transfers import (
    GetAllBanks, IntraBankTransfer, InterBankTransfer, TransactionStatus
)

apply_tag("Transfers", [
    GetAllBanks,
    IntraBankTransfer,
    InterBankTransfer,
    TransactionStatus
])


# === Cards ===
from .transfers import PayWithCard, FundWallet
from .views import RefundFailedCardTransaction

apply_tag("Cards", [
    PayWithCard,
    FundWallet,
    RefundFailedCardTransaction,
])


# === Transactions ===
from .tx import AllTransactions, RetrieveTransaction
apply_tag("Transactions", [AllTransactions, RetrieveTransaction])


# === FX ===
from .fx import GetQuotation
apply_tag("FX", [GetQuotation])


# === Webhooks ===
from .webhooks import (
    CardDepositPaystackWebhook,
    VerifyCardPaymentTransaction,
    RedirectingPageView,
    InflowsWebhookNotificationView
)

apply_tag("Webhooks", [
    CardDepositPaystackWebhook,
    VerifyCardPaymentTransaction,
    RedirectingPageView,
    InflowsWebhookNotificationView,
])


# === Account ===
from .views import GetAccountDetails, NotificationView

apply_tag("Account", [GetAccountDetails])
apply_tag("Notifications", [NotificationView])
