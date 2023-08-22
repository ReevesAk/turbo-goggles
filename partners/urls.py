from django.urls import path
from .views import *

urlpatterns = [
    path('register_partners/', RegisterPartner.as_view(), name='register-partners'),
    path('partner_service/<int:id>/', PartnerServiceViewsets.as_view(
        {'get': 'list', 'post': 'create'}
    ), name='partner-service'),
    path('service_charge/<int:id>/', ServiceAndChargeViewsets.as_view(
        {'get': 'list', 'post': 'create'}
    ), name='service-charge'),
    path('service_uploads/<int:id>/', UploadImage.as_view(), name='service-uploads'),
    path('wallet_info/', WalletInfo.as_view(), name='wallet_info'),
    path('deposit/', DepositFunds.as_view(), name='deposit'),
    path('deposit/verify/<str:reference>/', VerifyDeposit.as_view(), name='verify_deposit'),
    path('transfer/', TransferFunds.as_view(), name='transfer'),
]
