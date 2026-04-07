import json as _json
from uuid import uuid4

from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from security import decrypt, encrypt


def _make_payload(**kwargs):
    return _json.dumps(encrypt(kwargs))


def _create_user(**overrides):
    seed = uuid4().hex[:8]
    data = {
        "phone_number": f"23480{seed[:7]}",
        "password": "StrongPass123!",
        "first_name": "Partner",
        "last_name": "User",
        "email": f"partner.{seed}@example.com",
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


class PartnersBehaviorTests(APITestCase):
    def test_list_all_partners_returns_only_partner_role_users(self):
        requester = _create_user(active_role="Member")
        _create_user(active_role="Partner", business_name="Biz 1")
        _create_user(active_role="Partner", business_name="Biz 2")
        _create_user(active_role="Member")

        self.client.force_authenticate(user=requester)
        response = self.client.get("/v1/partners/list-all-partners")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = decrypt(response.data)
        results = payload.get("results", [])
        self.assertGreaterEqual(len(results), 2)
        self.assertTrue(all(item.get("active_role") == "Partner" for item in results))

    def test_create_partner_rejects_empty_payload(self):
        user = _create_user(active_role="Member")
        self.client.force_authenticate(user=user)

        response = self.client.post(
            "/v1/partners/create-partners",
            data=_make_payload(),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        user.refresh_from_db()
        self.assertEqual(user.active_role, "Member")
