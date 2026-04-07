import json as _json
from unittest.mock import patch

from django.contrib.auth.hashers import check_password
from django.core.cache import cache
from django.utils import timezone
from datetime import timedelta

from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import AccountType, DeviceId, OTP, User, UserNotification
from security import decrypt, encrypt
from .models import ADMIN_TYPES


def _make_payload(**kwargs):
    return _json.dumps(encrypt(kwargs))


def _create_user(**overrides):
    payload = {
        "phone_number": "2348111111111",
        "password": "StrongPass123!",
        "email": "admin@example.com",
        "first_name": "Admin",
        "last_name": "User",
        "full_name": "Admin User",
        "country": "NG",
        "state": "Lagos",
        "city": "Ikeja",
        "is_verified": True,
        "active_role": "SuperAdmin",
    }
    payload.update(overrides)
    password = payload.pop("password")
    user = User.objects.create(**payload)
    user.set_password(password)
    user.save()
    return user


def _expire_otp(otp):
    otp_obj = OTP.objects.get(otp=otp)
    otp_obj.expires_at = timezone.now() - timedelta(seconds=1)
    otp_obj.save(update_fields=["expires_at"])
    return otp_obj


class RolesModelTests(APITestCase):
    def test_admin_types_constant_contains_expected_roles(self):
        admin_types = [role for role, _ in ADMIN_TYPES]

        self.assertIn("TaskAdmin", admin_types)
        self.assertIn("WalletAdmin", admin_types)
        self.assertIn("FmcgAdmin", admin_types)


