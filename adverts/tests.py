from datetime import timedelta
from uuid import uuid4
from unittest.mock import patch, MagicMock

from django.contrib.auth.hashers import make_password
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User, TxModel
from adverts.models import AdLocation, CreateAd
from adverts.serializers import AdSerializers
from banking.models import FundWithCard, WalletModel
from gamification.models import UserGeneratedContent, StreakChallenge
from security import decrypt, encrypt
from tasks.models import BrandTaskSubmission
from user_profile.models import MemberSurvey


def _create_ugc_task(user, **overrides):
    defaults = {
        "user": user,
        "business_or_brand_name": "Test Brand",
        "type_of_business": "online",
        "task_name": "Test UGC Task",
        "task_type": "take_a_picture",
        "description": "Take a picture with our product",
        "thumbnail_url": "https://res.cloudinary.com/example/image/upload/thumb.jpg",
        "sample_url": "https://res.cloudinary.com/example/image/upload/sample.jpg",
        "slot_cap": 100,
        "slots_filled": 0,
        "amount": "10000.00",
        "reward_points": 50,
        "targeting_type": "broad",
        "location_perimeter": "nation_wide",
        "gender": "all",
        "is_active": True,
        "credit_settled": False,
        "unlimited_slots": False,
    }
    defaults.update(overrides)
    return UserGeneratedContent.objects.create(**defaults)


def _create_inapp_task(user, **overrides):
    defaults = {
        "created_by": user,
        "name": "Test In-App Task",
        "streak_type": "financial_task",
        "duration_days": 14,
        "start_date": timezone.now(),
        "end_date": timezone.now() + timedelta(days=14),
        "reward_points": 100,
    }
    defaults.update(overrides)
    return StreakChallenge.objects.create(**defaults)


def _create_user(**overrides):
    seed = uuid4().hex[:8]
    data = {
        "phone_number": f"23481{seed[:7]}",
        "password": "StrongPass123!",
        "first_name": "Brand",
        "last_name": "User",
        "email": f"brand.{seed}@example.com",
        "country": "NG",
        "state": "Lagos",
        "city": "Ikeja",
        "is_verified": True,
        "active_role": "BrandAd",
    }
    data.update(overrides)
    password = data.pop("password")
    user = User.objects.create(**data)
    user.set_password(password)
    user.save()
    return user


class AdvertsBehaviorTests(APITestCase):
    def test_list_all_ads_returns_current_users_ads_only(self):
        owner = _create_user(active_role="BrandAd")
        other = _create_user(active_role="BrandAd")

        CreateAd.objects.create(user=owner, campaign_name="Owner Campaign")
        CreateAd.objects.create(user=other, campaign_name="Other Campaign")

        self.client.force_authenticate(user=owner)
        response = self.client.get("/v1/adverts/list-all-ads")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.data)
        self.assertEqual(body["status"], "success")

        data = body["data"]
        results = data.get("results") if isinstance(data, dict) else data
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["campaign_name"], "Owner Campaign")

    def test_ad_serializer_reports_expired_without_writing(self):
        # Serializing is read-only: expiry is reported via remaining_time and
        # handled by cleanup_expired_ads, not by flipping is_active on read.
        user = _create_user(active_role="BrandAd")
        ad = CreateAd.objects.create(
            user=user,
            campaign_name="Expiring Campaign",
            expiry_date=timezone.now() - timedelta(hours=1),
            is_active=True,
        )

        serialized = AdSerializers(ad).data
        ad.refresh_from_db()

        self.assertEqual(serialized["remaining_time"], "Expired")
        self.assertTrue(ad.is_active)

    def test_list_all_ads_includes_ugc_tasks(self):
        """
        UGC tasks (UserGeneratedContent) are a separate model/app from
        CreateAd, but a brand thinks of both as just "my ads" - regression
        coverage for list-all-ads never surfacing UGC tasks at all.
        """
        owner = _create_user(active_role="BrandAd")
        other = _create_user(active_role="BrandAd")

        CreateAd.objects.create(user=owner, campaign_name="Owner Campaign")
        _create_ugc_task(owner, task_name="Owner UGC Task")
        _create_ugc_task(other, task_name="Other Brand's UGC Task")

        self.client.force_authenticate(user=owner)
        response = self.client.get("/v1/adverts/list-all-ads")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.data)
        data = body["data"]
        results = data.get("results") if isinstance(data, dict) else data

        self.assertEqual(len(results), 2)
        by_type = {row["ad_type"]: row for row in results}
        self.assertEqual(by_type["brand_ad"]["campaign_name"], "Owner Campaign")
        self.assertEqual(by_type["ugc"]["task_name"], "Owner UGC Task")

    def test_list_all_ads_orders_mixed_ad_types_by_created_at(self):
        owner = _create_user(active_role="BrandAd")

        older_ugc = _create_ugc_task(owner, task_name="Older UGC")
        UserGeneratedContent.objects.filter(pk=older_ugc.pk).update(
            created_at=timezone.now() - timedelta(days=2)
        )
        CreateAd.objects.create(user=owner, campaign_name="Newest Campaign")

        self.client.force_authenticate(user=owner)
        response = self.client.get("/v1/adverts/list-all-ads")

        body = decrypt(response.data)
        data = body["data"]
        results = data.get("results") if isinstance(data, dict) else data

        self.assertEqual(results[0]["ad_type"], "brand_ad")
        self.assertEqual(results[0]["campaign_name"], "Newest Campaign")
        self.assertEqual(results[1]["ad_type"], "ugc")
        self.assertEqual(results[1]["task_name"], "Older UGC")

    def test_list_all_ads_includes_own_inapp_tasks(self):
        """
        StreakChallenge (in-app tasks) is owned via created_by, not user -
        distinct from CreateAd/UserGeneratedContent which are brand-owned.
        """
        admin = _create_user(active_role="SuperAdmin")
        other_admin = _create_user(active_role="SuperAdmin")

        _create_inapp_task(admin, name="My Streak Challenge")
        _create_inapp_task(other_admin, name="Someone Else's Challenge")

        self.client.force_authenticate(user=admin)
        response = self.client.get("/v1/adverts/list-all-ads")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.data)
        data = body["data"]
        results = data.get("results") if isinstance(data, dict) else data

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["ad_type"], "in_app")
        self.assertEqual(results[0]["name"], "My Streak Challenge")


