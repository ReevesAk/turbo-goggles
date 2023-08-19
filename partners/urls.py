from django.urls import path
from .views import *

urlpatterns = [
    path('register_partners/', RegisterPartner.as_view(), name='register-partners'),
    path('partner_service/', PartnerServiceViewsets.as_view(
        {'get': 'list', 'post': 'create'}
    ), name='partner-service'),
    path('service_charge/', ServiceAndChargeViewsets.as_view(
        {'get': 'list', 'post': 'create'}
    ), name='service-charge'),
    path('service_uploads/', UploadImage.as_view(), name='service-uploads')
]
