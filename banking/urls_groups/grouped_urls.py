from django.urls import path
from banking.views import (
    BankTransferView,
    BankListView,
    VerifyBankAccountView,
    AccountBalanceView,
    WalletToWalletTransferView,
    InitiateCardPaymentView,
    VerifyCardPaymentView,
    TransactionHistoryView,
    TransactionDetailView,
)

urlpatterns = [
    # =============================
    # BANK TRANSFERS
    # =============================
    path("transfer/bank/", BankTransferView.as_view(), name="bank_transfer"),
    path("banks/", BankListView.as_view(), name="bank_list"),
    path("account/verify/", VerifyBankAccountView.as_view(), name="verify_bank_account"),

    # =============================
    # WALLET
    # =============================
    path("wallet/balance/", AccountBalanceView.as_view(), name="account_balance"),
    path("wallet/transfer/", WalletToWalletTransferView.as_view(), name="wallet_to_wallet_transfer"),

    # =============================
    # CARD PAYMENTS
    # =============================
    path("card/initiate/", InitiateCardPaymentView.as_view(), name="initiate_card_payment"),
    path("card/verify/", VerifyCardPaymentView.as_view(), name="verify_card_payment"),

    # =============================
    # TRANSACTIONS
    # =============================
    path("transactions/", TransactionHistoryView.as_view(), name="transaction_history"),
    path("transactions/<uuid:tx_reference>/", TransactionDetailView.as_view(), name="transaction_detail"),
]
