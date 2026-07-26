import json as _json
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth.hashers import check_password
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from datetime import timedelta
from django.urls import reverse


from rest_framework.test import APIClient
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import AccountType, DeviceId, OTP, TxModel, User, UserNotification
from banking.models import WalletModel
from partners.models import PartnerServices, PartnerPurchase
from support.models import Ticket
from security import decrypt, encrypt
from .models import ADMIN_TYPES, knowledgeBaseModel
from .analytics import (
    _tx_category,
    get_pending_settlement_list,
    get_transaction_detail_row,
    get_reconciliation_differences_queryset,
    get_reconciliation_differences_count,
    get_reconciliation_differences_list,
    get_reconciliation_difference_detail,
    get_duplicate_transaction_pairs,
    get_duplicate_transactions_list,
    get_duplicate_transaction_detail,
    get_fraud_alerts_list,
    get_alert_and_risk_snapshot,
    get_all_transactions,
    RECONCILIATION_GRACE_PERIOD_HOURS,
    DUPLICATE_TRANSACTION_WINDOW_MINUTES,
)


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


# ── Admin: Pending Submissions Queue ─────────────────────────────────────────


class PendingSubmissionsAdminViewTests(APITestCase):
    url = "/v1/roles/tasks/pending/"

    def setUp(self):
        cache.clear()
        seed = uuid4().hex[:8]
        self.admin = _create_user(
            email=f"pend-admin-{seed}@example.com",
            phone_number=f"23482{seed[:7]}",
            active_role="AdAdmin",
        )
        self.member = _create_user(
            email=f"pend-member-{seed}@example.com",
            phone_number=f"23483{seed[:7]}",
            active_role="Member",
        )
        self.brand = _create_user(
            email=f"pend-brand-{seed}@example.com",
            phone_number=f"23484{seed[:7]}",
            active_role="BrandAd",
        )

    def test_requires_authentication(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_admin_is_denied(self):
        self.client.force_authenticate(user=self.member)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_returns_combined_pending_social_and_brand_counts(self):
        from adverts.models import CreateAd
        from tasks.models import BrandTaskSubmission, SocialTask, TaskSubmission

        ad = CreateAd.objects.create(
            user=self.brand,
            campaign_name="Brand Pending",
            task_type="social_engage",
            is_active=True,
        )
        BrandTaskSubmission.objects.create(ad=ad, user=self.member, status="Pending")

        task = SocialTask.objects.create(
            title="Follow Us",
            platform="X",
            task_type="Follow",
            is_active=True,
            created_by=self.admin,
        )
        TaskSubmission.objects.create(
            task=task,
            user=self.member,
            screenshot_url="https://cdn.example.com/ss.png",
            status="Pending",
        )

        self.client.force_authenticate(user=self.admin)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.data)
        self.assertEqual(body["status"], "success")
        self.assertEqual(body["brand"]["total"], 1)
        self.assertEqual(body["social"]["total"], 1)

    def test_approved_submissions_are_excluded_from_queue(self):
        from adverts.models import CreateAd
        from tasks.models import BrandTaskSubmission

        ad = CreateAd.objects.create(
            user=self.brand,
            campaign_name="Approved Campaign",
            task_type="watch_video",
            is_active=True,
        )
        BrandTaskSubmission.objects.create(ad=ad, user=self.member, status="Approved")

        self.client.force_authenticate(user=self.admin)
        response = self.client.get(self.url)

        body = decrypt(response.data)
        self.assertEqual(body["brand"]["total"], 0)


# ── Admin: Unified Submission Review ─────────────────────────────────────────


class ReviewTaskSubmissionAdminViewTests(APITestCase):
    def _url(self, submission_id):
        return f"/v1/roles/tasks/{submission_id}/review/"

    def setUp(self):
        cache.clear()
        seed = uuid4().hex[:8]
        self.admin = _create_user(
            email=f"rev-admin-{seed}@example.com",
            phone_number=f"23485{seed[:7]}",
            active_role="AdAdmin",
            full_name="Review Admin",
        )
        self.member = _create_user(
            email=f"rev-member-{seed}@example.com",
            phone_number=f"23486{seed[:7]}",
            active_role="Member",
        )
        self.brand = _create_user(
            email=f"rev-brand-{seed}@example.com",
            phone_number=f"23487{seed[:7]}",
            active_role="BrandAd",
        )

    def test_unknown_uuid_returns_404(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            self._url(uuid4()),
            data=_make_payload(action="approve"),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        body = decrypt(response.data)
        self.assertEqual(body["status"], "fail")

    @patch("tasks.jobs.approve_brand_submission.delay")
    def test_approve_brand_submission_queues_celery_task(self, mock_delay):
        from adverts.models import CreateAd
        from tasks.models import BrandTaskSubmission

        ad = CreateAd.objects.create(
            user=self.brand,
            campaign_name="Approve Me",
            task_type="social_engage",
            is_active=True,
        )
        submission = BrandTaskSubmission.objects.create(
            ad=ad,
            user=self.member,
            screenshot_url="https://cdn.example.com/proof.png",
            status="Pending",
        )
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            self._url(submission.pk),
            data=_make_payload(action="approve"),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.data)
        self.assertEqual(body["status"], "success")
        mock_delay.assert_called_once_with(str(submission.pk), str(self.admin.pk))

    @patch("tasks.jobs.reject_brand_submission.delay")
    def test_reject_brand_submission_passes_reason_to_job(self, mock_delay):
        from adverts.models import CreateAd
        from tasks.models import BrandTaskSubmission

        ad = CreateAd.objects.create(
            user=self.brand,
            campaign_name="Reject Me",
            task_type="app_download",
            is_active=True,
        )
        submission = BrandTaskSubmission.objects.create(
            ad=ad,
            user=self.member,
            screenshot_url="https://cdn.example.com/proof2.png",
            status="Pending",
        )
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            self._url(submission.pk),
            data=_make_payload(action="reject", reason="Screenshot unclear"),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_delay.assert_called_once_with(
            str(submission.pk), str(self.admin.pk), "Screenshot unclear"
        )

    @patch("tasks.jobs.manual_approve.delay")
    def test_approve_social_submission_routes_to_manual_approve_job(self, mock_delay):
        from tasks.models import SocialTask, TaskSubmission

        task = SocialTask.objects.create(
            title="Like Our Post",
            platform="Instagram",
            task_type="Like",
            is_active=True,
            created_by=self.admin,
        )
        submission = TaskSubmission.objects.create(
            task=task,
            user=self.member,
            screenshot_url="https://cdn.example.com/ig.png",
            status="Pending",
        )
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            self._url(submission.pk),
            data=_make_payload(action="approve"),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.data)
        self.assertEqual(body["status"], "success")
        mock_delay.assert_called_once_with(str(submission.pk), str(self.admin.pk))


