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


app_name = "accounts"

# ============ Token Management Endpoints ============
token_urlpatterns = [
    path("token-refresh", TokenRefreshView.as_view(), name="token_refresh"),
    path("verify-token", TokenVerifyView.as_view(), name="verify_token"),
]

# ============ Registration Endpoints ============
registration_urlpatterns = [
    path("register", Register.as_view(), name="register"),
    path("verify-otp", PhoneVerifyOTP.as_view(), name="verify_otp"),
    path("resend-otp", ResendOTP.as_view(), name="resend_otp"),
]

# ============ Authentication Endpoints ============
authentication_urlpatterns = [
    path("login", Login.as_view(), name="login"),
    path("logout", Logout.as_view(), name="logout"),
]

# ============ Password Management Endpoints ============
password_urlpatterns = [
    path("forgot-password", ForgotPassword.as_view(), name="forgot_password"),
    path(
        "password-verify-otp",
        PasswordPhoneVerifyOTP.as_view(),
        name="password_verify_otp",
    ),
    path(
        "password-resend-otp",
        PasswordResendOTP.as_view(),
        name="password_resend_otp",
    ),
    path("password-reset", ResetPassword.as_view(), name="password_reset"),
]

# ============ Combine All URL Patterns ============
urlpatterns = (
    token_urlpatterns
    + registration_urlpatterns
    + authentication_urlpatterns
    + password_urlpatterns
)
