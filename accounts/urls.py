from django.urls import path
from .views import *

from rest_framework_simplejwt.views import TokenRefreshView, TokenVerifyView

urlpatterns = [
    # Token endpoints.
    path("token_refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("verify_token/", TokenVerifyView.as_view(), name="verify_token"),
    # authentication endpoints.
    path("register/", Register.as_view(), name="register"),
    path("verify_email/", EmailVerifyOTP.as_view(), name="verify_email"),
    path("login/", Login.as_view(), name="login"),
    path("forgot_password/", ForgotPassword.as_view(), name="forgot_password"),
    path("password_reset/", ResetPassword.as_view(), name="password_reset"),
]
