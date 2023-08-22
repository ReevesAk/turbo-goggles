from django.urls import path
from .views import *

urlpatterns = [
    path('register-adverts/', StartRegisterAdverts.as_view(), name='register_ads-start'),
    path('register-adverts-contd/', ContdRegisterAdverts.as_view(), name='register_ads-contd'),
]