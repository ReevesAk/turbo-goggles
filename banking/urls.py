from django.urls import path

from .views import (
    VerifYBVN,
    VerifYNIN,
    CreateUserWallet,
    UpgradeToTier2Wallet,
    RequestToUpgradeToTier3Wallet,
    SetWalletPin,
    ForgotWalletPin,
    PinResendOTP,
    PinVerifyOTP,
    ResetPin,
    ChangePin,
    NotificationView,
    GetAccountDetails,
    RefundFailedCardTransaction,
    GetCashbackBalance,
    GenerateAccountStatement,
    CreateCorporateWallet,
    UpdateCorporateWallet,
    GetCorporateWalletStatus,
)

from .transfers import (
    GetAllBanks,
    Get9PSBWallet,
    ValidateAccountOfOtherBank,
    IntraBankTransfer,
    IntraBankFreeTransferCount,
    SuggestedBeneficiaries,
    InterBankTransfer,
    TransactionStatus,
    PayWithCard,
    FundWallet,
)

# from .fx import GetQuotation
from .tx import AllTransactions, RetrieveTransaction

from .webhooks import (
    CardDepositPaystackWebhook,
    VerifyCardPaymentTransaction,
    RedirectingPageView,
    DojahRedirectingPageView,
    WebhookDispatcherView,
    InflowsWebhookNotificationView,
    AccountUpgradeWebhookNotificationView,
    AddressVerificationWebhookView,
)

app_name = "banking"

urlpatterns = [
    # KYC
    path("verify-bvn", VerifYBVN.as_view(), name="verify_bvn"),
    path("verify-nin", VerifYNIN.as_view(), name="verify_nin"),
    path(
        "get-cashback-balance",
        GetCashbackBalance.as_view(),
        name="get_cashback_balance",
    ),
    # Wallet
    path("create-wallet", CreateUserWallet.as_view(), name="create_wallet"),
    path("upgrade-to-tier2", UpgradeToTier2Wallet.as_view(), name="upgrade_to_tier2"),
    path(
        "request-upgrade-to-tier3",
        RequestToUpgradeToTier3Wallet.as_view(),
        name="request_upgrade_to_tier3",
    ),
    path("set-wallet-pin", SetWalletPin.as_view(), name="set_wallet_pin"),
    path("forgot-wallet-pin", ForgotWalletPin.as_view(), name="forgot_wallet_pin"),
    path("resend-otp", PinResendOTP.as_view(), name="resend_otp"),
    path("verify-otp", PinVerifyOTP.as_view(), name="verify_otp"),
    path("reset-wallet-pin", ResetPin.as_view(), name="reset_wallet_pin"),
    path("change-wallet-pin", ChangePin.as_view(), name="change_wallet_pin"),
    # Transfers
    path("transfers/get-all-banks", GetAllBanks.as_view(), name="get_all_banks"),
    path("transfers/get-9psb-wallet", Get9PSBWallet.as_view(), name="get_9psb_wallet"),
    path(
        "transfers/validate-account",
        ValidateAccountOfOtherBank.as_view(),
        name="validate_account",
    ),
    path("transfers/intra-bank", IntraBankTransfer.as_view(), name="intra_bank"),
    path(
        "transfers/intra-bank/free-count",
        IntraBankFreeTransferCount.as_view(),
        name="intra_bank_free_count",
    ),
    path(
        "transfers/beneficiaries/suggested",
        SuggestedBeneficiaries.as_view(),
        name="suggested_beneficiaries",
    ),
    path("transfers/inter-bank", InterBankTransfer.as_view(), name="inter_bank"),
    path(
        "transfers/<int:tx_reference>/status",
        TransactionStatus.as_view(),
        name="transaction_status",
    ),
    # Card Payments
    path("pay-with-card", PayWithCard.as_view(), name="fund_with_card"),
    path(
        "fund-picadailys-wallet-with-other-cards-yesandyes",
        FundWallet.as_view(),
        name="fund_wallet",
    ),
    path("create-refund", RefundFailedCardTransaction.as_view(), name="create_refund"),
    # Transactions
    path(
        "transactions/get-all", AllTransactions.as_view(), name="get_all_transactions"
    ),
    path(
        "transactions/get-single/<uuid:tx_reference>/",
        RetrieveTransaction.as_view(),
        name="retrieve_transaction",
    ),
    # FX
    # path("fx/get-quotation", GetQuotation.as_view(), name="get_quotation"),
    # Webhooks
    path(
        "paystack/webhook/",
        CardDepositPaystackWebhook.as_view(),
        name="paystack_webhook",
    ),
    path("webhook", WebhookDispatcherView.as_view(), name="webhook_dispatcher"),
    path(
        "webhook/transfer",
        InflowsWebhookNotificationView.as_view(),
        name="webhook_transfer",
    ),
    path(
        "webhook/account-upgrade",
        AccountUpgradeWebhookNotificationView.as_view(),
        name="webhook_account_upgrade",
    ),
    path(
        "webhook/address-verification",
        AddressVerificationWebhookView.as_view(),
        name="webhook_address_verification",
    ),
    path(
        "verify-card-deposit/<str:txn_reference>/",
        VerifyCardPaymentTransaction.as_view(),
        name="verify_card_deposit",
    ),
    path("redirecting/", RedirectingPageView.as_view(), name="redirecting"),
    path("dojah/redirect", DojahRedirectingPageView.as_view(), name="redirecting"),
    # Account + Notifications
    path("account-details", GetAccountDetails.as_view(), name="account_details"),
    path("notification", NotificationView.as_view(), name="notification"),
    path(
        "generate-statement",
        GenerateAccountStatement.as_view(),
        name="generate_statement",
    ),
    # Corporate wallet
    path("corporate/submit", CreateCorporateWallet.as_view(), name="corporate_submit"),
    path("corporate/update", UpdateCorporateWallet.as_view(), name="corporate_update"),
    path(
        "corporate/status", GetCorporateWalletStatus.as_view(), name="corporate_status"
    ),
]
