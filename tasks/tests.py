import json as _json
from unittest.mock import patch
from uuid import uuid4

from django.core.cache import cache
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from adverts.models import CreateAd
from gamification.models import PointTransaction, Points
from security import decrypt, encrypt
from tasks.models import BrandTaskSubmission, SocialTask, TaskSubmission


def _make_payload(**kwargs):
    return _json.dumps(encrypt(kwargs))


def _create_user(**overrides):
    seed = uuid4().hex[:8]
    data = {
        "phone_number": f"23481{seed[:7]}",
        "first_name": "Test",
        "last_name": "User",
        "email": f"user.{seed}@example.com",
        "country": "NG",
        "state": "Lagos",
        "city": "Ikeja",
        "is_verified": True,
        "active_role": "Member",
    }
    data.update(overrides)
    user = User.objects.create(**data)
    user.set_password("StrongPass123!")
    user.save()
    return user


def _create_ad(user, **overrides):
    defaults = {
        "campaign_name": f"Campaign {uuid4().hex[:6]}",
        "business_or_brand_name": "Test Brand",
        "task_type": "watch_video",
        "task_details": {
            "video_url": "https://example.com/vid",
            "platform": "YouTube",
            "min_watch_duration": 30,
        },
        "reward_points": 50,
        "is_active": True,
        # Real campaigns always carry a duration; CreateAd.save derives
        # expiry_date from it, and the feed only lists unexpired ads.
        "campaign_duration": 7,
    }
    defaults.update(overrides)
    return CreateAd.objects.create(user=user, **defaults)


# Brand Task Feed


