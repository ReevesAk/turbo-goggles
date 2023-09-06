from django.urls import path
from .views import (
   RegisterPartner, PartnerServiceView, PartnerServiceListView, 
   WalletInfo, ServiceAndChargeView, UploadImage, ServiceAndChargeListView,
   DepositFunds, TransferFunds, VerifyDeposit
)

urlpatterns = [
    path('register_partners/', RegisterPartner.as_view(), name='register-partners'),
    path('partner_service/', PartnerServiceView.as_view(), name='create_partner_service'),
    path('list-partner-service/<int:id>/', PartnerServiceListView.as_view(), name='partner-service'),
    path('add-service-charge/<int:id>/', ServiceAndChargeView.as_view(), name='create_service_charge'),
    path('list-service-charge/<int:id>/', ServiceAndChargeListView.as_view(), name='service-charge'),
    path('service-uploads/<int:id>/', UploadImage.as_view(), name='service-uploads'),
    path('wallet-info/<int:id>/', WalletInfo.as_view(), name='wallet_info'),
    path('deposit/<int:id>/', DepositFunds.as_view(), name='deposit'),
    path('deposit/verify/<str:reference>/', VerifyDeposit.as_view(), name='verify_deposit'),
    path('transfer/<int:id>/', TransferFunds.as_view(), name='transfer'),
]