# ==========================================
# Knowledge Base Test Cases
# ==========================================


class KnowledgeBaseModelTest(TestCase):
    """Test cases for the Knowledge Base model."""

    def setUp(self):
        self.article = knowledgeBaseModel.objects.create(
            category="Mobile Services",
            section="Airtime & Data",
            content_type="Website",
            authors=["John Doe", "Jane Smith"],
            caption="How to buy airtime",
            author_image_urls=["https://example.com/author1.jpg"],
            content="Detailed content about buying airtime...",
            ads_and_media_url=["https://example.com/ad1.jpg"],
            ad_description="Promotional ad description",
            is_post_scheduled=False,
        )

    def test_knowledge_base_creation(self):
        """Test that a knowledge base article is created correctly."""
        self.assertEqual(self.article.category, "Mobile Services")
        self.assertEqual(self.article.section, "Airtime & Data")
        self.assertEqual(self.article.content_type, "Website")
        self.assertEqual(len(self.article.authors), 2)
        self.assertEqual(self.article.caption, "How to buy airtime")
        self.assertIsNotNone(self.article.created_at)

    def test_string_representation(self):
        """Test the string representation of the model."""
        expected = f"{self.article.caption}"
        self.assertEqual(str(self.article), expected)

    def test_optional_fields(self):
        """Test that optional fields can be null/blank."""
        article = knowledgeBaseModel.objects.create(
            category="Test",
            section="Banking",
            content_type="Email",
            caption="Test article",
        )
        self.assertEqual([], article.authors)
        self.assertEqual([], article.author_image_urls)
        self.assertEqual([], article.ads_and_media_url)
        self.assertIsNone(article.ad_description)
        self.assertFalse(article.is_post_scheduled)


class KnowledgeBaseListViewTest(TestCase):
    """Test cases for the public KnowledgeBaseListView."""

    def setUp(self):
        self.client = APIClient()
        self.url = reverse("roles:knowledge-base-list")

        # Create articles with different sections and content types
        self.articles = []
        sections = ["Airtime & Data", "Electricity", "Banking", "Brand Ads", "Partners"]
        content_types = ["Website", "Social Post", "Email"]

        for i in range(10):
            article = knowledgeBaseModel.objects.create(
                category=f"Category {i % 3}",
                section=sections[i % len(sections)],
                content_type=content_types[i % len(content_types)],
                authors=[f"Author {i}"],
                caption=f"Article {i}",
                content=f"Content for article {i}",
                is_post_scheduled=i % 2 == 0,
            )
            self.articles.append(article)

    def test_list_all_articles(self):
        """Test that all articles are returned."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # The response should be unencrypted (should_encrypt=False)
        data = response.data
        self.assertEqual(data["status"], "success")
        self.assertEqual(
            data["message"], "Knowledge base articles retrieved successfully."
        )
        self.assertEqual(data["data"]["count"], 10)

    def test_filter_by_section(self):
        """Test filtering articles by section."""
        response = self.client.get(self.url, {"section": "Banking"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.data
        results = data["data"].get("results", [])

        for article in results:
            self.assertEqual(article["section"], "Banking")

    def test_filter_by_content_type(self):
        """Test filtering articles by content type."""
        response = self.client.get(self.url, {"content_type": "Social Post"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.data
        results = data["data"].get("results", [])

        for article in results:
            self.assertEqual(article["content_type"], "Social Post")

    def test_filter_by_category(self):
        """Test filtering articles by category."""
        response = self.client.get(self.url, {"category": "Category 0"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.data
        results = data["data"].get("results", [])

        for article in results:
            self.assertEqual(article["category"], "Category 0")

    def test_multiple_filters(self):
        """Test filtering with multiple parameters."""
        response = self.client.get(
            self.url, {"section": "Airtime & Data", "content_type": "Website"}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.data
        results = data["data"].get("results", [])

        for article in results:
            self.assertEqual(article["section"], "Airtime & Data")
            self.assertEqual(article["content_type"], "Website")

    def test_pagination(self):
        """Test pagination of knowledge base list."""
        # Test default page size (10)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.data
        self.assertEqual(data["data"]["count"], 10)
        self.assertEqual(len(data["data"]["results"]), 10)

        # Test custom page size
        response = self.client.get(self.url, {"page_size": 3})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.data
        self.assertEqual(len(data["data"]["results"]), 3)

    def test_list_serializer_excludes_content(self):
        """Test that the list serializer excludes the 'content' field."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.data
        results = data["data"].get("results", [])

        if results:
            # The content field should not be in the list view
            self.assertNotIn("content", results[0])
            self.assertNotIn("ads_and_media_url", results[0])
            self.assertNotIn("author_image_urls", results[0])

            # These fields should be present
            self.assertIn("id", results[0])
            self.assertIn("category", results[0])
            self.assertIn("section", results[0])
            self.assertIn("content_type", results[0])
            self.assertIn("authors", results[0])
            self.assertIn("caption", results[0])