def _create_ad(user, **overrides):
    defaults = {
        "campaign_name": f"Campaign {uuid4().hex[:6]}",
        "business_or_brand_name": "Emeka & Sons",
        "type_of_business": "Hybrid",
        "industry": "Health and Fitness",
        "brand_objective": "Brand Awareness",
        "task_type": "social_engage",
        "task_name": "Match up your body",
        "task_description": "Follow me and engage in my post",
        "task_details": {
            "platform": "Instagram",
            "post_url": "https://instagram.com/p/abc123",
            "required_actions": ["like", "comment"],
            "timing": "30s",
            "comment_prompt": "Tag a friend in the comment section",
        },
        "engagement_type": "Like Post",
        "reward_points": 40,
        "slot_cap": 1000,
        "slots_filled": 0,
        "campaign_duration": "7",
        "amount": "170000",
        "gender": "All",
        "demography": "18 - 25",
        "auto_boost": True,
        "auto_boost_points": 0,
        "ads_credit": "0",
        "is_active": True,
        "expiry_date": timezone.now() + timedelta(days=7),
    }
    defaults.update(overrides)
    return CreateAd.objects.create(user=user, **defaults)


def _create_participant(
    brand_user, ad, sex="Male", age_bracket="18 - 25", state="Lagos"
):
    seed = uuid4().hex[:8]
    participant = User.objects.create(
        phone_number=f"23481{seed[:7]}",
        first_name="Participant",
        last_name="User",
        email=f"participant.{seed}@example.com",
        country="NG",
        state=state,
        is_verified=True,
        active_role="Member",
    )
    participant.set_password("StrongPass123!")
    participant.save()
    MemberSurvey.objects.create(
        user=participant,
        sex=sex,
        age_bracket=age_bracket,
        state=state,
    )
    BrandTaskSubmission.objects.create(ad=ad, user=participant, status="Approved")
    return participant


