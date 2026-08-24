from banking.models import WalletModel
from django.contrib.auth.hashers import make_password


def ensure_wallet_for_user(user, account_number="1234567890", balance=10000):
    """
    Ensure the test user has a WalletModel with a valid PIN and sufficient
    balance. walletType="INDIVIDUAL" is required - VAS views look wallets up
    with WalletModel.objects.get(user=user, walletType="INDIVIDUAL"), so a
    wallet without it is invisible to them (WalletModel.DoesNotExist).
    """
    wallet, created = WalletModel.objects.get_or_create(user=user)
    wallet.walletType = "INDIVIDUAL"
    wallet.account_number = account_number
    wallet.balance = balance
    wallet.pin = make_password("1234")
    wallet.save()
    return wallet
