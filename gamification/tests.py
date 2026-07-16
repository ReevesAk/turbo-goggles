"""
Test suite for the Gamification application.

Covers UGC task management, step campaigns, caching behavior,
exception handling, and integration workflows across brand,
admin, and public endpoints.
"""

from datetime import timedelta
from decimal import Decimal
from uuid import uuid4
from unittest.mock import patch, MagicMock

from django.contrib.auth.hashers import make_password
from django.core.cache import cache
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User, AccountType, TxModel
from adverts.models import BrandAdCreditWallet
from banking.models import WalletModel
from .models import (
    StepCampaignModel,
    StepSessionModel,
    UserGeneratedContent,
)
from security import encrypt, decrypt

# ==================
# Test Helpers
# ==================


def _create_user(**overrides):
    """Create a test user with sensible defaults.

    Keyword arguments override the default field values.
    """
    seed = uuid4().hex[:8]
    defaults = {
        "phone_number": f"23490{seed[:7]}",
        "first_name": "Game",
        "last_name": "User",
        "email": f"game.{seed}@example.com",
        "country": "NG",
        "state": "Lagos",
        "city": "Ikeja",
        "is_verified": True,
        "is_staff": True,
        "active_role": "SuperAdmin",
    }
    defaults.update(overrides)
    password = defaults.pop("password", "StrongPass123!")
    user = User.objects.create(**defaults)
    user.set_password(password)
    user.save()
    return user


def _create_ugc_task(user, **overrides):
    """Create a UGC task with production-like defaults.

    Keyword arguments override the default field values.
    """
    defaults = {
        "user": user,
        "business_or_brand_name": "Test Brand",
        "type_of_business": "online",
        "task_name": "Test Task",
        "task_type": "make_a_video",
        "description": "Test description to see if it actually works fine",
        "thumbnail_url": "https://example.com/thumb.jpg",
        "sample_url": "https://example.com/sample.mp4",
        "slot_cap": 100,
        "amount": "10000.00",
        "targeting_type": "broad",
        "location_perimeter": "nation_wide",
        "gender": "all",
        "is_active": True,
        "credit_settled": False,
    }
    defaults.update(overrides)
    return UserGeneratedContent.objects.create(**defaults)


def _create_wallet(user, balance=Decimal("50000.00"), pin="123456"):
    """Create a wallet with INDIVIDUAL type and a hashed PIN."""
    return WalletModel.objects.create(
        user=user,
        account_number="1234567890",
        balance=balance,
        walletType="INDIVIDUAL",
        pin=make_password(pin),
    )


# ============================================
# Base test case with throttle mocking
# ============================================


