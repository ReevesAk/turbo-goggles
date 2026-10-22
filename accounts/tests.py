import json as _json
from datetime import timedelta
from unittest.mock import patch

from django.utils import timezone

from rest_framework import status
from rest_framework.test import APITestCase

from security import encrypt, decrypt
from .models import AccountType, DeviceId, OTP, User, UserNotification
from .otp import OTPManager
from .tokens import create_jwt_pair_for_user

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_payload(**kwargs):
    """
    Encrypt a dict and JSON-encode the result.
    Views call decrypt(request.data). DRF's JSON parser returns whatever
    the body parses to — so wrapping the base64 string in JSON quotes
    means request.data will be the base64 string, not a dict.
    """
    return _json.dumps(encrypt(kwargs))


def _user_kwargs(**overrides):
    base = dict(
        phone_number="2348000000001",
        password="SecurePass123!",
        first_name="Test",
        last_name="User",
        email="test@example.com",
        country="NG",
        state="Lagos",
        city="Ikeja",
        is_verified=True,
        active_role="Member",
    )
    base.update(overrides)
    return base


def _create_user(**overrides):
    kwargs = _user_kwargs(**overrides)
    password = kwargs.pop("password")
    user = User.objects.create(**kwargs)
    user.set_password(password)
    user.save()
    return user


def _expire_otp(otp):
    otp_obj = OTP.objects.get(otp=otp)
    otp_obj.expires_at = timezone.now() - timedelta(seconds=1)
    otp_obj.save(update_fields=["expires_at"])
    return otp_obj


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


class OTPManagerTests(APITestCase):
    def setUp(self):
        self.user = _create_user()
        self.manager = OTPManager()

    def test_create_otp_returns_4_digit_string(self):
        otp = self.manager.create_otp(user_id=str(self.user.id))

        self.assertEqual(len(otp), 4)
        self.assertTrue(otp.isdigit())

    def test_create_otp_replaces_existing_otp(self):
        self.manager.create_otp(user_id=str(self.user.id))
        self.manager.create_otp(user_id=str(self.user.id))

        self.assertEqual(OTP.objects.filter(user_id=self.user.id).count(), 1)

    def test_validate_invalid_otp_returns_none(self):
        result = self.manager.validate_user_otp("0000")

        self.assertIsNone(result)


class JWTTokenTests(APITestCase):
    def test_create_jwt_pair_returns_access_and_refresh(self):
        user = _create_user()

        tokens = create_jwt_pair_for_user(user)

        self.assertIn("access", tokens)
        self.assertIn("refresh", tokens)
        self.assertIsInstance(tokens["access"], str)
        self.assertIsInstance(tokens["refresh"], str)


class UserModelTests(APITestCase):
    def test_user_string_representation_returns_phone_number(self):
        user = _create_user(phone_number="2348000000099")

        self.assertEqual(str(user), "2348000000099")

    def test_update_level_promotes_user_based_on_total_points(self):
        user = _create_user(total_points=3200)

        user.update_level()

        self.assertEqual(user.level, "Influencer")


# ---------------------------------------------------------------------------
# Register endpoint
# ---------------------------------------------------------------------------