class KnowledgeBaseDetailViewTest(TestCase):
    """Test cases for the public KnowledgeBaseDetailView."""

    def setUp(self):
        self.client = APIClient()

        # Create a test article
        self.article = knowledgeBaseModel.objects.create(
            category="Mobile Services",
            section="Airtime & Data",
            content_type="Website",
            authors=["John Doe", "Jane Smith"],
            caption="How to buy airtime",
            author_image_urls=["https://example.com/author1.jpg"],
            content="Detailed content about buying airtime on Picadailys platform...",
            ads_and_media_url=["https://example.com/ad1.jpg"],
            ad_description="Special promotion: 10% off on airtime purchases",
            is_post_scheduled=False,
        )

        self.url = reverse(
            "roles:knowledge-base-detail", kwargs={"id": self.article.id}
        )

    def test_retrieve_article_success(self):
        """Test retrieving a knowledge base article successfully."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Response should be unencrypted (should_encrypt=False)
        data = response.data
        self.assertEqual(data["status"], "success")
        self.assertEqual(
            data["message"], "Knowledge base article retrieved successfully."
        )

        article_data = data["data"]
        self.assertEqual(article_data["id"], self.article.id)
        self.assertEqual(article_data["category"], self.article.category)
        self.assertEqual(article_data["section"], self.article.section)
        self.assertEqual(article_data["content_type"], self.article.content_type)
        self.assertEqual(article_data["authors"], self.article.authors)
        self.assertEqual(article_data["caption"], self.article.caption)
        self.assertEqual(
            article_data["author_image_urls"], self.article.author_image_urls
        )
        self.assertEqual(article_data["content"], self.article.content)
        self.assertEqual(
            article_data["ads_and_media_url"], self.article.ads_and_media_url
        )
        self.assertEqual(article_data["ad_description"], self.article.ad_description)

    def test_retrieve_article_not_found(self):
        """Test retrieving a non-existent knowledge base article."""
        non_existent_url = reverse("roles:knowledge-base-detail", kwargs={"id": 99999})
        response = self.client.get(non_existent_url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        data = response.data
        response_status = data["status"]
        message = data["message"]
        self.assertEqual(response_status, "fail")
        self.assertEqual(message, "Knowledge base article not found.")

    def test_detail_serializer_includes_all_fields(self):
        """Test that the detail serializer includes all fields."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.data
        article_data = data["data"]

        # All fields should be present in detail view
        expected_fields = [
            "id",
            "category",
            "section",
            "content_type",
            "authors",
            "caption",
            "author_image_urls",
            "content",
            "ads_and_media_url",
            "ad_description",
            "created_at",
        ]

        for field in expected_fields:
            self.assertIn(field, article_data)


