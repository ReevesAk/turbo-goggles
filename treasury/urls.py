from django.urls import path

from .views import (
    CreateTreasuryAccount,
    GetTreasuryAccountDetails,
    SetAccountPin,
    ForgotAccountPin,
    PinResendOTP,
    PinVerifyOTP,
    ResetAccountPin,
    GetTreasuryCashbackBalance,
    UpgradeTierTwoView,
    UpgradeTierThreeView,
    ListBeneficiariesView,
    DeleteBeneficiaryView,
)
from .transfers import (
    ValidateTreasuryAccount,
    ValidateExternalAccount,
    InternalTransfer,
    InternalTransferFreeCount,
    ExternalTransfer,
    PayWithCard,
    FundTreasuryAccount,
)
from .webhooks import (
    AnchorWebhookView,
    CardDepositPaystackWebhook,
    VerifyCardPaymentTransaction,
)

app_name = "treasury"

urlpatterns = [
    # Account management
    path("create-account", CreateTreasuryAccount.as_view(), name="create_account"),
    path(
        "account-details", GetTreasuryAccountDetails.as_view(), name="account_details"
    ),
    path(
        "get-cashback-balance",
        GetTreasuryCashbackBalance.as_view(),
        name="cashback_balance",
    ),
    # KYC tier upgrades
    path("upgrade-tier2", UpgradeTierTwoView.as_view(), name="upgrade_tier2"),
    path("upgrade-tier3", UpgradeTierThreeView.as_view(), name="upgrade_tier3"),
    # Beneficiaries
    path("beneficiaries", ListBeneficiariesView.as_view(), name="list_beneficiaries"),
    path(
        "beneficiaries/<int:pk>",
        DeleteBeneficiaryView.as_view(),
        name="delete_beneficiary",
    ),
    # PIN management
    path("set-pin", SetAccountPin.as_view(), name="set_pin"),
    path("forgot-pin", ForgotAccountPin.as_view(), name="forgot_pin"),
    path("resend-otp", PinResendOTP.as_view(), name="resend_otp"),
    path("verify-otp", PinVerifyOTP.as_view(), name="verify_otp"),
    path("reset-pin", ResetAccountPin.as_view(), name="reset_pin"),
    # Transfers
    path(
        "transfers/validate-account",
        ValidateTreasuryAccount.as_view(),
        name="validate_treasury_account",
    ),
    path(
        "transfers/validate-external-account",
        ValidateExternalAccount.as_view(),
        name="validate_external_account",
    ),
    path("transfers/internal", InternalTransfer.as_view(), name="internal_transfer"),
    path(
        "transfers/internal/free-count",
        InternalTransferFreeCount.as_view(),
        name="internal_transfer_free_count",
    ),
    path("transfers/external", ExternalTransfer.as_view(), name="external_transfer"),
    # Card funding
    path("pay-with-card", PayWithCard.as_view(), name="pay_with_card"),
    path("fund-account", FundTreasuryAccount.as_view(), name="fund_account"),
    path(
        "verify-card-deposit/<str:txn_reference>/",
        VerifyCardPaymentTransaction.as_view(),
        name="verify_card_deposit",
    ),
    # Webhooks
    path("webhook/anchor/", AnchorWebhookView.as_view(), name="anchor_webhook"),
    path(
        "paystack/webhook/",
        CardDepositPaystackWebhook.as_view(),
        name="paystack_webhook",
    ),
]
