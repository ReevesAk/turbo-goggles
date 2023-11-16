from django.urls import path

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

from rest_framework_simplejwt.views import TokenRefreshView, TokenVerifyView

urlpatterns = [
    # Token endpoints.
    path("token-refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("verify-token/", TokenVerifyView.as_view(), name="verify_token"),
    # authentication endpoints.
    path("register/", Register.as_view(), name="register"),
    path("verify-otp/", PhoneVerifyOTP.as_view(), name="verify_otp"),
    path(
        "password-verify-otp/",
        PasswordPhoneVerifyOTP.as_view(),
        name="password_verify_otp",
    ),
    path("login/", Login.as_view(), name="login"),
    path("forgot-password/", ForgotPassword.as_view(), name="forgot_password"),
    path("password-reset/", ResetPassword.as_view(), name="password_reset"),
    path("resend-otp/", ResendOTP.as_view(), name="resend_otp"),
    path(
        "password-resend-otp/", PasswordResendOTP.as_view(), name="password-resend_otp"
    ),
    path("logout/", Logout.as_view(), name="logout"),
]