class BrandAdAnalyticsViewTests(APITestCase):
    url_template = "/v1/adverts/analytics/{}/"

    def setUp(self):
        self.brand = _create_user(active_role="BrandAd")
        self.other = _create_user(active_role="BrandAd")

    # ── Auth & ownership ──────────────────────────────────────────────────────

    def test_requires_authentication(self):
        ad = _create_ad(self.brand)
        response = self.client.get(self.url_template.format(ad.id))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_404_for_nonexistent_ad(self):
        self.client.force_authenticate(user=self.brand)
        response = self.client.get(self.url_template.format(99999))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_403_when_ad_belongs_to_another_user(self):
        ad = _create_ad(self.other)
        self.client.force_authenticate(user=self.brand)
        response = self.client.get(self.url_template.format(ad.id))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # ── Ongoing ad ───────────────────────────────────────────────────────────

    def test_ongoing_ad_returns_is_finished_false(self):
        ad = _create_ad(self.brand)
        self.client.force_authenticate(user=self.brand)

        response = self.client.get(self.url_template.format(ad.id))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.data)
        self.assertFalse(body["data"]["is_finished"])

    def test_ongoing_ad_has_correct_chips_data(self):
        ad = _create_ad(self.brand, slots_filled=500)
        self.client.force_authenticate(user=self.brand)

        response = self.client.get(self.url_template.format(ad.id))

        data = decrypt(response.data)["data"]
        self.assertEqual(data["objective"], "Brand Awareness")
        self.assertEqual(data["task_type"], "social_engage")
        self.assertEqual(data["platform"], "Instagram")
        self.assertEqual(data["slots_filled"], 500)
        self.assertEqual(data["slot_cap"], 1000)
        self.assertEqual(data["duration_days"], 7)
        self.assertIsNotNone(data["current_day"])

    def test_ongoing_ad_includes_location_perimeter(self):
        ad = _create_ad(self.brand)
        AdLocation.objects.create(brand=ad, state="Abia")
        AdLocation.objects.create(brand=ad, state="Lagos")
        self.client.force_authenticate(user=self.brand)

        response = self.client.get(self.url_template.format(ad.id))

        data = decrypt(response.data)["data"]
        perimeter = data["location_perimeter"]
        self.assertIsNotNone(perimeter)
        self.assertEqual(perimeter["gender"], "All")
        self.assertEqual(perimeter["demography"], "18 - 25")
        self.assertIn("Abia", perimeter["states"])
        self.assertIn("Lagos", perimeter["states"])
        self.assertEqual(perimeter["slot_cap"], 1000)
        self.assertEqual(perimeter["reward_points"], 40)

    def test_ongoing_ad_has_no_performance_sections(self):
        ad = _create_ad(self.brand)
        self.client.force_authenticate(user=self.brand)

        response = self.client.get(self.url_template.format(ad.id))

        data = decrypt(response.data)["data"]
        self.assertIsNone(data["performance_breakdown"])
        self.assertIsNone(data["performance_demographic"])

    def test_ongoing_ad_task_details_fields_present(self):
        ad = _create_ad(self.brand)
        self.client.force_authenticate(user=self.brand)

        response = self.client.get(self.url_template.format(ad.id))

        data = decrypt(response.data)["data"]
        self.assertEqual(data["task_name"], "Match up your body")
        self.assertEqual(data["task_description"], "Follow me and engage in my post")
        self.assertEqual(data["campaign_budget"], "170000")
        self.assertEqual(data["reward_points"], 40)
        self.assertEqual(data["brand_name"], "Emeka & Sons")
        self.assertEqual(data["business_type"], "Hybrid")
        self.assertEqual(data["industry"], "Health and Fitness")
        self.assertEqual(data["user_action"], "Like Post")
        self.assertEqual(data["comment_prompt"], "Tag a friend in the comment section")
        self.assertEqual(data["timing"], "30s")
        self.assertTrue(data["auto_boost"])

    # ── Finished ad (slots exhausted) ────────────────────────────────────────

    def test_slots_exhausted_returns_is_finished_true(self):
        ad = _create_ad(self.brand, slots_filled=1000)
        self.client.force_authenticate(user=self.brand)

        response = self.client.get(self.url_template.format(ad.id))

        self.assertTrue(decrypt(response.data)["data"]["is_finished"])

    def test_expired_ad_returns_is_finished_true(self):
        ad = _create_ad(self.brand, expiry_date=timezone.now() - timedelta(hours=1))
        self.client.force_authenticate(user=self.brand)

        response = self.client.get(self.url_template.format(ad.id))

        self.assertTrue(decrypt(response.data)["data"]["is_finished"])

    def test_inactive_ad_returns_is_finished_true(self):
        ad = _create_ad(self.brand, is_active=False)
        self.client.force_authenticate(user=self.brand)

        response = self.client.get(self.url_template.format(ad.id))

        self.assertTrue(decrypt(response.data)["data"]["is_finished"])

    def test_finished_ad_has_task_duration_label(self):
        ad = _create_ad(self.brand, slots_filled=1000)
        self.client.force_authenticate(user=self.brand)

        response = self.client.get(self.url_template.format(ad.id))

        data = decrypt(response.data)["data"]
        self.assertEqual(data["task_duration_label"], "7 Days (Completed)")
        self.assertIsNone(data["current_day"])

    def test_finished_ad_has_no_location_perimeter(self):
        ad = _create_ad(self.brand, slots_filled=1000)
        self.client.force_authenticate(user=self.brand)

        response = self.client.get(self.url_template.format(ad.id))

        self.assertIsNone(decrypt(response.data)["data"]["location_perimeter"])

    def test_finished_ad_performance_breakdown_fields(self):
        ad = _create_ad(
            self.brand, slots_filled=1000, ads_credit="10000", auto_boost_points=300000
        )
        self.client.force_authenticate(user=self.brand)

        response = self.client.get(self.url_template.format(ad.id))

        breakdown = decrypt(response.data)["data"]["performance_breakdown"]
        self.assertIsNotNone(breakdown)
        self.assertEqual(breakdown["campaign_budget"], "170000")
        self.assertEqual(breakdown["ads_credit"], "10000.00")
        self.assertEqual(breakdown["reward_per_person"], 40)
        self.assertEqual(breakdown["auto_boost_points"], 300000)
        self.assertEqual(breakdown["total_points_rewarded"], 1000 * 40)

    # ── Performance demographic ───────────────────────────────────────────────

    def test_finished_ad_demographic_by_sex(self):
        ad = _create_ad(self.brand, slots_filled=1000)
        _create_participant(self.brand, ad, sex="Male", state="Abia")
        _create_participant(self.brand, ad, sex="Male", state="Abuja")
        _create_participant(self.brand, ad, sex="Female", state="Rivers")
        self.client.force_authenticate(user=self.brand)

        response = self.client.get(self.url_template.format(ad.id))

        by_sex = decrypt(response.data)["data"]["performance_demographic"]["by_sex"]
        self.assertEqual(by_sex.get("Male"), 2)
        self.assertEqual(by_sex.get("Female"), 1)

    def test_finished_ad_demographic_by_age_bracket(self):
        ad = _create_ad(self.brand, slots_filled=1000)
        _create_participant(self.brand, ad, age_bracket="18 - 25")
        _create_participant(self.brand, ad, age_bracket="18 - 25")
        _create_participant(self.brand, ad, age_bracket="26 - 35")
        self.client.force_authenticate(user=self.brand)

        response = self.client.get(self.url_template.format(ad.id))

        by_age = decrypt(response.data)["data"]["performance_demographic"][
            "by_age_bracket"
        ]
        self.assertEqual(by_age.get("18 - 25"), 2)
        self.assertEqual(by_age.get("26 - 35"), 1)

    def test_finished_ad_demographic_by_state(self):
        ad = _create_ad(self.brand, slots_filled=1000)
        _create_participant(self.brand, ad, state="Abia")
        _create_participant(self.brand, ad, state="Abia")
        _create_participant(self.brand, ad, state="Lagos")
        self.client.force_authenticate(user=self.brand)

        response = self.client.get(self.url_template.format(ad.id))

        by_state = decrypt(response.data)["data"]["performance_demographic"]["by_state"]
        self.assertEqual(by_state.get("Abia"), 2)
        self.assertEqual(by_state.get("Lagos"), 1)

    def test_finished_ad_demographic_empty_when_no_participants(self):
        ad = _create_ad(self.brand, slots_filled=1000)
        self.client.force_authenticate(user=self.brand)

        response = self.client.get(self.url_template.format(ad.id))

        demographic = decrypt(response.data)["data"]["performance_demographic"]
        self.assertEqual(demographic["by_sex"], {})
        self.assertEqual(demographic["by_age_bracket"], {})
        self.assertEqual(demographic["by_state"], {})


