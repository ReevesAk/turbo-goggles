from django.urls import path
from .views import *

urlpatterns = [
    path('register/', Register.as_view(), name='register'),
    path('verify_email/', EmailVerifyOTP.as_view(), name="verify_email"),
    path('login/', Login.as_view(), name='login'),
    path('forgot_password/', ForgotPassword.as_view(), name='forgot_password'),
    path('password_reset/', ResetPassword.as_view(), name='password_reset')
]
