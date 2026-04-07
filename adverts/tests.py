from datetime import timedelta
from uuid import uuid4

from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from adverts.models import CreateAd
from adverts.serializers import AdSerializers
from security import decrypt


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

    def test_ad_serializer_marks_expired_ads_inactive(self):
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
        self.assertFalse(ad.is_active)