class BrandTaskFeedViewTests(APITestCase):
    url = "/v1/tasks/brand/feed/"

    def setUp(self):
        cache.clear()
        self.user = _create_user()
        self.brand = _create_user(active_role="BrandAd")

    def test_requires_authentication(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_returns_active_campaigns(self):
        _create_ad(self.brand, campaign_name="Active Campaign")
        self.client.force_authenticate(user=self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.data)
        self.assertEqual(body["status"], "success")
        names = [item["campaign_name"] for item in body["data"]["active"]]
        self.assertIn("Active Campaign", names)

    def test_excludes_inactive_campaigns(self):
        _create_ad(self.brand, campaign_name="Inactive", is_active=False)
        self.client.force_authenticate(user=self.user)

        response = self.client.get(self.url)

        body = decrypt(response.data)
        names = [item["campaign_name"] for item in body["data"]["active"]]
        self.assertNotIn("Inactive", names)

    def test_excludes_campaigns_user_already_submitted(self):
        ad = _create_ad(self.brand, campaign_name="Already Done")
        BrandTaskSubmission.objects.create(ad=ad, user=self.user, status="Approved")
        self.client.force_authenticate(user=self.user)

        response = self.client.get(self.url)

        body = decrypt(response.data)
        names = [item["campaign_name"] for item in body["data"]["active"]]
        self.assertNotIn("Already Done", names)

    def test_task_type_filter(self):
        _create_ad(self.brand, campaign_name="Video Task", task_type="watch_video")
        _create_ad(self.brand, campaign_name="Survey Task", task_type="survey")
        self.client.force_authenticate(user=self.user)

        response = self.client.get(self.url + "?task_type=survey")

        body = decrypt(response.data)
        names = [item["campaign_name"] for item in body["data"]["active"]]
        self.assertIn("Survey Task", names)
        self.assertNotIn("Video Task", names)

    def test_store_visit_filter_returns_store_visits(self):
        # Regression: feed items nest their type under "task", so the
        # store_visit filter used to drop every item and return [].
        _create_ad(self.brand, campaign_name="Store Task", task_type="store_visit")
        _create_ad(self.brand, campaign_name="Video Task", task_type="watch_video")
        self.client.force_authenticate(user=self.user)

        response = self.client.get(self.url + "?task_type=store_visit")

        body = decrypt(response.data)
        names = [item["campaign_name"] for item in body["data"]["active"]]
        self.assertIn("Store Task", names)
        self.assertNotIn("Video Task", names)

    def test_excludes_streak_challenge_not_yet_started(self):
        """
        A StreakChallenge scheduled to start in the future must not show up
        as an available task on the feed - it isn't "active" until its
        start_date, same as the admin dashboard's task_status/is_ongoing.
        """
        from datetime import timedelta

        from django.utils import timezone

        from gamification.models import StreakChallenge

        StreakChallenge.objects.create(
            name="Not Started Yet",
            streak_type="financial_task",
            mission_category="kyc_upgrade",
            duration_days=14,
            start_date=timezone.now() + timedelta(days=2),
            end_date=timezone.now() + timedelta(days=16),
            reward_points=175,
            is_active=True,
        )
        self.client.force_authenticate(user=self.user)

        response = self.client.get(self.url)

        body = decrypt(response.data)
        names = [item["campaign_name"] for item in body["data"]["active"]]
        self.assertNotIn("Not Started Yet", names)

    def test_includes_ongoing_streak_challenge_with_status_fields(self):
        from datetime import timedelta

        from django.utils import timezone

        from gamification.models import StreakChallenge

        StreakChallenge.objects.create(
            name="Share Picadailys App on X",
            streak_type="financial_task",
            mission_category="kyc_upgrade",
            action_type="one_time",
            kyc_target_tier=1,
            duration_days=14,
            start_date=timezone.now() - timedelta(days=1),
            end_date=timezone.now() + timedelta(days=13),
            reward_points=175,
            is_active=True,
        )
        self.client.force_authenticate(user=self.user)

        response = self.client.get(self.url)

        body = decrypt(response.data)
        item = next(
            i for i in body["data"]["active"] if i["campaign_name"] == "Share Picadailys App on X"
        )
        self.assertEqual(item["source"], "inapp")
        details = item["task"]["details"]
        self.assertEqual(details["task_status"], "active")
        self.assertFalse(details["is_scheduled"])
        self.assertFalse(details["is_paused"])
        self.assertFalse(details["is_cancelled"])
        self.assertEqual(details["kyc_target_tier"], 1)


# Submit Brand Task
class SubmitBrandTaskViewTests(APITestCase):
    url = "/v1/tasks/brand/submit/"

    def setUp(self):
        cache.clear()
        self.user = _create_user()
        self.brand = _create_user(active_role="BrandAd")
        self.ad = _create_ad(self.brand, task_type="watch_video")

    def test_requires_authentication(self):
        response = self.client.post(
            self.url,
            data=_make_payload(task=str(self.ad.id)),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    @patch("tasks.jobs.approve_brand_submission.delay")
    def test_watch_video_rejected_use_webview_endpoint(self, mock_delay):
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            self.url,
            data=_make_payload(task=str(self.ad.id)),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("only for social engage tasks", decrypt(response.data)["message"])
        mock_delay.assert_not_called()
        self.assertFalse(
            BrandTaskSubmission.objects.filter(ad=self.ad, user=self.user).exists()
        )

    @patch("tasks.jobs.approve_brand_submission.delay")
    def test_social_engage_without_screenshot_returns_400(self, mock_delay):
        social_ad = _create_ad(
            self.brand,
            task_type="social_engage",
            task_details={
                "platform": "Instagram",
                "post_url": "https://ig.com/p/1",
                "required_actions": ["like"],
            },
        )
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            self.url,
            data=_make_payload(task=str(social_ad.id)),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("screenshot is required", decrypt(response.data)["message"])
        mock_delay.assert_not_called()

    @patch("tasks.jobs.approve_brand_submission.delay")
    @patch("tasks.views.run_brand_verification.delay")
    def test_social_engage_with_screenshot_queues_ai_verification(
        self, mock_verify, mock_delay
    ):
        social_ad = _create_ad(
            self.brand,
            task_type="social_engage",
            task_details={
                "platform": "Instagram",
                "post_url": "https://ig.com/p/1",
                "required_actions": ["like"],
            },
        )
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            self.url,
            data=_make_payload(
                task=str(social_ad.id),
                screenshot_url="https://cdn.example.com/proof.png",
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        body = decrypt(response.data)
        self.assertIn("Verification in progress", body["message"])
        mock_delay.assert_not_called()
        submission = BrandTaskSubmission.objects.get(ad=social_ad, user=self.user)
        self.assertEqual(submission.status, "Pending")
        mock_verify.assert_called_once_with(str(submission.pk))

    @patch("tasks.jobs.approve_brand_submission.delay")
    def test_duplicate_submission_returns_400(self, mock_delay):
        social_ad = _create_ad(self.brand, task_type="social_engage")
        BrandTaskSubmission.objects.create(ad=social_ad, user=self.user)
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            self.url,
            data=_make_payload(
                task=str(social_ad.id),
                screenshot_url="https://cdn.example.com/proof.png",
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("already submitted", decrypt(response.data)["message"])
        mock_delay.assert_not_called()

    @patch("tasks.jobs.approve_brand_submission.delay")
    def test_inactive_campaign_returns_400(self, mock_delay):
        inactive_ad = _create_ad(self.brand, is_active=False)
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            self.url,
            data=_make_payload(task=str(inactive_ad.id)),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("no longer active", decrypt(response.data)["message"])
        mock_delay.assert_not_called()


class CompleteWebviewTaskViewTests(APITestCase):
    url = "/v1/tasks/brand/webview/complete/"

    def setUp(self):
        cache.clear()
        self.user = _create_user()
        self.brand = _create_user(active_role="BrandAd")
        self.ad = _create_ad(self.brand, task_type="watch_video", reward_points=50)

    def test_requires_authentication(self):
        response = self.client.post(
            self.url,
            data=_make_payload(task_id=self.ad.id, is_done=True),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_webview_task_completion_awards_points_immediately(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            self.url,
            data=_make_payload(task_id=self.ad.id, is_done=True),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        body = decrypt(response.data)
        self.assertEqual(body["status"], "success")
        self.assertEqual(body["data"]["task_id"], self.ad.id)
        self.assertEqual(body["data"]["reward_points"], 50)
        self.assertTrue(body["data"]["reward_issued"])

        submission = BrandTaskSubmission.objects.get(ad=self.ad, user=self.user)
        self.assertEqual(submission.status, "Approved")
        self.assertTrue(submission.reward_issued)

        points = Points.objects.get(user=self.user)
        self.assertEqual(points.balance, 50)
        self.user.refresh_from_db()
        self.assertEqual(self.user.total_points, 50)
        self.assertTrue(
            PointTransaction.objects.filter(
                user=self.user,
                source="watch_video",
                reference_id=str(submission.pk),
                amount=50,
            ).exists()
        )

    def test_rejects_when_is_done_is_false(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            self.url,
            data=_make_payload(task_id=self.ad.id, is_done=False),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(
            BrandTaskSubmission.objects.filter(ad=self.ad, user=self.user).exists()
        )

    def test_rejects_non_webview_task(self):
        social_ad = _create_ad(self.brand, task_type="social_engage")
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            self.url,
            data=_make_payload(task_id=social_ad.id, is_done=True),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(
            BrandTaskSubmission.objects.filter(ad=social_ad, user=self.user).exists()
        )

    def test_rejects_duplicate_completion(self):
        BrandTaskSubmission.objects.create(
            ad=self.ad, user=self.user, status="Approved", reward_issued=True
        )
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            self.url,
            data=_make_payload(task_id=self.ad.id, is_done=True),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            BrandTaskSubmission.objects.filter(ad=self.ad, user=self.user).count(), 1
        )


# My Brand Submissions


class MyBrandSubmissionsViewTests(APITestCase):
    url = "/v1/tasks/brand/my-submissions/"

    def setUp(self):
        cache.clear()
        self.user = _create_user()
        self.other = _create_user()
        self.brand = _create_user(active_role="BrandAd")

    def test_requires_authentication(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_returns_only_own_submissions(self):
        my_ad = _create_ad(self.brand, campaign_name="My Campaign")
        other_ad = _create_ad(self.brand, campaign_name="Other Campaign")
        BrandTaskSubmission.objects.create(ad=my_ad, user=self.user, status="Approved")
        BrandTaskSubmission.objects.create(
            ad=other_ad, user=self.other, status="Pending"
        )
        self.client.force_authenticate(user=self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.data)
        self.assertEqual(body["status"], "success")
        self.assertEqual(len(body["data"]), 1)
        self.assertEqual(body["data"][0]["campaign_name"], "My Campaign")

    def test_response_includes_status_and_reward_fields(self):
        ad = _create_ad(self.brand, reward_points=75, campaign_name="Points Campaign")
        BrandTaskSubmission.objects.create(
            ad=ad, user=self.user, status="Approved", reward_issued=True
        )
        self.client.force_authenticate(user=self.user)

        response = self.client.get(self.url)

        body = decrypt(response.data)
        submission = body["data"][0]
        self.assertEqual(submission["status"], "Approved")
        self.assertTrue(submission["reward_issued"])
        self.assertEqual(submission["reward_points"], 75)
