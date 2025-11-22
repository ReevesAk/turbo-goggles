from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView, TokenVerifyView

from .views import (
    Register,
    Login,
    PhoneVerifyOTP,
    PasswordPhoneVerifyOTP,
    ForgotPassword,
    ResendOTP,
    PasswordResendOTP,
    ResetPassword,
    Logout,
)

app_name = "accounts"

urlpatterns = [
    # ===== Token Management =====
    path("token-refresh", TokenRefreshView.as_view(), name="token_refresh"),
    path("verify-token", TokenVerifyView.as_view(), name="verify_token"),

    # ===== Registration =====
    path("register", Register.as_view(), name="register"),
    path("verify-otp", PhoneVerifyOTP.as_view(), name="verify_otp"),
    path("resend-otp", ResendOTP.as_view(), name="resend_otp"),

    # ===== Authentication =====
    path("login", Login.as_view(), name="login"),
    path("logout", Logout.as_view(), name="logout"),

    # ===== Password Management =====
    path("forgot-password", ForgotPassword.as_view(), name="forgot_password"),
    path("password-verify-otp", PasswordPhoneVerifyOTP.as_view(), name="password_verify_otp"),
    path("password-resend-otp", PasswordResendOTP.as_view(), name="password_resend_otp"),
    path("password-reset", ResetPassword.as_view(), name="password_reset"),
]