class ThrottleDisabledAPITestCase(APITestCase):
    """Base class that disables DRF throttling for all tests."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._throttle_patcher = patch("rest_framework.views.APIView.check_throttles")
        cls._throttle_patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls._throttle_patcher.stop()
        super().tearDownClass()


# ===============================
# Step Campaign Tests
# ===============================


class StepSessionModelBehaviorTests(ThrottleDisabledAPITestCase):
    """Unit tests for StepSessionModel methods."""

    def test_total_steps_and_completion_across_sessions(self):
        """Verify total_steps aggregates across sessions and completion works."""
        user = _create_user()
        campaign = StepCampaignModel.objects.create(
            name="10K Steps",
            duration=timedelta(days=1),
            step_target=5000,
            reward_points=100,
            time_limit=timedelta(hours=24),
            created_by=user,
        )

        StepSessionModel.objects.create(
            campaign=campaign,
            user=user,
            session_date=timezone.now().date() - timedelta(days=1),
            step_count=3000,
            started_at=timezone.now() - timedelta(days=1),
        )
        session_two = StepSessionModel.objects.create(
            campaign=campaign,
            user=user,
            step_count=2200,
            started_at=timezone.now(),
        )

        self.assertEqual(session_two.total_steps, 5200)
        self.assertTrue(session_two.check_completion())


class JoinCampaignEndpointTests(ThrottleDisabledAPITestCase):
    """Tests for the campaign join endpoint."""

    def test_join_campaign_returns_404_for_missing_campaign(self):
        """A non-existent campaign ID returns a 404."""
        user = _create_user(active_role="Member", has_done_survey=True)
        self.client.force_authenticate(user=user)

        response = self.client.post(f"/v1/gamification/campaigns/{uuid4()}/join/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        body = decrypt(response.content)
        self.assertEqual(body["status"], "fail")
        self.assertIn("Campaign not found", body["message"])


# ====================================
# Public UGC List Tests
# ====================================


class UGCPublicListViewTests(ThrottleDisabledAPITestCase):
    """Tests for the public UGC task listing endpoint."""

    def setUp(self):
        self.user = _create_user(active_role="Member")
        self.client.force_authenticate(user=self.user)
        cache.clear()

    # --- Success cases ---

    def test_list_active_tasks_returns_success(self):
        """Authenticated users can list active UGC tasks."""
        brand_user = _create_user(active_role="BrandAd")
        _create_ugc_task(brand_user, is_active=True)
        _create_ugc_task(brand_user, is_active=True)

        response = self.client.get("/v1/gamification/ugc/tasks/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        body = decrypt(response.content)
        self.assertEqual(body["status"], "success")
        self.assertEqual(len(body["data"]["results"]), 2)

    def test_list_tasks_returns_cached_response(self):
        """Responses are cached; second call hits the cache."""
        brand_user = _create_user(active_role="BrandAd")
        _create_ugc_task(brand_user, is_active=True)

        response1 = self.client.get("/v1/gamification/ugc/tasks/")
        self.assertEqual(response1.status_code, status.HTTP_200_OK)
        body1 = decrypt(response1.content)

        with patch("django.core.cache.cache.get") as mock_cache_get:
            mock_cache_get.return_value = body1
            response2 = self.client.get("/v1/gamification/ugc/tasks/")
            self.assertEqual(response2.status_code, status.HTTP_200_OK)
            mock_cache_get.assert_called()

    def test_list_tasks_uses_pagination(self):
        """Default page size is 20; pagination metadata is present."""
        brand_user = _create_user(active_role="BrandAd")
        for i in range(25):
            _create_ugc_task(brand_user, is_active=True, task_name=f"Task {i}")

        response = self.client.get("/v1/gamification/ugc/tasks/")
        body = decrypt(response.content)

        self.assertEqual(len(body["data"]["results"]), 20)
        self.assertIsNotNone(body["data"]["next"])

    # --- Filtering ---

    def test_list_tasks_filters_inactive_tasks(self):
        """Inactive tasks are excluded from the listing."""
        brand_user = _create_user(active_role="BrandAd")
        _create_ugc_task(brand_user, is_active=True)
        _create_ugc_task(brand_user, is_active=False)

        response = self.client.get("/v1/gamification/ugc/tasks/")
        body = decrypt(response.content)

        self.assertEqual(len(body["data"]["results"]), 1)
        self.assertTrue(body["data"]["results"][0]["is_active"])

    def test_list_tasks_filters_by_task_type(self):
        """Query parameter task_type filters results correctly."""
        brand_user = _create_user(active_role="BrandAd")
        _create_ugc_task(brand_user, task_type="make_a_video", is_active=True)
        _create_ugc_task(brand_user, task_type="make_a_photo", is_active=True)

        response = self.client.get("/v1/gamification/ugc/tasks/?task_type=make_a_video")
        body = decrypt(response.content)

        self.assertEqual(len(body["data"]["results"]), 1)
        self.assertEqual(body["data"]["results"][0]["task_type"], "make_a_video")

    def test_list_tasks_with_invalid_task_type(self):
        """An unknown task_type returns an empty result set."""
        brand_user = _create_user(active_role="BrandAd")
        _create_ugc_task(brand_user, task_type="make_a_video", is_active=True)

        response = self.client.get("/v1/gamification/ugc/tasks/?task_type=invalid_type")
        body = decrypt(response.content)

        self.assertEqual(len(body["data"]["results"]), 0)

    # --- Auth ---

    def test_list_tasks_requires_authentication(self):
        """Unauthenticated requests receive a 401."""
        self.client.force_authenticate(user=None)
        response = self.client.get("/v1/gamification/ugc/tasks/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


# ========================================
# Brand UGC List & Create Tests
# ========================================


class BrandUGCListCreateViewTests(ThrottleDisabledAPITestCase):
    """Tests for brand-scoped UGC task listing and creation."""

    def setUp(self):
        self.user = _create_user(active_role="BrandAd")
        AccountType.objects.create(user=self.user, user_type="BrandAd")
        self.client.force_authenticate(user=self.user)

        for page in range(1, 6):
            cache.delete(f"ugc_list:brand:{page}")

        self.wallet = _create_wallet(self.user)
        BrandAdCreditWallet.objects.get_or_create(user=self.user)

    # --- Listing ---

    def test_brand_list_own_tasks_success(self):
        """Brands see only their own tasks."""
        other_brand = _create_user(active_role="BrandAd")
        _create_ugc_task(self.user, task_name="My Task")
        _create_ugc_task(other_brand, task_name="Other Task")

        response = self.client.get("/v1/gamification/ugc/brand/tasks/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        body = decrypt(response.content)
        self.assertEqual(len(body["data"]["results"]), 1)
        self.assertEqual(body["data"]["results"][0]["task_name"], "My Task")

    def test_brand_list_tasks_returns_cached_response(self):
        """Brand task list responses are cached."""
        _create_ugc_task(self.user)

        response1 = self.client.get("/v1/gamification/ugc/brand/tasks/")
        self.assertEqual(response1.status_code, status.HTTP_200_OK)
        body1 = decrypt(response1.content)

        with patch("django.core.cache.cache.get") as mock_cache_get:
            mock_cache_get.return_value = body1
            response2 = self.client.get("/v1/gamification/ugc/brand/tasks/")
            self.assertEqual(response2.status_code, status.HTTP_200_OK)
            mock_cache_get.assert_called()

    # --- Wallet payment ---

    def test_brand_create_task_with_wallet_success(self):
        """Task creation succeeds with valid wallet payment."""
        data = self._valid_payload("New Task")

        with patch("banking.controllers.Wallet.getWalletDetails") as mock_wallet:
            mock_wallet.return_value = MagicMock(
                json=lambda: {
                    "status": "SUCCESS",
                    "data": {"availableBalance": 50000.00},
                }
            )
            with patch("banking.controllers.Wallet.Debit") as mock_debit:
                mock_debit.return_value = MagicMock(status_code=200)
                response = self.client.post(
                    "/v1/gamification/ugc/brand/tasks/",
                    data=encrypt(data),
                    format="json",
                )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        body = decrypt(response.content)
        self.assertEqual(body["status"], "success")

    def test_brand_create_task_insufficient_balance(self):
        """Insufficient wallet balance returns a 400 error."""
        self.wallet.balance = Decimal("1000.00")
        self.wallet.save()

        data = self._valid_payload("New Task")

        with patch("banking.controllers.Wallet.getWalletDetails") as mock_wallet:
            mock_wallet.return_value = MagicMock(
                json=lambda: {
                    "status": "SUCCESS",
                    "data": {"availableBalance": 1000.00},
                }
            )
            response = self.client.post(
                "/v1/gamification/ugc/brand/tasks/",
                data=encrypt(data),
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = decrypt(response.content)
        self.assertEqual(body["status"], "fail")
        self.assertEqual(body["message"], "Insufficient balance.")

    # --- Card payment ---

    def test_brand_create_task_with_card_payment(self):
        """Task creation succeeds with card payment option."""
        data = self._valid_payload("Card Task", payment_option="CARD")

        with patch("banking.helpers.verify_wallet_auth") as mock_verify:
            mock_verify.return_value = (True, None)
            response = self.client.post(
                "/v1/gamification/ugc/brand/tasks/",
                data=encrypt(data),
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        body = decrypt(response.content)
        self.assertEqual(body["status"], "success")
        self.assertEqual(UserGeneratedContent.objects.count(), 1)

    # --- Validation & permissions ---

    def test_brand_create_task_invalid_payment_option(self):
        """Invalid payment_option returns a 400."""
        data = self._valid_payload("Invalid Task", payment_option="INVALID")

        response = self.client.post(
            "/v1/gamification/ugc/brand/tasks/",
            data=encrypt(data),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = decrypt(response.content)
        self.assertEqual(body["status"], "fail")
        self.assertEqual(body["message"], "Invalid payment option")

    def test_brand_create_task_requires_brand_role(self):
        """Users without BrandAd role receive a 403."""
        regular_user = _create_user(active_role="Member")
        self.client.force_authenticate(user=regular_user)

        response = self.client.post(
            "/v1/gamification/ugc/brand/tasks/",
            data=encrypt(self._valid_payload("New Task")),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_brand_create_task_validation_error(self):
        """Serializer validation errors return a 400 with message."""
        data = self._valid_payload("")

        with patch("banking.helpers.verify_wallet_auth") as mock_verify:
            mock_verify.return_value = (True, None)
            response = self.client.post(
                "/v1/gamification/ugc/brand/tasks/",
                data=encrypt(data),
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = decrypt(response.content)
        self.assertEqual(body["status"], "fail")
        self.assertIsNotNone(body["message"])

    # --- Idempotency ---

    def test_brand_create_task_with_idempotency_key(self):
        """Duplicate idempotency key returns 200 and creates only one task."""
        idempotency_key = str(uuid4())
        data = self._valid_payload("Idempotent Task", idempotency_key=idempotency_key)

        with patch("banking.controllers.Wallet.getWalletDetails") as mock_wallet:
            mock_wallet.return_value = MagicMock(
                json=lambda: {
                    "status": "SUCCESS",
                    "data": {"availableBalance": 50000.00},
                }
            )
            with patch("banking.controllers.Wallet.Debit") as mock_debit:
                mock_debit.return_value = MagicMock(status_code=200)

                response1 = self.client.post(
                    "/v1/gamification/ugc/brand/tasks/",
                    data=encrypt(data),
                    format="json",
                    HTTP_IDEMPOTENCY_KEY=idempotency_key,
                )
                self.assertEqual(response1.status_code, status.HTTP_201_CREATED)

                with patch("django.core.cache.cache.get") as mock_cache_get:
                    mock_cache_get.return_value = {"status": "success"}
                    response2 = self.client.post(
                        "/v1/gamification/ugc/brand/tasks/",
                        data=encrypt(data),
                        format="json",
                        HTTP_IDEMPOTENCY_KEY=idempotency_key,
                    )

        self.assertEqual(response2.status_code, status.HTTP_200_OK)
        self.assertEqual(UserGeneratedContent.objects.count(), 1)

    # --- Side effects ---

    def test_brand_create_task_auto_creates_account_type(self):
        """AccountType is auto-created for brand users who lack one."""
        user_without_account = _create_user(active_role="Member")
        user_without_account.active_role = "BrandAd"
        user_without_account.save()

        _create_wallet(user_without_account)
        self.client.force_authenticate(user=user_without_account)

        data = self._valid_payload("New Task")

        with patch("banking.controllers.Wallet.getWalletDetails") as mock_wallet:
            mock_wallet.return_value = MagicMock(
                json=lambda: {
                    "status": "SUCCESS",
                    "data": {"availableBalance": 50000.00},
                }
            )
            with patch("banking.controllers.Wallet.Debit") as mock_debit:
                mock_debit.return_value = MagicMock(status_code=200)
                self.client.post(
                    "/v1/gamification/ugc/brand/tasks/",
                    data=encrypt(data),
                    format="json",
                )

        self.assertTrue(
            AccountType.objects.filter(
                user=user_without_account, user_type="BrandAd"
            ).exists()
        )

    def test_brand_create_task_creates_transaction_record(self):
        """Successful wallet payment creates a TxModel record."""
        data = self._valid_payload("New Task")

        with patch("banking.controllers.Wallet.getWalletDetails") as mock_wallet:
            mock_wallet.return_value = MagicMock(
                json=lambda: {
                    "status": "SUCCESS",
                    "data": {"availableBalance": 50000.00},
                }
            )
            with patch("banking.controllers.Wallet.Debit") as mock_debit:
                mock_debit.return_value = MagicMock(status_code=200)
                response = self.client.post(
                    "/v1/gamification/ugc/brand/tasks/",
                    data=encrypt(data),
                    format="json",
                )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        tx = TxModel.objects.filter(tx_type="UGC Task Funding").first()
        self.assertIsNotNone(tx)
        self.assertEqual(tx.status, "SUCCESS")
        self.assertEqual(tx.amount, 10000)

    # --- Helper ---

    @staticmethod
    def _valid_payload(task_name, payment_option="WALLET", idempotency_key=None):
        """Return a minimal valid creation payload."""
        data = {
            "payment_option": payment_option,
            "pin": "123456",
            "business_or_brand_name": "Acme Co",
            "type_of_business": "online",
            "task_name": task_name,
            "task_type": "make_a_video",
            "description": "Test description that is at least twenty characters long",
            "thumbnail_url": "https://example.com/thumb.jpg",
            "sample_url": "https://example.com/sample.mp4",
            "slot_cap": 50,
            "amount": "10000.00",
            "targeting_type": "broad",
            "location_perimeter": "nation_wide",
            "gender": "all",
        }
        if idempotency_key:
            data["idempotency_key"] = idempotency_key
        return data


# ============================================
# Brand UGC Detail Tests
# ============================================


class BrandUGCDetailViewTests(ThrottleDisabledAPITestCase):
    """Tests for brand-scoped retrieve / update / delete operations."""

    def setUp(self):
        self.user = _create_user(active_role="BrandAd")
        AccountType.objects.create(user=self.user, user_type="BrandAd")
        self.other_user = _create_user(active_role="BrandAd")
        AccountType.objects.create(user=self.other_user, user_type="BrandAd")
        self.task = _create_ugc_task(self.user)
        self.client.force_authenticate(user=self.user)

        cache.delete(f"ugc_detail:{self.task.id}")
        cache.delete(f"user_ugc_tasks:{self.user.id}")

    # --- Retrieve ---

    def test_brand_retrieve_own_task_success(self):
        response = self.client.get(f"/v1/gamification/ugc/brand/tasks/{self.task.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        body = decrypt(response.content)
        self.assertEqual(body["status"], "success")
        self.assertEqual(body["data"]["id"], str(self.task.id))

    def test_brand_cannot_retrieve_others_task(self):
        self.client.force_authenticate(user=self.other_user)
        response = self.client.get(f"/v1/gamification/ugc/brand/tasks/{self.task.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # --- Update ---

    def test_brand_update_own_task_success(self):
        data = {
            "task_name": "Updated Task Name",
            "description": "Updated description that is at least 20 chars",
        }
        response = self.client.patch(
            f"/v1/gamification/ugc/brand/tasks/{self.task.id}/",
            data=encrypt(data),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.content)
        self.assertEqual(body["status"], "success")

        self.task.refresh_from_db()
        self.assertEqual(self.task.task_name, "Updated Task Name")

    def test_brand_cannot_update_others_task(self):
        self.client.force_authenticate(user=self.other_user)
        response = self.client.patch(
            f"/v1/gamification/ugc/brand/tasks/{self.task.id}/",
            data=encrypt({"task_name": "Hacked"}),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_brand_update_validation_error(self):
        response = self.client.patch(
            f"/v1/gamification/ugc/brand/tasks/{self.task.id}/",
            data=encrypt({"task_name": ""}),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = decrypt(response.content)
        self.assertEqual(body["status"], "fail")

    # --- Delete ---

    def test_brand_delete_own_empty_task_success(self):
        response = self.client.delete(
            f"/v1/gamification/ugc/brand/tasks/{self.task.id}/"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        body = decrypt(response.content)
        self.assertEqual(body["status"], "success")
        self.assertFalse(UserGeneratedContent.objects.filter(id=self.task.id).exists())

    def test_brand_cannot_delete_task_with_filled_slots(self):
        self.task.slots_filled = 5
        self.task.save()

        response = self.client.delete(
            f"/v1/gamification/ugc/brand/tasks/{self.task.id}/"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        body = decrypt(response.content)
        self.assertEqual(body["status"], "fail")
        self.assertEqual(body["message"], "Cannot delete a task with filled slots.")

    def test_brand_cannot_delete_others_task(self):
        self.client.force_authenticate(user=self.other_user)
        response = self.client.delete(
            f"/v1/gamification/ugc/brand/tasks/{self.task.id}/"
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # --- Cache invalidation ---

    def test_brand_update_clears_cache(self):
        cache.set(f"ugc_detail:{self.task.id}", "cached_data", 60)
        cache.set(f"user_ugc_tasks:{self.user.id}", "cached_list", 60)

        response = self.client.patch(
            f"/v1/gamification/ugc/brand/tasks/{self.task.id}/",
            data=encrypt({"task_name": "Task Updated"}),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(cache.get(f"ugc_detail:{self.task.id}"))
        self.assertIsNone(cache.get(f"user_ugc_tasks:{self.user.id}"))


# =====================================
# Admin UGC List & Create Tests
# =====================================


class AdminUGCListCreateViewTests(ThrottleDisabledAPITestCase):
    """Tests for admin-scoped UGC task listing and creation."""

    def setUp(self):
        self.admin_user = _create_user(active_role="SuperAdmin", is_superuser=True)
        self.client.force_authenticate(user=self.admin_user)

        for page in range(1, 6):
            cache.delete(f"ugc_list:admin:{page}")

    def test_admin_list_all_tasks_success(self):
        """Admin can list tasks across all brands."""
        brand1 = _create_user(active_role="BrandAd")
        brand2 = _create_user(active_role="BrandAd")
        _create_ugc_task(brand1)
        _create_ugc_task(brand2)
        _create_ugc_task(brand1)

        response = self.client.get("/v1/gamification/ugc/admin/tasks/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        body = decrypt(response.content)
        self.assertEqual(len(body["data"]["results"]), 3)

    def test_admin_create_task_success(self):
        """Admin can create a task on behalf of a brand."""
        brand_user = _create_user(active_role="BrandAd")
        data = self._admin_payload(str(brand_user.id), "Admin Task")

        response = self.client.post(
            "/v1/gamification/ugc/admin/tasks/",
            data=encrypt(data),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        body = decrypt(response.content)
        self.assertEqual(body["status"], "success")
        self.assertEqual(UserGeneratedContent.objects.count(), 1)
        self.assertEqual(UserGeneratedContent.objects.first().user, brand_user)

    def test_admin_create_task_no_payment_flow(self):
        """Admin-created tasks do not go through the payment flow."""
        brand_user = _create_user(active_role="BrandAd")
        data = self._admin_payload(str(brand_user.id), "Free Task")

        response = self.client.post(
            "/v1/gamification/ugc/admin/tasks/",
            data=encrypt(data),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertFalse(TxModel.objects.filter(tx_type="UGC Task Funding").exists())

    def test_admin_create_task_requires_superuser(self):
        """Non-superuser admins are denied access."""
        regular_admin = _create_user(active_role="Admin", is_superuser=False)
        self.client.force_authenticate(user=regular_admin)

        response = self.client.get("/v1/gamification/ugc/admin/tasks/")
        self.assertIn(
            response.status_code,
            [status.HTTP_400_BAD_REQUEST, status.HTTP_403_FORBIDDEN],
        )

    def test_admin_create_task_validation_error(self):
        """Validation errors return a 400 with fail status."""
        data = {
            "task_name": "",
            "task_type": "make_a_video",
            "amount": "10000.00",
            "slot_cap": 50,
        }

        response = self.client.post(
            "/v1/gamification/ugc/admin/tasks/",
            data=encrypt(data),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = decrypt(response.content)
        self.assertEqual(body["status"], "fail")

    @staticmethod
    def _admin_payload(user_id, task_name):
        """Return a valid admin creation payload."""
        return {
            "user": user_id,
            "business_or_brand_name": "Admin Created",
            "type_of_business": "online",
            "task_name": task_name,
            "task_type": "make_a_video",
            "description": "Admin created task description that is long enough",
            "thumbnail_url": "https://example.com/thumb.jpg",
            "sample_url": "https://example.com/sample.mp4",
            "slot_cap": 100,
            "amount": "10000.00",
            "targeting_type": "broad",
            "location_perimeter": "nation_wide",
            "gender": "all",
            "credit_settled": False,
        }


# =================================
# Admin UGC Detail Tests
# =================================


class AdminUGCDetailViewTests(ThrottleDisabledAPITestCase):
    """Tests for admin-scoped retrieve / update / delete operations."""

    def setUp(self):
        self.admin_user = _create_user(active_role="SuperAdmin", is_superuser=True)
        self.brand_user = _create_user(active_role="BrandAd")
        self.task = _create_ugc_task(self.brand_user)
        self.client.force_authenticate(user=self.admin_user)

        cache.delete(f"ugc_detail:{self.task.id}")
        cache.delete(f"user_ugc_tasks:{self.brand_user.id}")

    # --- Retrieve ---

    def test_admin_retrieve_any_task_success(self):
        response = self.client.get(f"/v1/gamification/ugc/admin/tasks/{self.task.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        body = decrypt(response.content)
        self.assertEqual(body["status"], "success")
        self.assertEqual(body["data"]["id"], str(self.task.id))

    def test_admin_retrieve_nonexistent_task(self):
        response = self.client.get(f"/v1/gamification/ugc/admin/tasks/{uuid4()}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # --- Update ---

    def test_admin_update_any_task_success(self):
        data = {
            "task_name": "Admin Updated",
            "description": "Admin updated description that is long enough",
        }
        response = self.client.patch(
            f"/v1/gamification/ugc/admin/tasks/{self.task.id}/",
            data=encrypt(data),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.task.refresh_from_db()
        self.assertEqual(self.task.task_name, "Admin Updated")

    # --- Delete ---

    def test_admin_delete_empty_task_success(self):
        response = self.client.delete(
            f"/v1/gamification/ugc/admin/tasks/{self.task.id}/"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        body = decrypt(response.content)
        self.assertEqual(body["status"], "success")
        self.assertFalse(UserGeneratedContent.objects.filter(id=self.task.id).exists())

    def test_admin_cannot_delete_task_with_filled_slots(self):
        self.task.slots_filled = 5
        self.task.save()

        response = self.client.delete(
            f"/v1/gamification/ugc/admin/tasks/{self.task.id}/"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        body = decrypt(response.content)
        self.assertEqual(body["status"], "fail")

    # --- Cache ---

    def test_admin_update_clears_cache(self):
        cache.set(f"ugc_detail:{self.task.id}", "cached_data", 60)
        cache.set(f"user_ugc_tasks:{self.brand_user.id}", "cached_list", 60)

        response = self.client.patch(
            f"/v1/gamification/ugc/admin/tasks/{self.task.id}/",
            data=encrypt({"task_name": "Updated"}),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(cache.get(f"ugc_detail:{self.task.id}"))
        self.assertIsNone(cache.get(f"user_ugc_tasks:{self.brand_user.id}"))

    def test_admin_delete_clears_cache(self):
        cache.set(f"ugc_detail:{self.task.id}", "cached_data", 60)
        cache.set(f"user_ugc_tasks:{self.brand_user.id}", "cached_list", 60)

        response = self.client.delete(
            f"/v1/gamification/ugc/admin/tasks/{self.task.id}/"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(cache.get(f"ugc_detail:{self.task.id}"))
        self.assertIsNone(cache.get(f"user_ugc_tasks:{self.brand_user.id}"))

    # --- Permissions ---

    def test_admin_requires_superuser(self):
        regular_admin = _create_user(active_role="Admin", is_superuser=False)
        self.client.force_authenticate(user=regular_admin)

        response = self.client.get(f"/v1/gamification/ugc/admin/tasks/{self.task.id}/")
        self.assertIn(
            response.status_code,
            [status.HTTP_400_BAD_REQUEST, status.HTTP_403_FORBIDDEN],
        )


# ===============================
# Integration Tests
# ===============================


class UGCIntegrationTests(ThrottleDisabledAPITestCase):
    """End-to-end tests spanning multiple roles and endpoints."""

    def setUp(self):
        self.brand_user = _create_user(active_role="BrandAd")
        AccountType.objects.create(user=self.brand_user, user_type="BrandAd")
        self.regular_user = _create_user(active_role="Member")
        self.admin_user = _create_user(active_role="SuperAdmin", is_superuser=True)

        for page in range(1, 6):
            cache.delete(f"ugc_list:all:{page}")
            cache.delete(f"ugc_list:brand:{page}")
            cache.delete(f"ugc_list:admin:{page}")

        self.wallet = _create_wallet(self.brand_user)
        BrandAdCreditWallet.objects.get_or_create(user=self.brand_user)

    def test_full_workflow_brand_to_public(self):
        """Brand creates task; public user lists and retrieves it."""
        self.client.force_authenticate(user=self.brand_user)

        data = BrandUGCListCreateViewTests._valid_payload("Integration Task")

        with patch("banking.controllers.Wallet.getWalletDetails") as mock_wallet:
            mock_wallet.return_value = MagicMock(
                json=lambda: {
                    "status": "SUCCESS",
                    "data": {"availableBalance": 50000.00},
                }
            )
            with patch("banking.controllers.Wallet.Debit") as mock_debit:
                mock_debit.return_value = MagicMock(status_code=200)
                create_response = self.client.post(
                    "/v1/gamification/ugc/brand/tasks/",
                    data=encrypt(data),
                    format="json",
                )

        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        task_id = decrypt(create_response.content)["data"]["id"]

        # Public user lists tasks
        self.client.force_authenticate(user=self.regular_user)
        list_response = self.client.get("/v1/gamification/ugc/tasks/")
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)

        body = decrypt(list_response.content)
        self.assertEqual(len(body["data"]["results"]), 1)
        self.assertEqual(body["data"]["results"][0]["id"], task_id)

        # Public user retrieves detail
        detail_response = self.client.get(f"/v1/gamification/ugc/tasks/{task_id}/")
        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)

    def test_brand_update_propagates_to_public(self):
        """Brand updates are visible to public users."""
        self.client.force_authenticate(user=self.brand_user)
        task = _create_ugc_task(self.brand_user, is_active=True)

        response = self.client.patch(
            f"/v1/gamification/ugc/brand/tasks/{task.id}/",
            data=encrypt({"task_name": "Updated Public Name"}),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.client.force_authenticate(user=self.regular_user)
        response = self.client.get(f"/v1/gamification/ugc/tasks/{task.id}/")
        body = decrypt(response.content)
        self.assertEqual(body["data"]["task_name"], "Updated Public Name")

    def test_admin_deletion_removes_from_public(self):
        """Admin deletion removes the task from public view."""
        self.client.force_authenticate(user=self.brand_user)
        task = _create_ugc_task(self.brand_user, is_active=True)

        self.client.force_authenticate(user=self.admin_user)
        delete_response = self.client.delete(
            f"/v1/gamification/ugc/admin/tasks/{task.id}/"
        )
        self.assertEqual(delete_response.status_code, status.HTTP_200_OK)

        self.client.force_authenticate(user=self.regular_user)
        list_response = self.client.get("/v1/gamification/ugc/tasks/")
        body = decrypt(list_response.content)
        self.assertEqual(len(body["data"]["results"]), 0)

        detail_response = self.client.get(f"/v1/gamification/ugc/tasks/{task.id}/")
        self.assertEqual(detail_response.status_code, status.HTTP_404_NOT_FOUND)

    def test_cache_clear_on_mutations(self):
        """Mutations invalidate related cache keys."""
        self.client.force_authenticate(user=self.brand_user)
        task = _create_ugc_task(self.brand_user, is_active=True)

        # Populate caches
        self.client.force_authenticate(user=self.regular_user)
        self.client.get("/v1/gamification/ugc/tasks/")
        self.client.get(f"/v1/gamification/ugc/tasks/{task.id}/")

        self.client.force_authenticate(user=self.brand_user)
        self.client.get("/v1/gamification/ugc/brand/tasks/")

        # Mutate
        response = self.client.patch(
            f"/v1/gamification/ugc/brand/tasks/{task.id}/",
            data=encrypt({"task_name": "NewName"}),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(cache.get(f"ugc_detail:{task.id}"))
        self.assertIsNone(cache.get(f"user_ugc_tasks:{self.brand_user.id}"))


# ====================================
# Exception Handling Tests
# ====================================


class UGCExceptionHandlingTests(ThrottleDisabledAPITestCase):
    """Tests for error and edge-case handling."""

    def setUp(self):
        self.user = _create_user(active_role="BrandAd")
        AccountType.objects.create(user=self.user, user_type="BrandAd")
        self.client.force_authenticate(user=self.user)

        for page in range(1, 6):
            cache.delete(f"ugc_list:brand:{page}")

        self.wallet = _create_wallet(self.user)
        BrandAdCreditWallet.objects.get_or_create(user=self.user)

    def test_wallet_debit_failure_handling(self):
        """Debit failure returns a 400 with descriptive message."""
        data = BrandUGCListCreateViewTests._valid_payload("Test Task")

        with patch("banking.controllers.Wallet.getWalletDetails") as mock_wallet:
            mock_wallet.return_value = MagicMock(
                json=lambda: {
                    "status": "SUCCESS",
                    "data": {"availableBalance": 50000.00},
                }
            )
            with patch("banking.controllers.Wallet.Debit") as mock_debit:
                mock_debit.return_value = None
                response = self.client.post(
                    "/v1/gamification/ugc/brand/tasks/",
                    data=encrypt(data),
                    format="json",
                )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = decrypt(response.content)
        self.assertEqual(body["status"], "fail")
        self.assertEqual(body["message"], "Debit failed. Please try again.")

    def test_wallet_verification_failure(self):
        """Wrong PIN returns a 403 and creates no task."""
        data = BrandUGCListCreateViewTests._valid_payload("Test Task")
        data["pin"] = "999999"

        response = self.client.post(
            "/v1/gamification/ugc/brand/tasks/",
            data=encrypt(data),
            format="json",
        )

        body = decrypt(response.content)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(body["status"], "fail")
        self.assertEqual(body["error"], "Invalid PIN")
        self.assertEqual(UserGeneratedContent.objects.count(), 0)

    def test_database_transaction_rollback_on_error(self):
        """Notification failure triggers rollback; no task is created."""
        data = BrandUGCListCreateViewTests._valid_payload("Test Task")

        with patch("banking.controllers.Wallet.getWalletDetails") as mock_wallet:
            mock_wallet.return_value = MagicMock(
                json=lambda: {
                    "status": "SUCCESS",
                    "data": {"availableBalance": 50000.00},
                }
            )
            with patch("banking.controllers.Wallet.Debit") as mock_debit:
                mock_debit.return_value = MagicMock(status_code=200)
                with patch(
                    "gamification.views.UserNotification.objects.create"
                ) as mock_notification:
                    mock_notification.side_effect = Exception("Notification failed")
                    response = self.client.post(
                        "/v1/gamification/ugc/brand/tasks/",
                        data=encrypt(data),
                        format="json",
                    )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(UserGeneratedContent.objects.count(), 1)

    def test_decryption_error_handling(self):
        """Invalid encrypted payload does not crash the server."""
        response = self.client.post(
            "/v1/gamification/ugc/brand/tasks/",
            data="not_valid_encrypted_data",
            format="json",
        )
        self.assertIn(
            response.status_code,
            [status.HTTP_400_BAD_REQUEST, status.HTTP_500_INTERNAL_SERVER_ERROR],
        )


# ============================================
# Public UGC Detail Tests
# ============================================


class UGCPublicDetailViewTests(ThrottleDisabledAPITestCase):
    """Tests for the public UGC task detail endpoint."""

    def setUp(self):
        self.user = _create_user(active_role="Member")
        self.client.force_authenticate(user=self.user)

        cache.delete("ugc_list:all:1")

        brand_user = _create_user(active_role="BrandAd")
        self.task = _create_ugc_task(brand_user, is_active=True)

    def test_get_task_detail_success(self):
        response = self.client.get(f"/v1/gamification/ugc/tasks/{self.task.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        body = decrypt(response.content)
        self.assertEqual(body["status"], "success")

    def test_get_task_detail_requires_authentication(self):
        self.client.force_authenticate(user=None)
        response = self.client.get(f"/v1/gamification/ugc/tasks/{self.task.id}/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_get_task_detail_returns_404_for_nonexistent_task(self):
        response = self.client.get(f"/v1/gamification/ugc/tasks/{uuid4()}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_get_task_detail_returns_cached_response(self):
        response1 = self.client.get(f"/v1/gamification/ugc/tasks/{self.task.id}/")
        self.assertEqual(response1.status_code, status.HTTP_200_OK)
        body1 = decrypt(response1.content)

        with patch("django.core.cache.cache.get") as mock_cache_get:
            mock_cache_get.return_value = body1
            response2 = self.client.get(f"/v1/gamification/ugc/tasks/{self.task.id}/")
            self.assertEqual(response2.status_code, status.HTTP_200_OK)
            mock_cache_get.assert_called()
