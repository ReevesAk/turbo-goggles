from django.urls import path
from .views import (
   RegisterPartner, PartnerServiceView, GetPartnerDetails, 
   PartnerServiceListView, ServiceAndChargeView, 
   UploadImage,
)

urlpatterns = [
    path('register_partners/', RegisterPartner.as_view(), name='register-partners'),
    path('partner_service/', PartnerServiceView.as_view(), name='create_partner_service'),
    path('partner-profile/', GetPartnerDetails.as_view(), name='get_partner_profile'),
    path('list-partner-service/<int:id>/', PartnerServiceListView.as_view(), name='partner-service'),
    path('add-service-charge/<int:id>/', ServiceAndChargeView.as_view(), name='create_service_charge'),
    path('service-uploads/<int:id>/', UploadImage.as_view(), name='service-uploads'),
]
