import json as _json
from unittest.mock import patch
from uuid import uuid4

from django.core.cache import cache
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from adverts.models import CreateAd
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
        names = [item["campaign_name"] for item in body["data"]]
        self.assertIn("Active Campaign", names)

    def test_excludes_inactive_campaigns(self):
        _create_ad(self.brand, campaign_name="Inactive", is_active=False)
        self.client.force_authenticate(user=self.user)

        response = self.client.get(self.url)

        body = decrypt(response.data)
        names = [item["campaign_name"] for item in body["data"]]
        self.assertNotIn("Inactive", names)

    def test_excludes_campaigns_user_already_submitted(self):
        ad = _create_ad(self.brand, campaign_name="Already Done")
        BrandTaskSubmission.objects.create(ad=ad, user=self.user, status="Approved")
        self.client.force_authenticate(user=self.user)

        response = self.client.get(self.url)

        body = decrypt(response.data)
        names = [item["campaign_name"] for item in body["data"]]
        self.assertNotIn("Already Done", names)

    def test_excludes_slot_capped_campaigns(self):
        _create_ad(self.brand, campaign_name="Full", slot_cap=5, slots_filled=5)
        self.client.force_authenticate(user=self.user)

        response = self.client.get(self.url)

        body = decrypt(response.data)
        names = [item["campaign_name"] for item in body["data"]]
        self.assertNotIn("Full", names)

    def test_task_type_filter(self):
        _create_ad(self.brand, campaign_name="Video Task", task_type="watch_video")
        _create_ad(self.brand, campaign_name="Survey Task", task_type="survey")
        self.client.force_authenticate(user=self.user)

        response = self.client.get(self.url + "?task_type=survey")

        body = decrypt(response.data)
        names = [item["campaign_name"] for item in body["data"]]
        self.assertIn("Survey Task", names)
        self.assertNotIn("Video Task", names)


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
            data=_make_payload(ad=str(self.ad.id)),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    @patch("tasks.jobs.approve_brand_submission.delay")
    def test_watch_video_auto_approves_and_queues_points(self, mock_delay):
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            self.url,
            data=_make_payload(ad=str(self.ad.id)),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        body = decrypt(response.data)
        self.assertEqual(body["status"], "success")
        self.assertIn("Points are being credited", body["message"])
        mock_delay.assert_called_once()
        submission = BrandTaskSubmission.objects.get(pk=body["data"]["submission_id"])
        self.assertEqual(submission.user, self.user)

    @patch("tasks.jobs.approve_brand_submission.delay")
    def test_social_engage_without_screenshot_returns_400(self, mock_delay):
        social_ad = _create_ad(
            self.brand,
            task_type="social_engage",
            task_details={"platform": "Instagram", "post_url": "https://ig.com/p/1", "required_actions": ["like"]},
        )
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            self.url,
            data=_make_payload(ad=str(social_ad.id)),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        mock_delay.assert_not_called()

    @patch("tasks.jobs.approve_brand_submission.delay")
    def test_social_engage_with_screenshot_queues_for_review(self, mock_delay):
        social_ad = _create_ad(
            self.brand,
            task_type="social_engage",
            task_details={"platform": "Instagram", "post_url": "https://ig.com/p/1", "required_actions": ["like"]},
        )
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            self.url,
            data=_make_payload(
                ad=str(social_ad.id),
                screenshot_url="https://cdn.example.com/proof.png",
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        body = decrypt(response.data)
        self.assertIn("screenshot is being reviewed", body["message"])
        mock_delay.assert_not_called()
        submission = BrandTaskSubmission.objects.get(ad=social_ad, user=self.user)
        self.assertEqual(submission.status, "Pending")

    @patch("tasks.jobs.approve_brand_submission.delay")
    def test_duplicate_submission_returns_400(self, mock_delay):
        BrandTaskSubmission.objects.create(ad=self.ad, user=self.user)
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            self.url,
            data=_make_payload(ad=str(self.ad.id)),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        mock_delay.assert_not_called()

    @patch("tasks.jobs.approve_brand_submission.delay")
    def test_inactive_campaign_returns_400(self, mock_delay):
        inactive_ad = _create_ad(self.brand, is_active=False)
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            self.url,
            data=_make_payload(ad=str(inactive_ad.id)),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        mock_delay.assert_not_called()

    @patch("tasks.jobs.approve_brand_submission.delay")
    def test_slot_capped_campaign_returns_400(self, mock_delay):
        capped_ad = _create_ad(self.brand, slot_cap=1, slots_filled=1)
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            self.url,
            data=_make_payload(ad=str(capped_ad.id)),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        mock_delay.assert_not_called()


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
        BrandTaskSubmission.objects.create(ad=other_ad, user=self.other, status="Pending")
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