def _valid_ad_payload(payment_option="WALLET", **overrides):
    """Return a minimal valid payload for CreateAdAndOnboardBrandView."""
    data = {
        "payment_option": payment_option,
        "business_or_brand_name": "Acme Co",
        "type_of_business": "Online",
        "industry": "Technology",
        "brand_objective": "Brand Awareness",
        "campaign_name": f"Campaign {uuid4().hex[:6]}",
        "gender": "All",
        "demography": "26 - 35",
        "campaign_duration": "7",
        "amount": "10000.00",
        "targeting_type": "broad",
        "location_type": "states",
        "state": ["Lagos"],
        "city": ["Ikeja"],
        "task_type": "watch_video",
        "task_name": "Watch our promo",
        "task_description": "Watch 30 secs of our latest ad.",
        "task_details": {
            "video_url": "https://youtube.com/watch?v=abc123",
            "platform": "YouTube",
            "min_watch_duration": "30s",
        },
        "slot_cap": 200,
    }
    if payment_option == "WALLET":
        data["pin"] = "123456"
    data.update(overrides)
    return data


class CreateAdAndOnboardBrandViewTests(APITestCase):
    """Tests for ad creation's brand-charging flow (BrandChargeMixin)."""

    url = "/v1/adverts/onboard-and-create"

    def setUp(self):
        self.user = _create_user(active_role="BrandAd")
        self.client.force_authenticate(user=self.user)
        self.wallet = WalletModel.objects.create(
            user=self.user,
            account_number="1234567890",
            balance="50000.00",
            walletType="INDIVIDUAL",
            pin=make_password("123456"),
        )

    # --- Wallet payment ---

    def test_create_ad_with_wallet_success(self):
        data = _valid_ad_payload()

        with patch("banking.controllers.Wallet.getWalletDetails") as mock_wallet:
            mock_wallet.return_value = MagicMock(
                json=lambda: {
                    "status": "SUCCESS",
                    "data": {"availableBalance": 50000.00},
                }
            )
            with patch("banking.controllers.Wallet.Debit") as mock_debit:
                mock_debit.return_value = MagicMock(status_code=200)
                response = self.client.post(self.url, data=encrypt(data), format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.content)
        self.assertEqual(body["status"], "Success!")
        self.assertEqual(CreateAd.objects.filter(user=self.user).count(), 1)
        tx = TxModel.objects.get(user=self.user, tx_type="Brand Promotion")
        self.assertEqual(tx.status, "SUCCESS")

    def test_create_ad_insufficient_balance(self):
        data = _valid_ad_payload(amount="100000.00")

        with patch("banking.controllers.Wallet.getWalletDetails") as mock_wallet:
            mock_wallet.return_value = MagicMock(
                json=lambda: {
                    "status": "SUCCESS",
                    "data": {"availableBalance": 50000.00},
                }
            )
            response = self.client.post(self.url, data=encrypt(data), format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = decrypt(response.content)
        self.assertEqual(body["message"], "Insufficient balance.")
        self.assertEqual(CreateAd.objects.filter(user=self.user).count(), 0)

    def test_create_ad_no_wallet_returns_404(self):
        self.wallet.delete()
        data = _valid_ad_payload()

        response = self.client.post(self.url, data=encrypt(data), format="json")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        body = decrypt(response.content)
        self.assertEqual(body["error"], "Account or PIN not found")

    # --- Card payment ---

    def test_create_ad_with_card_payment_success(self):
        FundWithCard.objects.create(
            user=self.user,
            txn_reference="card-ref-123",
            status="success",
            is_processed=False,
            amount="10000.00",
        )
        data = _valid_ad_payload(payment_option="CARD", card_reference="card-ref-123")

        response = self.client.post(self.url, data=encrypt(data), format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.content)
        self.assertEqual(body["status"], "Success!")
        self.assertEqual(CreateAd.objects.filter(user=self.user).count(), 1)

    def test_create_ad_rejects_another_users_card_reference(self):
        other_user = _create_user(active_role="BrandAd")
        FundWithCard.objects.create(
            user=other_user,
            txn_reference="not-mine-456",
            status="success",
            is_processed=False,
            amount="10000.00",
        )
        data = _valid_ad_payload(payment_option="CARD", card_reference="not-mine-456")

        response = self.client.post(self.url, data=encrypt(data), format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(CreateAd.objects.filter(user=self.user).count(), 0)

    # --- Validation & idempotency ---

    def test_create_ad_invalid_payment_option(self):
        data = _valid_ad_payload(payment_option="INVALID")

        response = self.client.post(self.url, data=encrypt(data), format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_ad_idempotency_key_replays_success(self):
        data = _valid_ad_payload(idempotency_key="idem-key-1")

        with patch("banking.controllers.Wallet.getWalletDetails") as mock_wallet:
            mock_wallet.return_value = MagicMock(
                json=lambda: {
                    "status": "SUCCESS",
                    "data": {"availableBalance": 50000.00},
                }
            )
            with patch("banking.controllers.Wallet.Debit") as mock_debit:
                mock_debit.return_value = MagicMock(status_code=200)
                first = self.client.post(self.url, data=encrypt(data), format="json")
                second = self.client.post(self.url, data=encrypt(data), format="json")

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        second_body = decrypt(second.content)
        self.assertEqual(second_body["status"], "success")
        self.assertEqual(second_body["message"], "This request was already processed.")
        self.assertEqual(CreateAd.objects.filter(user=self.user).count(), 1)
