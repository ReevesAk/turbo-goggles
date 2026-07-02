from datetime import timedelta
from uuid import uuid4

from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from gamification.models import StepCampaignModel, StepSessionModel
from security import decrypt


def _create_user(**overrides):
	seed = uuid4().hex[:8]
	data = {
		"phone_number": f"23490{seed[:7]}",
		"password": "StrongPass123!",
		"first_name": "Game",
		"last_name": "User",
		"email": f"game.{seed}@example.com",
		"country": "NG",
		"state": "Lagos",
		"city": "Ikeja",
		"is_verified": True,
		"active_role": "Member",
	}
	data.update(overrides)
	password = data.pop("password")
	user = User.objects.create(**data)
	user.set_password(password)
	user.save()
	return user


class StepSessionModelBehaviorTests(APITestCase):
	def test_total_steps_and_completion_across_sessions(self):
		user = _create_user()
		campaign = StepCampaignModel.objects.create(
			name="10K Steps",
			duration=timedelta(days=1),
			step_target=5000,
			reward_points=100,
			time_limit=timedelta(hours=24),
			created_by=user,
		)

		session_one = StepSessionModel.objects.create(
			campaign=campaign,
			user=user,
			step_count=2200,
			started_at=timezone.now(),
		)
		StepSessionModel.objects.create(
			campaign=campaign,
			user=user,
			session_date=timezone.now().date() - timedelta(days=1),
			step_count=3000,
			started_at=timezone.now() - timedelta(days=1),
		)

		self.assertEqual(session_one.total_steps, 5200)
		self.assertTrue(session_one.check_completion())


class JoinCampaignEndpointTests(APITestCase):
	def test_join_campaign_returns_404_for_missing_campaign(self):
		user = _create_user(active_role="Member")
		self.client.force_authenticate(user=user)

		response = self.client.post(
			f"/v1/gamification/campaigns/{uuid4()}/join/"
		)

		self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
		body = decrypt(response.data)
		self.assertEqual(body["status"], "fail")
		self.assertIn("Campaign not found", body["message"])