@patch("roles.views.Messaging")
class RegisterSuperAdminEndpointTests(APITestCase):
    url = "/v1/roles/register-super-admin"

    def setUp(self):
        cache.clear()

    def _payload(self, **overrides):
        data = {
            "email": "superadmin@example.com",
            "phone_number": "2348222222222",
            "password": "StrongPass123!",
            "password2": "StrongPass123!",
            "device_id": "super-device-123",
        }
        data.update(overrides)
        return _make_payload(**data)

    def test_register_super_admin_returns_403_if_one_exists(self, mock_msg):
        _create_user(
            email="existing-super@example.com",
            phone_number="2348333333333",
            active_role="SuperAdmin",
        )

        response = self.client.post(
            self.url,
            data=self._payload(),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            response.data, "Registration is not allowed. Super admin already exists."
        )

    def test_register_super_admin_success_creates_user_account_type_and_otp(
        self, mock_msg
    ):
        response = self.client.post(
            self.url,
            data=self._payload(),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        body = decrypt(response.data)
        self.assertEqual(body["status"], "success")
        user = User.objects.get(email="superadmin@example.com")
        self.assertEqual(user.active_role, "SuperAdmin")
        self.assertTrue(
            AccountType.objects.filter(user=user, user_type="SuperAdmin").exists()
        )
        self.assertTrue(OTP.objects.filter(user_id=user.id).exists())


class LoginAdminEndpointTests(APITestCase):
    url = "/v1/roles/admin-login"

    def setUp(self):
        cache.clear()

    def _payload(self, **overrides):
        data = {
            "email": "adminlogin@example.com",
            "password": "StrongPass123!",
        }
        data.update(overrides)
        return _make_payload(**data)

    def test_login_admin_unknown_email_returns_401(self):
        response = self.client.post(
            self.url,
            data=self._payload(),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        body = decrypt(response.data)
        self.assertEqual(body["error"], "Invalid credentials")

    def test_login_admin_unverified_user_returns_401(self):
        user = _create_user(
            email="adminlogin@example.com",
            phone_number="2348444444444",
            is_verified=False,
            active_role="TaskAdmin",
        )
        AccountType.objects.create(user=user, user_type="TaskAdmin")

        response = self.client.post(
            self.url,
            data=self._payload(),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        body = decrypt(response.data)
        self.assertEqual(body["status"], "fail")

    def test_login_admin_existing_device_returns_400(self):
        user = _create_user(
            email="adminlogin@example.com",
            phone_number="2348555555555",
            active_role="TaskAdmin",
        )
        AccountType.objects.create(user=user, user_type="TaskAdmin")
        DeviceId.objects.create(user=user, device_id="existing-device")

        response = self.client.post(
            self.url,
            data=self._payload(),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = decrypt(response.data)
        self.assertIn("more than two devices", body["error"])

    def test_login_admin_success_returns_tokens_and_roles(self):
        user = _create_user(
            email="adminlogin@example.com",
            phone_number="2348666666666",
            active_role="TaskAdmin",
            full_name="Task Admin",
        )
        AccountType.objects.create(user=user, user_type="TaskAdmin")
        AccountType.objects.create(user=user, user_type="WalletAdmin")

        response = self.client.post(
            self.url,
            data=self._payload(),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.data)
        self.assertEqual(body["status"], "success")
        self.assertIn("access", body["tokens"])
        self.assertIn("TaskAdmin", body["user_data"]["roles"])
        self.assertIn("WalletAdmin", body["user_data"]["roles"])


class RolesAdminListEndpointTests(APITestCase):
    admin_types_url = "/v1/roles/list-admin-types"
    admin_users_url = "/v1/roles/list-admin-users"
    admin_user_types_url = "/v1/roles/list-admin-user-types"

    def setUp(self):
        cache.clear()
        self.superadmin = _create_user(
            email="super@example.com",
            phone_number="2348777777777",
            active_role="SuperAdmin",
        )
        AccountType.objects.create(user=self.superadmin, user_type="SuperAdmin")

    def test_admin_types_requires_authentication(self):
        response = self.client.get(self.admin_types_url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_admin_types_returns_encrypted_categories_for_superadmin(self):
        self.client.force_authenticate(user=self.superadmin)

        response = self.client.get(self.admin_types_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.data)
        self.assertEqual(body["status"], "success.")
        self.assertIn("TaskAdmin", body["categories"])
        self.assertIn("WalletAdmin", body["categories"])

    def test_list_admin_users_returns_counts_for_superadmin(self):
        first_admin = _create_user(
            email="taskadmin@example.com",
            phone_number="2348888888888",
            active_role="TaskAdmin",
            is_admin_disabled=False,
        )
        second_admin = _create_user(
            email="walletadmin@example.com",
            phone_number="2348999999998",
            active_role="WalletAdmin",
            is_admin_disabled=True,
        )
        AccountType.objects.create(user=first_admin, user_type="TaskAdmin")
        AccountType.objects.create(user=second_admin, user_type="WalletAdmin")
        self.client.force_authenticate(user=self.superadmin)

        response = self.client.get(self.admin_users_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.data)
        self.assertEqual(body["status"], "success")
        self.assertEqual(body["num_of_admin_users"], 3)
        self.assertEqual(body["num_of_active_admin_users"], 2)
        self.assertEqual(body["num_of_disabled_admin_users"], 1)
        self.assertEqual(len(body["admin_users"]), 3)

    def test_list_admin_user_types_groups_roles(self):
        first_admin = _create_user(
            email="taskadmin2@example.com",
            phone_number="2348999999997",
            active_role="TaskAdmin",
        )
        second_admin = _create_user(
            email="walletadmin2@example.com",
            phone_number="2348999999996",
            active_role="WalletAdmin",
        )
        AccountType.objects.create(user=first_admin, user_type="TaskAdmin")
        AccountType.objects.create(user=second_admin, user_type="WalletAdmin")
        self.client.force_authenticate(user=self.superadmin)

        response = self.client.get(self.admin_user_types_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.data)
        self.assertEqual(body["status"], "success")
        self.assertEqual(body["admin_role_counts"]["TaskAdmin"], 1)
        self.assertEqual(body["admin_role_counts"]["WalletAdmin"], 1)


class SetAdminPinEndpointTests(APITestCase):
    url = "/v1/roles/set-admin-pin"

    def setUp(self):
        cache.clear()
        self.admin = _create_user(
            email="pinadmin@example.com",
            phone_number="2348999999995",
            active_role="TaskAdmin",
        )
        AccountType.objects.create(user=self.admin, user_type="TaskAdmin")

    def test_set_admin_pin_requires_authentication(self):
        response = self.client.post(
            self.url,
            data=_make_payload(pin="12345"),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_set_admin_pin_success_hashes_pin(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            self.url,
            data=_make_payload(pin="12345"),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        body = decrypt(response.data)
        self.assertEqual(body["status"], "success")
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_admin_pin_set)
        self.assertTrue(check_password("12345", self.admin.admin_pin))
        self.assertTrue(
            UserNotification.objects.filter(user=self.admin, title="Admin Pin").exists()
        )


@patch("roles.views.Messaging")
class StaffForgotPasswordEndpointTests(APITestCase):
    url = "/v1/roles/staff-forgot-password"

    def setUp(self):
        cache.clear()

    def test_staff_forgot_password_unknown_user_returns_generic_success(self, mock_msg):
        response = self.client.post(
            self.url,
            data=_make_payload(email="missingstaff@example.com"),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.data)
        self.assertEqual(body["status"], "success")

    def test_staff_forgot_password_non_staff_account_returns_403(self, mock_msg):
        user = _create_user(
            email="member@example.com",
            phone_number="2348999999994",
            active_role="Member",
        )
        AccountType.objects.create(user=user, user_type="Member")

        response = self.client.post(
            self.url,
            data=_make_payload(email=user.email),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        body = decrypt(response.data)
        self.assertEqual(body["status"], "fail")

    def test_staff_forgot_password_staff_account_returns_201_and_creates_otp(
        self, mock_msg
    ):
        user = _create_user(
            email="staff@example.com",
            phone_number="2348999999993",
            active_role="WalletAdmin",
            full_name="Wallet Admin",
        )
        AccountType.objects.create(user=user, user_type="WalletAdmin")

        response = self.client.post(
            self.url,
            data=_make_payload(email=user.email),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        body = decrypt(response.data)
        self.assertEqual(body["status"], "success")
        self.assertTrue(OTP.objects.filter(user_id=user.id).exists())


@patch("roles.views.Messaging")
class StaffPasswordFlowEndpointTests(APITestCase):
    resend_url = "/v1/roles/staff-password-resend-otp"
    verify_url = "/v1/roles/staff-email-verify-otp"
    reset_url = "/v1/roles/staff-reset-password"

    def setUp(self):
        cache.clear()
        self.staff = _create_user(
            email="role-staff@example.com",
            phone_number="2348999999992",
            active_role="TaskAdmin",
            full_name="Role Staff",
        )
        AccountType.objects.create(user=self.staff, user_type="TaskAdmin")

    def test_staff_password_resend_unknown_user_returns_404(self, mock_msg):
        response = self.client.post(
            self.resend_url,
            data=_make_payload(email="missing@example.com"),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        body = decrypt(response.data)
        self.assertEqual(body["status"], "fail")

    def test_staff_password_resend_success_returns_200(self, mock_msg):
        response = self.client.post(
            self.resend_url,
            data=_make_payload(email=self.staff.email),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.data)
        self.assertEqual(body["status"], "success")
        self.assertTrue(OTP.objects.filter(user_id=self.staff.id).exists())

    def test_staff_email_verify_invalid_otp_returns_400(self, mock_msg):
        response = self.client.post(
            self.verify_url,
            data=_make_payload(otp="9999"),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = decrypt(response.data)
        self.assertEqual(body["status"], "fail")

    def test_staff_email_verify_success_returns_user_id(self, mock_msg):
        from accounts.otp import otp_manager

        otp = otp_manager.create_otp(user_id=str(self.staff.id))
        _expire_otp(otp)

        response = self.client.post(
            self.verify_url,
            data=_make_payload(otp=otp),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.data)
        self.assertEqual(body["status"], "success")
        self.assertEqual(str(body["user_id"]), str(self.staff.id))

    def test_staff_reset_password_mismatch_returns_400(self, mock_msg):
        response = self.client.post(
            self.reset_url,
            data=_make_payload(
                admin_id=str(self.staff.id),
                password="NewStrongPass123!",
                password2="WrongStrongPass123!",
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = decrypt(response.data)
        self.assertIn("Passwords do not match", body["error"])

    def test_staff_reset_password_success_updates_password(self, mock_msg):
        response = self.client.post(
            self.reset_url,
            data=_make_payload(
                admin_id=str(self.staff.id),
                password="NewStrongPass123!",
                password2="NewStrongPass123!",
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.data)
        self.assertEqual(body["status"], "success")
        self.staff.refresh_from_db()
        self.assertTrue(self.staff.check_password("NewStrongPass123!"))


@patch("roles.views.Messaging")
class AdminPinFlowEndpointTests(APITestCase):
    forgot_url = "/v1/roles/admin-forgot-pin"
    verify_url = "/v1/roles/verify-pin-otp"
    reset_url = "/v1/roles/reset-pin"

    def setUp(self):
        cache.clear()
        self.admin = _create_user(
            email="pinflow@example.com",
            phone_number="2348999999991",
            active_role="SuperAdmin",
        )
        AccountType.objects.create(user=self.admin, user_type="SuperAdmin")

    def test_admin_forgot_pin_unknown_user_returns_404(self, mock_msg):
        response = self.client.post(
            self.forgot_url,
            data=_make_payload(email="missingpin@example.com"),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        body = decrypt(response.data)
        self.assertEqual(body["status"], "fail")

    def test_admin_forgot_pin_success_creates_otp(self, mock_msg):
        response = self.client.post(
            self.forgot_url,
            data=_make_payload(email=self.admin.email),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        body = decrypt(response.data)
        self.assertEqual(body["status"], "success")
        self.assertTrue(OTP.objects.filter(user_id=self.admin.id).exists())

    def test_verify_pin_otp_invalid_returns_400(self, mock_msg):
        response = self.client.post(
            self.verify_url,
            data=_make_payload(otp="9999"),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = decrypt(response.data)
        self.assertEqual(body["status"], "fail")

    def test_verify_pin_otp_success_returns_user_id(self, mock_msg):
        from accounts.otp import otp_manager

        otp = otp_manager.create_otp(user_id=str(self.admin.id))
        _expire_otp(otp)

        response = self.client.post(
            self.verify_url,
            data=_make_payload(otp=otp),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.data)
        self.assertEqual(body["status"], "success")
        self.assertEqual(str(body["user_id"]), str(self.admin.id))

    def test_reset_pin_mismatch_returns_400(self, mock_msg):
        response = self.client.post(
            self.reset_url,
            data=_make_payload(admin_id=str(self.admin.id), pin="12345", pin2="54321"),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = decrypt(response.data)
        self.assertIn("Pins do not match", body["error"])

    def test_reset_pin_success_updates_hashed_pin(self, mock_msg):
        response = self.client.post(
            self.reset_url,
            data=_make_payload(admin_id=str(self.admin.id), pin="12345", pin2="12345"),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.data)
        self.assertEqual(body["status"], "success")
        self.admin.refresh_from_db()
        self.assertTrue(check_password("12345", self.admin.admin_pin))


class SwitchRolesEndpointTests(APITestCase):
    url = "/v1/roles/switch-roles"

    def setUp(self):
        cache.clear()
        self.admin = _create_user(
            email="switchroles@example.com",
            phone_number="2348999999990",
            active_role="TaskAdmin",
            full_name="Switch Roles",
        )
        AccountType.objects.create(user=self.admin, user_type="TaskAdmin")
        AccountType.objects.create(user=self.admin, user_type="WalletAdmin")

    def test_switch_roles_requires_authentication(self):
        response = self.client.put(
            self.url,
            data=_make_payload(user_type="WalletAdmin"),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_switch_roles_rejects_unassigned_role(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.put(
            self.url,
            data=_make_payload(user_type="MembersAdmin"),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = decrypt(response.data)
        self.assertEqual(body["status"], "fail")

    def test_switch_roles_returns_message_when_role_is_already_active(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.put(
            self.url,
            data=_make_payload(user_type="TaskAdmin"),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.data)
        self.assertEqual(body["status"], "success")
        self.assertIn("already on the TaskAdmin screen", body["message"])

    def test_switch_roles_success_updates_active_role(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.put(
            self.url,
            data=_make_payload(user_type="WalletAdmin"),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.data)
        self.assertEqual(body["status"], "success")
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.active_role, "WalletAdmin")