class KnowledgeBaseEdgeCasesTest(TestCase):
    """Test cases for edge cases and error scenarios."""

    def setUp(self):
        self.client = APIClient()
        self.list_url = reverse("roles:knowledge-base-list")

    def test_empty_list(self):
        """Test listing when there are no articles."""
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.data
        self.assertEqual(data["data"]["count"], 0)
        self.assertEqual(data["data"]["results"], [])

    def test_filter_with_no_matches(self):
        """Test filtering with a value that has no matches."""
        response = self.client.get(self.list_url, {"section": "NonExistent"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.data
        self.assertEqual(data["data"]["count"], 0)
        self.assertEqual(data["data"]["results"], [])

    def test_pagination_with_large_page_size(self):
        """Test that pagination max page size is enforced."""
        # Create more than max page size articles
        for i in range(60):
            knowledgeBaseModel.objects.create(
                category=f"Category {i}",
                section="Airtime & Data",
                content_type="Website",
                caption=f"Article {i}",
            )

        response = self.client.get(self.list_url, {"page_size": 100})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.data
        results = data["data"].get("results", [])
        self.assertLessEqual(len(results), 50)  # Max page size

    def test_special_characters_in_search_filter(self):
        """Test filtering with special characters."""
        article = knowledgeBaseModel.objects.create(
            category="Test & Category",
            section="Banking",
            content_type="Social Post",
            caption="Test @#$% article",
        )

        # Filter by category with special characters
        response = self.client.get(self.list_url, {"category": "Test & Category"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.data
        results = data["data"].get("results", [])
        self.assertGreater(len(results), 0)
        self.assertEqual(results[0]["category"], "Test & Category")

    def test_case_insensitive_filtering(self):
        """Test that filtering is case-insensitive."""
        article = knowledgeBaseModel.objects.create(
            category="Mobile Services",
            section="Airtime & Data",
            content_type="Website",
            caption="Test article",
        )

        # Try different case variations
        response = self.client.get(self.list_url, {"section": "airtime & data"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.data
        results = data["data"].get("results", [])
        self.assertGreater(len(results), 0)

        response = self.client.get(self.list_url, {"content_type": "website"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.data
        results = data["data"].get("results", [])
        self.assertGreater(len(results), 0)

    def test_article_with_minimal_fields(self):
        """Test retrieving an article with minimal fields."""
        minimal_article = knowledgeBaseModel.objects.create(
            category="Test",
            section="Banking",
            content_type="Email",
            caption="Minimal article",
        )

        url = reverse("roles:knowledge-base-detail", kwargs={"id": minimal_article.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.data
        article_data = data["data"]

        # Optional fields should be None or empty
        self.assertEqual([], article_data["authors"])
        self.assertEqual([], article_data["author_image_urls"])
        self.assertIsNone(article_data["content"])
        self.assertEqual([], article_data["ads_and_media_url"])
        self.assertIsNone(article_data["ad_description"])

    def test_filter_by_scheduled_status(self):
        """Test filtering by scheduled status."""
        # Create both scheduled and non-scheduled articles
        knowledgeBaseModel.objects.create(
            category="Scheduled",
            section="Airtime & Data",
            content_type="Website",
            caption="Scheduled article",
            is_post_scheduled=True,
        )
        knowledgeBaseModel.objects.create(
            category="Not Scheduled",
            section="Electricity",
            content_type="Social Post",
            caption="Not scheduled article",
            is_post_scheduled=False,
        )

        # Note: The current implementation doesn't filter by is_post_scheduled
        # This test ensures the endpoint handles articles with both statuses
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.data
        results = data["data"].get("results", [])

        # Both types should be returned
        scheduled = [a for a in results if a.get("caption") == "Scheduled article"]
        not_scheduled = [
            a for a in results if a.get("caption") == "Not scheduled article"
        ]

        self.assertTrue(len(scheduled) > 0 or len(not_scheduled) > 0)


class KnowledgeBasePermissionsTest(TestCase):
    """Test cases for knowledge base permissions."""

    def setUp(self):
        self.client = APIClient()
        self.list_url = reverse("roles:knowledge-base-list")

        self.article = knowledgeBaseModel.objects.create(
            category="Test",
            section="Banking",
            content_type="Website",
            caption="Test article",
        )
        self.detail_url = reverse(
            "knowledge-base-detail", kwargs={"id": self.article.id}
        )

    def test_public_access_to_list(self):
        """Test that anyone can access the knowledge base list."""
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_public_access_to_detail(self):
        """Test that anyone can access the knowledge base detail."""
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_allow_any_permission_on_list_view(self):
        """Test that the list view has AllowAny permission."""
        # This is a structural test - ensure the view is accessible without auth
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_allow_any_permission_on_detail_view(self):
        """Test that the detail view has AllowAny permission."""
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class KnowledgeBaseSerializationTest(TestCase):
    """Test cases for knowledge base serializers."""

    def setUp(self):
        self.article = knowledgeBaseModel.objects.create(
            category="Mobile Services",
            section="Airtime & Data",
            content_type="Website",
            authors=["John Doe", "Jane Smith"],
            caption="How to buy airtime",
            author_image_urls=["https://example.com/author1.jpg"],
            content="Detailed content about buying airtime...",
            ads_and_media_url=["https://example.com/ad1.jpg"],
            ad_description="Promotional ad description",
            is_post_scheduled=False,
        )

    def test_knowledge_base_list_serializer(self):
        """Test the KnowledgeBaseListSerializer."""
        from .serializers import KnowledgeBaseListSerializer

        serializer = KnowledgeBaseListSerializer(self.article)
        data = serializer.data

        # Fields that should be present
        self.assertEqual(data["id"], self.article.id)
        self.assertEqual(data["category"], self.article.category)
        self.assertEqual(data["section"], self.article.section)
        self.assertEqual(data["content_type"], self.article.content_type)
        self.assertEqual(data["authors"], self.article.authors)
        self.assertEqual(data["caption"], self.article.caption)
        self.assertIsNotNone(data["created_at"])

        # Fields that should NOT be present
        self.assertNotIn("content", data)
        self.assertNotIn("author_image_urls", data)
        self.assertNotIn("ads_and_media_url", data)
        self.assertNotIn("ad_description", data)

    def test_knowledge_base_detail_serializer(self):
        """Test the KnowledgeBaseDetailSerializer."""
        from .serializers import KnowledgeBaseDetailSerializer

        serializer = KnowledgeBaseDetailSerializer(self.article)
        data = serializer.data

        # All fields should be present
        expected_fields = [
            "id",
            "category",
            "section",
            "content_type",
            "authors",
            "caption",
            "author_image_urls",
            "content",
            "ads_and_media_url",
            "ad_description",
            "created_at",
        ]

        for field in expected_fields:
            self.assertIn(field, data)

        # Verify values
        self.assertEqual(data["content"], self.article.content)
        self.assertEqual(data["author_image_urls"], self.article.author_image_urls)
        self.assertEqual(data["ads_and_media_url"], self.article.ads_and_media_url)
        self.assertEqual(data["ad_description"], self.article.ad_description)


def _backdate(instance, **fields):
    """Bypass auto_now_add by updating via the QuerySet, not instance.save()."""
    type(instance).objects.filter(pk=instance.pk).update(**fields)
    instance.refresh_from_db()
    return instance


class AlertAndRiskAnalyticsTests(TestCase):
    """Unit tests for the roles.analytics functions backing the Alert and
    Risk drill-downs (Pending Settlement, Reconciliation Differences,
    Duplicate Transactions, Fraud Alert) and the account_type/wallet
    enrichment added to get_all_transactions."""

    def setUp(self):
        self.buyer = User.objects.create(
            phone_number="2348010000001",
            email="buyer@example.com",
            first_name="Bola",
            last_name="Buyer",
            country="NG",
            state="Lagos",
            city="Ikeja",
            active_role="Member",
        )
        self.partner_user = User.objects.create(
            phone_number="2348010000002",
            email="partner@example.com",
            first_name="Pat",
            last_name="Partner",
            country="NG",
            state="Lagos",
            city="Ikeja",
            active_role="Partner",
        )
        WalletModel.objects.create(
            user=self.buyer,
            walletType="INDIVIDUAL",
            acct_name="Bola Buyer",
            account_number="1000000001",
        )
        self.partner_service = PartnerServices.objects.create(
            user=self.partner_user,
            business="Restaurant",
            service="Jollof Rice",
            price=5000,
        )

    def _make_tx(
        self, user=None, tx_type="Food", amount=5000, status="SUCCESS", **overrides
    ):
        return TxModel.objects.create(
            user=user or self.buyer,
            tx_type=tx_type,
            amount=amount,
            status=status,
            **overrides,
        )

    # ── _tx_category ──────────────────────────────────────────────────

    def test_tx_category_self_service_vs_partner_vs_brand_vs_wallet_vs_other(self):
        self_service_tx = self._make_tx(tx_type="Food")
        partner_tx = self._make_tx(tx_type="Gym")
        brand_tx = self._make_tx(tx_type="Brand Promotion")
        wallet_tx = self._make_tx(tx_type="Transfer to Bank Account")
        other_tx = self._make_tx(tx_type="Funding of wallet")

        partner_linked = {partner_tx.id}

        self.assertEqual(_tx_category(self_service_tx, partner_linked), "Self Services")
        self.assertEqual(_tx_category(partner_tx, partner_linked), "Partners")
        self.assertEqual(_tx_category(brand_tx, partner_linked), "Brand Ads")
        self.assertEqual(_tx_category(wallet_tx, partner_linked), "Wallet")
        self.assertEqual(_tx_category(other_tx, partner_linked), "Other")

    # ── Pending Settlement ───────────────────────────────────────────

    def test_pending_settlement_list_returns_only_pending_with_wallet_info(self):
        pending_tx = self._make_tx(status="PENDING", tx_type="Intra-Bank Transfer")
        self._make_tx(status="SUCCESS")

        rows = get_pending_settlement_list()

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(
            row["transaction_id"], pending_tx.tx_reference or str(pending_tx.id)
        )
        self.assertEqual(row["status"], "PENDING")
        self.assertEqual(row["account_type"], "Member")
        self.assertEqual(row["wallet_name"], "Bola Buyer")
        self.assertEqual(row["wallet_number"], "1000000001")

    def test_transaction_detail_row_found_and_not_found(self):
        self._make_tx(tx_reference="TX-ABC-123")

        found = get_transaction_detail_row("TX-ABC-123")
        missing = get_transaction_detail_row("does-not-exist")

        self.assertIsNotNone(found)
        self.assertEqual(found["transaction_id"], "TX-ABC-123")
        self.assertIsNone(missing)

    # ── Reconciliation Differences ──────────────────────────────────

    def test_reconciliation_excludes_transaction_within_grace_period(self):
        tx = self._make_tx(tx_type="Food", status="SUCCESS")
        # Still inside the grace period - not old enough to flag yet.
        _backdate(tx, date=timezone.now() - timedelta(hours=1))
        PartnerPurchase.objects.create(
            user=self.buyer,
            service=self.partner_service,
            tx=tx,
            commission_amount=500,
            payout_amount=4500,
            settled=False,
        )

        start = timezone.now() - timedelta(days=1)
        end = timezone.now() + timedelta(days=1)

        self.assertEqual(get_reconciliation_differences_count(start, end), 0)

    def test_reconciliation_excludes_settled_purchase(self):
        tx = self._make_tx(tx_type="Food", status="SUCCESS")
        _backdate(
            tx,
            date=timezone.now()
            - timedelta(hours=RECONCILIATION_GRACE_PERIOD_HOURS + 1),
        )
        PartnerPurchase.objects.create(
            user=self.buyer,
            service=self.partner_service,
            tx=tx,
            commission_amount=500,
            payout_amount=4500,
            settled=True,
        )

        start = timezone.now() - timedelta(days=1)
        end = timezone.now() + timedelta(days=1)

        self.assertEqual(get_reconciliation_differences_count(start, end), 0)

    def test_reconciliation_flags_unsettled_purchase_past_grace_period(self):
        tx = self._make_tx(tx_type="Food", status="SUCCESS")
        _backdate(
            tx,
            date=timezone.now()
            - timedelta(hours=RECONCILIATION_GRACE_PERIOD_HOURS + 1),
        )
        purchase = PartnerPurchase.objects.create(
            user=self.buyer,
            service=self.partner_service,
            tx=tx,
            commission_amount=500,
            payout_amount=4500,
            settled=False,
        )

        start = timezone.now() - timedelta(days=1)
        end = timezone.now() + timedelta(days=1)

        self.assertEqual(get_reconciliation_differences_count(start, end), 1)
        qs_ids = list(
            get_reconciliation_differences_queryset(start, end).values_list(
                "id", flat=True
            )
        )
        self.assertEqual(qs_ids, [purchase.id])

        rows = get_reconciliation_differences_list(start, end)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["category"], "Partners")

    def test_reconciliation_difference_detail_two_sided_shape(self):
        tx = self._make_tx(tx_type="Food", status="SUCCESS", tx_reference="TX-RECON-1")
        _backdate(
            tx,
            date=timezone.now()
            - timedelta(hours=RECONCILIATION_GRACE_PERIOD_HOURS + 1),
        )
        PartnerPurchase.objects.create(
            user=self.buyer,
            service=self.partner_service,
            tx=tx,
            commission_amount=500,
            payout_amount=4500,
            settled=False,
        )

        detail = get_reconciliation_difference_detail("TX-RECON-1")

        self.assertIsNotNone(detail)
        self.assertEqual(detail["user_side"]["status"], "SUCCESS")
        self.assertEqual(detail["user_side"]["category"], "User")
        self.assertEqual(detail["partner_side"]["status"], "PENDING")
        self.assertEqual(detail["partner_side"]["category"], "Partner")
        self.assertEqual(detail["partner_side"]["amount"], 4500.0)

    def test_reconciliation_difference_detail_not_found(self):
        self.assertIsNone(get_reconciliation_difference_detail("nope"))

    # ── Duplicate Transactions ───────────────────────────────────────

    def test_duplicate_pair_detected_within_window(self):
        first = self._make_tx(tx_type="Food", amount=1000)
        second = self._make_tx(tx_type="Food", amount=1000)
        now = timezone.now()
        _backdate(first, date=now)
        _backdate(
            second,
            date=now + timedelta(minutes=DUPLICATE_TRANSACTION_WINDOW_MINUTES - 1),
        )

        start = now - timedelta(days=1)
        end = now + timedelta(days=1)
        pairs = get_duplicate_transaction_pairs(start, end)

        self.assertEqual(len(pairs), 1)
        duplicate_tx, original_tx = pairs[0]
        self.assertEqual(duplicate_tx.id, second.id)
        self.assertEqual(original_tx.id, first.id)

    def test_duplicate_pair_not_detected_outside_window(self):
        first = self._make_tx(tx_type="Gym", amount=2000)
        second = self._make_tx(tx_type="Gym", amount=2000)
        now = timezone.now()
        _backdate(first, date=now)
        _backdate(
            second,
            date=now + timedelta(minutes=DUPLICATE_TRANSACTION_WINDOW_MINUTES + 5),
        )

        start = now - timedelta(days=1)
        end = now + timedelta(days=1)

        self.assertEqual(get_duplicate_transaction_pairs(start, end), [])

    def test_duplicate_pair_not_detected_for_different_amount(self):
        first = self._make_tx(tx_type="Cinema", amount=1000)
        second = self._make_tx(tx_type="Cinema", amount=1500)
        now = timezone.now()
        _backdate(first, date=now)
        _backdate(second, date=now + timedelta(minutes=1))

        start = now - timedelta(days=1)
        end = now + timedelta(days=1)

        self.assertEqual(get_duplicate_transaction_pairs(start, end), [])

    def test_duplicate_transactions_list_overrides_status_label(self):
        first = self._make_tx(tx_type="Food", amount=3000)
        second = self._make_tx(tx_type="Food", amount=3000)
        now = timezone.now()
        _backdate(first, date=now)
        _backdate(second, date=now + timedelta(minutes=2))

        rows = get_duplicate_transactions_list(
            now - timedelta(days=1), now + timedelta(days=1)
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "Duplicate")
        self.assertEqual(
            rows[0]["transaction_id"], second.tx_reference or str(second.id)
        )

    def test_duplicate_transaction_detail_returns_both_sides_with_real_status(self):
        first = self._make_tx(
            tx_type="Food", amount=3000, status="SUCCESS", tx_reference="TX-ORIG"
        )
        second = self._make_tx(
            tx_type="Food", amount=3000, status="PENDING", tx_reference="TX-DUP"
        )
        # get_duplicate_transaction_detail computes its own [now-365d, now)
        # window internally - backdate into the past, not relative to a
        # locally-captured `now`, so both rows are safely inside it by the
        # time the function calls timezone.now() itself.
        base = timezone.now() - timedelta(minutes=10)
        _backdate(first, date=base)
        _backdate(second, date=base + timedelta(minutes=2))

        detail = get_duplicate_transaction_detail("TX-DUP")

        self.assertIsNotNone(detail)
        self.assertEqual(detail["duplicate"]["transaction_id"], "TX-DUP")
        self.assertEqual(detail["duplicate"]["status"], "PENDING")
        self.assertEqual(detail["original"]["transaction_id"], "TX-ORIG")
        self.assertEqual(detail["original"]["status"], "SUCCESS")

    def test_duplicate_transaction_detail_not_found(self):
        self.assertIsNone(get_duplicate_transaction_detail("nope"))

    # ── Fraud Alert / snapshot ───────────────────────────────────────

    def test_fraud_alerts_list_always_empty(self):
        self.assertEqual(get_fraud_alerts_list(), [])

    def test_alert_and_risk_snapshot_aggregates_all_four_counts(self):
        self._make_tx(status="PENDING")

        recon_tx = self._make_tx(tx_type="Food", status="SUCCESS")
        _backdate(
            recon_tx,
            date=timezone.now()
            - timedelta(hours=RECONCILIATION_GRACE_PERIOD_HOURS + 1),
        )
        PartnerPurchase.objects.create(
            user=self.buyer,
            service=self.partner_service,
            tx=recon_tx,
            commission_amount=100,
            payout_amount=900,
            settled=False,
        )

        dup_first = self._make_tx(tx_type="Cinema", amount=7000)
        dup_second = self._make_tx(tx_type="Cinema", amount=7000)
        now = timezone.now()
        _backdate(dup_first, date=now)
        _backdate(dup_second, date=now + timedelta(minutes=1))

        start = now - timedelta(days=2)
        end = now + timedelta(days=1)
        snapshot = get_alert_and_risk_snapshot(start, end)

        self.assertGreaterEqual(snapshot["pending_settlement"], 1)
        self.assertEqual(snapshot["duplicate_transactions"], 1)
        self.assertEqual(snapshot["reconciliation_differences"], 1)
        self.assertEqual(snapshot["fraud_alerts"], 0)

    # ── All Transactions enrichment ──────────────────────────────────

    def test_all_transactions_rows_include_account_type_and_wallet_fields(self):
        self._make_tx(tx_type="Intra-Bank Transfer", status="SUCCESS")

        rows = get_all_transactions(
            timezone.now() - timedelta(days=1), timezone.now() + timedelta(days=1)
        )

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertIn("account_type", row)
        self.assertEqual(row["account_type"], "Member")
        self.assertEqual(row["wallet_name"], "Bola Buyer")
        self.assertEqual(row["wallet_number"], "1000000001")


class AlertAndRiskViewTests(APITestCase):
    """HTTP-level tests for the Alert and Risk drill-down endpoints and the
    action endpoints (Message Third Party, Cancel Pending)."""

    def setUp(self):
        cache.clear()
        self.superadmin = _create_user(
            email="risk-super@example.com",
            phone_number="2348020000001",
            active_role="SuperAdmin",
        )
        self.member = _create_user(
            email="risk-member@example.com",
            phone_number="2348020000002",
            active_role="Member",
        )
        self.buyer = _create_user(
            email="risk-buyer@example.com",
            phone_number="2348020000003",
            active_role="Member",
        )
        self.partner_user = _create_user(
            email="risk-partner@example.com",
            phone_number="2348020000004",
            active_role="Partner",
        )
        WalletModel.objects.create(
            user=self.buyer,
            walletType="INDIVIDUAL",
            acct_name="Risk Buyer",
            account_number="2000000001",
        )
        self.partner_service = PartnerServices.objects.create(
            user=self.partner_user,
            business="Gym",
            service="Monthly Membership",
            price=10000,
        )

    def _make_tx(self, **overrides):
        defaults = dict(user=self.buyer, tx_type="Gym", amount=10000, status="SUCCESS")
        defaults.update(overrides)
        return TxModel.objects.create(**defaults)

    def test_pending_settlement_list_requires_authentication(self):
        response = self.client.get(reverse("roles:pending_settlement_list"))

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_pending_settlement_list_rejects_non_superadmin(self):
        self.client.force_authenticate(user=self.member)

        response = self.client.get(reverse("roles:pending_settlement_list"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_pending_settlement_list_returns_rows_for_superadmin(self):
        self._make_tx(status="PENDING", tx_reference="TX-PEND-1")
        self.client.force_authenticate(user=self.superadmin)

        response = self.client.get(reverse("roles:pending_settlement_list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.data)
        self.assertEqual(body["status"], "success")
        self.assertEqual(body["data"]["count"], 1)
        self.assertEqual(body["data"]["results"][0]["transaction_id"], "TX-PEND-1")

    def test_transaction_detail_view_found_and_not_found(self):
        self._make_tx(status="PENDING", tx_reference="TX-DETAIL-1")
        self.client.force_authenticate(user=self.superadmin)

        found = self.client.get(
            reverse(
                "roles:transaction_detail", kwargs={"transaction_id": "TX-DETAIL-1"}
            )
        )
        missing = self.client.get(
            reverse("roles:transaction_detail", kwargs={"transaction_id": "nope"})
        )

        self.assertEqual(found.status_code, status.HTTP_200_OK)
        self.assertEqual(decrypt(found.data)["data"]["transaction_id"], "TX-DETAIL-1")
        self.assertEqual(missing.status_code, status.HTTP_404_NOT_FOUND)

    def test_reconciliation_differences_list_view(self):
        tx = self._make_tx(status="SUCCESS", tx_reference="TX-RECON-VIEW")
        now = timezone.now()
        TxModel.objects.filter(pk=tx.pk).update(
            date=now - timedelta(hours=RECONCILIATION_GRACE_PERIOD_HOURS + 1)
        )
        PartnerPurchase.objects.create(
            user=self.buyer,
            service=self.partner_service,
            tx=tx,
            commission_amount=500,
            payout_amount=9500,
            settled=False,
        )
        self.client.force_authenticate(user=self.superadmin)

        response = self.client.get(
            reverse("roles:reconciliation_differences_list"),
            {"granularity": "yearly"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.data)
        self.assertEqual(body["data"]["count"], 1)
        self.assertEqual(body["data"]["results"][0]["transaction_id"], "TX-RECON-VIEW")

    def test_reconciliation_difference_detail_view(self):
        tx = self._make_tx(status="SUCCESS", tx_reference="TX-RECON-DETAIL")
        TxModel.objects.filter(pk=tx.pk).update(
            date=timezone.now() - timedelta(hours=RECONCILIATION_GRACE_PERIOD_HOURS + 1)
        )
        PartnerPurchase.objects.create(
            user=self.buyer,
            service=self.partner_service,
            tx=tx,
            commission_amount=500,
            payout_amount=9500,
            settled=False,
        )
        self.client.force_authenticate(user=self.superadmin)

        response = self.client.get(
            reverse(
                "roles:reconciliation_difference_detail",
                kwargs={"transaction_id": "TX-RECON-DETAIL"},
            )
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.data)
        self.assertEqual(body["data"]["user_side"]["status"], "SUCCESS")
        self.assertEqual(body["data"]["partner_side"]["status"], "PENDING")

    def test_duplicate_transactions_list_and_detail_view(self):
        first = self._make_tx(amount=4000, tx_reference="TX-DUP-ORIG")
        second = self._make_tx(amount=4000, tx_reference="TX-DUP-COPY")
        # Backdate into the past (not relative to a locally-captured `now`)
        # so both rows are safely inside whatever window either endpoint
        # computes internally, however many milliseconds later that is.
        base = timezone.now() - timedelta(minutes=10)
        TxModel.objects.filter(pk=first.pk).update(date=base)
        TxModel.objects.filter(pk=second.pk).update(date=base + timedelta(minutes=1))
        self.client.force_authenticate(user=self.superadmin)

        list_response = self.client.get(
            reverse("roles:duplicate_transactions_list"),
            {"granularity": "yearly"},
        )
        detail_response = self.client.get(
            reverse(
                "roles:duplicate_transaction_detail",
                kwargs={"transaction_id": "TX-DUP-COPY"},
            )
        )

        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        list_body = decrypt(list_response.data)
        self.assertEqual(list_body["data"]["count"], 1)
        self.assertEqual(list_body["data"]["results"][0]["status"], "Duplicate")

        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        detail_body = decrypt(detail_response.data)
        self.assertEqual(
            detail_body["data"]["duplicate"]["transaction_id"], "TX-DUP-COPY"
        )
        self.assertEqual(
            detail_body["data"]["original"]["transaction_id"], "TX-DUP-ORIG"
        )

    def test_fraud_alerts_list_view_is_always_empty(self):
        self.client.force_authenticate(user=self.superadmin)

        response = self.client.get(reverse("roles:fraud_alerts_list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.data)
        self.assertEqual(body["data"]["count"], 0)
        self.assertEqual(body["data"]["results"], [])

    def test_message_third_party_creates_ticket_with_number(self):
        self._make_tx(status="PENDING", tx_reference="TX-MSG-1")
        self.client.force_authenticate(user=self.superadmin)

        # Plain JSON, not encrypted - MessageThirdPartyView reads
        # request.data directly (same convention as
        # roles.partners.SetPartnerServiceCommission): only responses are
        # encrypted on these admin write endpoints, not request bodies.
        response = self.client.post(
            reverse("roles:message_third_party"),
            data=_json.dumps(
                {
                    "transaction_id": "TX-MSG-1",
                    "title": "Pending Settlement",
                    "issues_description": (
                        "This transaction has not dropped in the customer's wallet."
                    ),
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        body = decrypt(response.data)
        self.assertEqual(body["status"], "success")
        self.assertTrue(body["data"]["ticket_number"])
        ticket = Ticket.objects.get(number=body["data"]["ticket_number"])
        self.assertEqual(ticket.title, "Pending Settlement")
        self.assertEqual(ticket.user_id, self.buyer.id)
        self.assertIn("TX-MSG-1", ticket.description)

    def test_cancel_pending_transaction_marks_cancelled(self):
        tx = self._make_tx(status="PENDING", tx_reference="TX-CANCEL-1")
        self.client.force_authenticate(user=self.superadmin)

        response = self.client.post(
            reverse(
                "roles:cancel_pending_transaction",
                kwargs={"transaction_id": "TX-CANCEL-1"},
            )
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        tx.refresh_from_db()
        self.assertEqual(tx.status, "CANCELLED")

    def test_cancel_pending_transaction_rejects_non_pending(self):
        self._make_tx(status="SUCCESS", tx_reference="TX-CANCEL-2")
        self.client.force_authenticate(user=self.superadmin)

        response = self.client.post(
            reverse(
                "roles:cancel_pending_transaction",
                kwargs={"transaction_id": "TX-CANCEL-2"},
            )
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cancel_pending_transaction_404_for_unknown(self):
        self.client.force_authenticate(user=self.superadmin)

        response = self.client.post(
            reverse(
                "roles:cancel_pending_transaction",
                kwargs={"transaction_id": "does-not-exist"},
            )
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_alert_and_risk_view_returns_real_reconciliation_and_fraud_numbers(self):
        tx = self._make_tx(status="SUCCESS", tx_reference="TX-SNAPSHOT")
        TxModel.objects.filter(pk=tx.pk).update(
            date=timezone.now() - timedelta(hours=RECONCILIATION_GRACE_PERIOD_HOURS + 1)
        )
        PartnerPurchase.objects.create(
            user=self.buyer,
            service=self.partner_service,
            tx=tx,
            commission_amount=500,
            payout_amount=9500,
            settled=False,
        )
        self.client.force_authenticate(user=self.superadmin)

        response = self.client.get(
            reverse("roles:alert_and_risk"), {"granularity": "yearly"}
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.data)
        self.assertIsNotNone(body["data"]["reconciliation_differences"]["value"])
        self.assertEqual(body["data"]["fraud_alerts"]["value"], 0)
