from django.urls import path

from .views import (
    VerifYBVN,
    CreateNGNAccount,
    UpgradeAccount,
    CreateUSDAccount,
    SetWalletPin,
)


urlpatterns = [
    path('verify-bvn/', VerifYBVN.as_view(), name='verify_bvn'),
    path('create-ngn-account', CreateNGNAccount.as_view(), name='ngn_create_account'),
    path('upgrade-account', UpgradeAccount.as_view(), name='upgrade_account'),
    path('create-USD-account', CreateUSDAccount.as_view(), name='create-_USD_account'),
    path('set-wallet-pin', SetWalletPin.as_view(), name='set_wallet_pin')
]