@patch("accounts.views.Messaging")
@patch("accounts.views.Points")
class RegisterEndpointTests(APITestCase):
    url = "/v1/accounts/register"

    def _valid_payload(self, **overrides):
        data = dict(
            f_name="Jane",
            first_name="Jane",
            last_name="Doe",
            email="newuser@example.com",
            phone_number="2348011111111",
            password="StrongPass123!",
            password2="StrongPass123!",
            device_id="device-abc-123456",
            device_name="iPhone-15-Pro",
            device_os="iOS-17-5-1",
            country="NG",
            state="Lagos",
            city="Ikeja",
            consent_given=True,
        )
        data.update(overrides)
        return _make_payload(**data)

    def test_register_duplicate_email_returns_400(self, mock_points, mock_msg):
        _create_user(email="newuser@example.com", phone_number="2348099999999")

        response = self.client.post(
            self.url,
            data=self._valid_payload(),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = decrypt(response.data)
        self.assertEqual(body["status"], "fail")
        self.assertIn("email", body["message"].lower())

    def test_register_duplicate_phone_returns_400(self, mock_points, mock_msg):
        _create_user(phone_number="2348011111111", email="other@example.com")

        response = self.client.post(
            self.url,
            data=self._valid_payload(),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = decrypt(response.data)
        self.assertEqual(body["status"], "fail")
        self.assertIn("phone", body["message"].lower())

    def test_register_password_mismatch_returns_400(self, mock_points, mock_msg):
        response = self.client.post(
            self.url,
            data=self._valid_payload(password2="WrongPass999!"),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = decrypt(response.data)
        self.assertEqual(body["status"], "fail")

    def test_register_success_creates_user(self, mock_points, mock_msg):
        response = self.client.post(
            self.url,
            data=self._valid_payload(),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        body = decrypt(response.data)
        self.assertEqual(body["status"], "success")
        self.assertTrue(User.objects.filter(email="newuser@example.com").exists())
        user = User.objects.get(email="newuser@example.com")
        self.assertTrue(
            AccountType.objects.filter(user=user, user_type="Member").exists()
        )
        self.assertTrue(
            DeviceId.objects.filter(user=user, device_id="device-abc-123456").exists()
        )
        self.assertTrue(user.referral_code)

    def test_register_with_unknown_referred_by_code_returns_400(
        self, mock_points, mock_msg
    ):
        response = self.client.post(
            self.url,
            data=self._valid_payload(referred_by_code="DOESNOTEXIST"),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = decrypt(response.data)
        self.assertEqual(body["status"], "fail")
        self.assertIn("referral code", body["message"].lower())
        self.assertFalse(User.objects.filter(email="newuser@example.com").exists())

    def test_register_with_valid_referred_by_code_records_referral(
        self, mock_points, mock_msg
    ):
        from gamification.models import Referral

        referrer = _create_user(
            email="referrer@example.com",
            phone_number="2348022222222",
            is_verified=True,
        )
        referrer.referral_code = "REFCODE1"
        referrer.save(update_fields=["referral_code"])

        response = self.client.post(
            self.url,
            data=self._valid_payload(referred_by_code="REFCODE1"),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        new_user = User.objects.get(email="newuser@example.com")
        referral = Referral.objects.get(referred=new_user)
        self.assertEqual(referral.referrer, referrer)
        self.assertTrue(referral.counted)

        referrer.refresh_from_db()
        self.assertEqual(referrer.referral_count, 1)

    def test_register_with_walk_to_earn_code_credits_separate_counter(
        self, mock_points, mock_msg
    ):
        """Signing up with a walk_to_earn_referral_code must credit
        walk_to_earn_referral_count only - never referral_count/
        gamification tasks, which the regular referral_code path is for."""
        from gamification.models import Referral

        referrer = _create_user(
            email="referrer@example.com",
            phone_number="2348022222222",
            is_verified=True,
        )
        referrer.walk_to_earn_referral_code = "REFCODE1WALK"
        referrer.save(update_fields=["walk_to_earn_referral_code"])

        response = self.client.post(
            self.url,
            data=self._valid_payload(referred_by_code="REFCODE1WALK"),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        new_user = User.objects.get(email="newuser@example.com")
        referral = Referral.objects.get(referred=new_user)
        self.assertEqual(referral.referrer, referrer)
        self.assertEqual(referral.referral_type, "walk_to_earn")
        self.assertTrue(referral.counted)

        referrer.refresh_from_db()
        self.assertEqual(referrer.walk_to_earn_referral_count, 1)
        self.assertEqual(referrer.referral_count, 0)


# ---------------------------------------------------------------------------
# Login endpoint
# ---------------------------------------------------------------------------


@patch("accounts.views.Messaging")
class LoginEndpointTests(APITestCase):
    url = "/v1/accounts/login"

    def setUp(self):
        self.user = _create_user()
        # Register a known device
        DeviceId.objects.create(
            user=self.user,
            device_id="device-123",
            device_name="iPhone",
            device_os="iOS",
        )

    def _payload(self, **overrides):
        data = dict(
            phone_number="2348000000001",
            password="SecurePass123!",
            device_id="device-123",
            device_name="iPhone",
            device_os="iOS",
        )
        data.update(overrides)
        return _make_payload(**data)

    def test_login_invalid_credentials_returns_401(self, mock_msg):
        response = self.client.post(
            self.url,
            data=self._payload(password="wrongpassword"),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_login_unverified_user_returns_401(self, mock_msg):
        unverified = _create_user(
            phone_number="2348000000002",
            email="unverified@example.com",
            is_verified=False,
        )
        DeviceId.objects.create(
            user=unverified,
            device_id="device-123",
            device_name="iPhone",
            device_os="iOS",
        )

        response = self.client.post(
            self.url,
            data=_make_payload(
                phone_number="2348000000002",
                password="SecurePass123!",
                device_id="device-123",
                device_name="iPhone",
                device_os="iOS",
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        body = decrypt(response.data)
        self.assertEqual(body["status"], "fail")

    def test_login_new_device_triggers_otp(self, mock_msg):
        response = self.client.post(
            self.url,
            data=self._payload(
                device_id="unknown-device",
                device_name="Android",
                device_os="Android 13",
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = decrypt(response.data)
        self.assertIn("New device", body["error"])

    def test_login_known_device_returns_tokens(self, mock_msg):
        response = self.client.post(
            self.url,
            data=self._payload(),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.data)
        self.assertEqual(body["status"], "success")
        self.assertIn("access", body["tokens"])
        self.assertIn("refresh", body["tokens"])


# ---------------------------------------------------------------------------
# OTP verify endpoint
# ---------------------------------------------------------------------------


@patch("accounts.views.Messaging")
class OTPVerifyEndpointTests(APITestCase):
    url = "/v1/accounts/verify-otp"

    def test_verify_invalid_otp_returns_400(self, mock_msg):
        response = self.client.post(
            self.url,
            data=_make_payload(otp="9999"),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = decrypt(response.data)
        self.assertEqual(body["status"], "fail")

    def test_verify_valid_otp_verifies_user(self, mock_msg):
        user = _create_user(
            phone_number="2348000000003", email="otp@example.com", is_verified=False
        )
        manager = OTPManager()
        otp = manager.create_otp(user_id=str(user.id))

        response = self.client.post(
            self.url,
            data=_make_payload(otp=otp),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.data)
        self.assertEqual(body["status"], "success")
        self.assertIn("tokens", body)

    def test_verify_expired_otp_returns_400(self, mock_msg):
        user = _create_user(
            phone_number="2348000000099", email="expired@example.com", is_verified=False
        )
        otp = OTPManager().create_otp(user_id=str(user.id))
        _expire_otp(otp)

        response = self.client.post(
            self.url,
            data=_make_payload(otp=otp),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        user.refresh_from_db()
        self.assertFalse(user.is_verified)


@patch("accounts.views.Messaging")
class DeviceVerificationEndpointTests(APITestCase):
    url = "/v1/accounts/new-device-otp"

    def test_verify_new_device_invalid_otp_returns_400(self, mock_msg):
        response = self.client.post(
            self.url,
            data=_make_payload(
                otp="9999",
                device_Id="new-device-001",
                device_name="Android",
                device_os="Android 14",
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = decrypt(response.data)
        self.assertEqual(body["status"], "fail")

    def test_verify_new_device_replaces_old_device_and_returns_tokens(self, mock_msg):
        user = _create_user(
            phone_number="2348000000004", email="device@example.com", is_verified=False
        )
        DeviceId.objects.create(
            user=user, device_id="old-device", device_name="iPhone", device_os="iOS"
        )
        otp = OTPManager().create_otp(user_id=str(user.id))

        response = self.client.post(
            self.url,
            data=_make_payload(
                otp=otp,
                device_Id="new-device-001",
                device_name="Pixel",
                device_os="Android 14",
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.data)
        self.assertEqual(body["status"], "success")
        self.assertTrue(
            DeviceId.objects.filter(user=user, device_id="new-device-001").exists()
        )
        self.assertFalse(
            DeviceId.objects.filter(user=user, device_id="old-device").exists()
        )


@patch("accounts.views.Messaging")
class ResendOTPEndpointTests(APITestCase):
    url = "/v1/accounts/resend-otp"

    def test_resend_otp_success_returns_200_and_creates_otp(self, mock_msg):
        user = _create_user(phone_number="2348000000005", email="resend@example.com")

        response = self.client.post(
            self.url,
            data=_make_payload(id=user.id, phone_number=user.phone_number),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.data)
        self.assertEqual(body["status"], "success")
        self.assertTrue(OTP.objects.filter(user_id=user.id).exists())


@patch("accounts.views.Messaging")
class PasswordResendOTPEndpointTests(APITestCase):
    url = "/v1/accounts/password-resend-otp"

    def test_password_resend_otp_unknown_user_returns_404(self, mock_msg):
        response = self.client.post(
            self.url,
            data=_make_payload(phone_number="2348999999999"),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        body = decrypt(response.data)
        self.assertEqual(body["status"], "fail")

    def test_password_resend_otp_success_returns_200(self, mock_msg):
        user = _create_user(
            phone_number="2348000000006", email="passwordresend@example.com"
        )

        response = self.client.post(
            self.url,
            data=_make_payload(phone_number=user.phone_number),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.data)
        self.assertEqual(body["status"], "success")
        self.assertTrue(OTP.objects.filter(user_id=user.id).exists())


@patch("accounts.views.Messaging")
class ForgotPasswordEndpointTests(APITestCase):
    url = "/v1/accounts/forgot-password"

    def test_forgot_password_unknown_user_returns_404(self, mock_msg):
        response = self.client.post(
            self.url,
            data=_make_payload(phone_number="2348999999999"),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        body = decrypt(response.data)
        self.assertEqual(body["status"], "fail")

    def test_forgot_password_success_creates_notification_and_otp(self, mock_msg):
        user = _create_user(phone_number="2348000000007", email="forgot@example.com")

        response = self.client.post(
            self.url,
            data=_make_payload(phone_number=user.phone_number),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        body = decrypt(response.data)
        self.assertEqual(body["status"], "success")
        self.assertTrue(OTP.objects.filter(user_id=user.id).exists())
        self.assertTrue(
            UserNotification.objects.filter(
                user=user, title="Forgot Password Request."
            ).exists()
        )


@patch("accounts.views.Messaging")
class PasswordPhoneVerifyOTPEndpointTests(APITestCase):
    url = "/v1/accounts/password-verify-otp"

    def test_password_verify_otp_invalid_code_returns_400(self, mock_msg):
        response = self.client.post(
            self.url,
            data=_make_payload(otp="9999"),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = decrypt(response.data)
        self.assertEqual(body["status"], "fail")

    def test_password_verify_otp_success_returns_user_id(self, mock_msg):
        user = _create_user(phone_number="2348000000008", email="pwdverify@example.com")
        otp = OTPManager().create_otp(user_id=str(user.id))

        response = self.client.post(
            self.url,
            data=_make_payload(otp=otp),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.data)
        self.assertEqual(body["status"], "success")
        self.assertEqual(str(body["user_id"]), str(user.id))


class ResetPasswordEndpointTests(APITestCase):
    url = "/v1/accounts/password-reset"

    def test_reset_password_mismatch_returns_400(self):
        user = _create_user(
            phone_number="2348000000010", email="reset-mismatch@example.com"
        )

        response = self.client.post(
            self.url,
            data=_make_payload(
                user_id=str(user.id),
                password="NewStrongPass123!",
                password2="WrongPass123!",
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = decrypt(response.data)
        self.assertIn("Passwords do not match", body["error"])

    def test_reset_password_success_updates_password(self):
        user = _create_user(phone_number="2348000000011", email="reset@example.com")

        response = self.client.post(
            self.url,
            data=_make_payload(
                user_id=str(user.id),
                password="NewStrongPass123!",
                password2="NewStrongPass123!",
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.data)
        self.assertEqual(body["status"], "success")
        user.refresh_from_db()
        self.assertTrue(user.check_password("NewStrongPass123!"))


class LogoutEndpointTests(APITestCase):
    url = "/v1/accounts/logout"

    def test_logout_requires_authentication(self):
        user = _create_user(phone_number="2348000000012", email="logout@example.com")
        tokens = create_jwt_pair_for_user(user)

        response = self.client.post(
            self.url,
            data=_make_payload(refresh_token=tokens["refresh"]),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_success_blacklists_token(self):
        user = _create_user(
            phone_number="2348000000013", email="logout-success@example.com"
        )
        tokens = create_jwt_pair_for_user(user)
        self.client.force_authenticate(user=user)

        response = self.client.post(
            self.url,
            data=_make_payload(refresh_token=tokens["refresh"]),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_205_RESET_CONTENT)
        body = decrypt(response.data)
        self.assertEqual(body["status"], "success")


class SingleSessionEnforcementTests(APITestCase):
    """Admin/support roles get one active session; a new login ends the old one."""

    logout_url = "/v1/accounts/logout"

    def _auth(self, access):
        return {"HTTP_AUTHORIZATION": f"Bearer {access}"}

    def test_privileged_login_sets_session_id_and_sid_claim(self):
        user = _create_user(
            phone_number="2348001112221",
            email="admin-sess@example.com",
            active_role="SuperAdmin",
        )
        tokens = create_jwt_pair_for_user(user)

        user.refresh_from_db()
        self.assertIsNotNone(user.active_session_id)

        from rest_framework_simplejwt.tokens import AccessToken

        self.assertEqual(
            str(AccessToken(tokens["access"])["sid"]), str(user.active_session_id)
        )

    def test_second_login_supersedes_first_session(self):
        user = _create_user(
            phone_number="2348001112222",
            email="admin-super@example.com",
            active_role="TaskAdmin",
        )
        first = create_jwt_pair_for_user(user)

        # First token works before the second login.
        ok = self.client.post(
            self.logout_url,
            data=_make_payload(refresh_token=first["refresh"]),
            content_type="application/json",
            **self._auth(first["access"]),
        )
        self.assertEqual(ok.status_code, status.HTTP_205_RESET_CONTENT)

        # Re-login (logout cleared the session id), then a brand-new login.
        create_jwt_pair_for_user(user)
        second = create_jwt_pair_for_user(user)

        stale = self.client.post(
            self.logout_url,
            data=_make_payload(refresh_token=second["refresh"]),
            content_type="application/json",
            **self._auth(first["access"]),
        )
        self.assertEqual(stale.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(stale.data["code"], "session_superseded")

        fresh = self.client.post(
            self.logout_url,
            data=_make_payload(refresh_token=second["refresh"]),
            content_type="application/json",
            **self._auth(second["access"]),
        )
        self.assertEqual(fresh.status_code, status.HTTP_205_RESET_CONTENT)

    def test_regular_user_is_not_session_limited(self):
        user = _create_user(
            phone_number="2348001112223",
            email="member-sess@example.com",
            active_role="Member",
        )
        first = create_jwt_pair_for_user(user)
        create_jwt_pair_for_user(user)

        user.refresh_from_db()
        self.assertIsNone(user.active_session_id)

        resp = self.client.post(
            self.logout_url,
            data=_make_payload(refresh_token=first["refresh"]),
            content_type="application/json",
            **self._auth(first["access"]),
        )
        self.assertEqual(resp.status_code, status.HTTP_205_RESET_CONTENT)
