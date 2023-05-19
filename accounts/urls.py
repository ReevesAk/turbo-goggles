from django.urls import path
from .views import *

urlpatterns = [
    path('register/', Register.as_view(), name='register'),
    path('verify_email/', EmailVerifyOTP.as_view(), name="verify_email"),
    path('login/', Login.as_view(), name='login'),
]
