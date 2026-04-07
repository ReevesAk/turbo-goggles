from django.utils import timezone

from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from security import decrypt
from .models import WaitlistModel
from .views import WAITLIST_REWARD, WAITLIST_TARGET


class WaitlistModelTests(APITestCase):
    def test_generate_referral_code_uses_first_name_prefix(self):
        code = WaitlistModel.generate_referral_code(first_name="john doe")

        self.assertTrue(code.startswith("JOHND"))
        self.assertEqual(len(code), 9)

    def test_joined_at_is_set_on_create(self):
        user = WaitlistModel.objects.create(
            f_name="Jane",
            l_name="Doe",
            email="jane_waitlist@example.com",
            phone="2348000000001",
            referral_code="JANE1A2B",
        )

        self.assertIsNotNone(user.joined_at)
        self.assertLessEqual(user.joined_at, timezone.now())


class WaitlistEndpointTests(APITestCase):
    join_url = "/v1/waitlist/join-betauser-waitlist"
    dashboard_url = "/v1/waitlist/waitlist-dashboard"
    public_list_url = "/v1/waitlist/waitlist-users"
    admin_list_url = "/v1/roles/waitlist/all-users"

    def _create_waitlist_user(self, idx, points=0, **extra):
        payload = {
            "f_name": extra.pop("f_name", f"User{idx}"),
            "l_name": extra.pop("l_name", "Test"),
            "email": extra.pop("email", f"waitlist_{idx}@example.com"),
            "phone": extra.pop("phone", f"2348000001{idx:03d}"),
            "referral_code": extra.pop("referral_code", f"CODE{idx:04d}"),
            "points": points,
            "is_student": extra.pop("is_student", False),
            "institution": extra.pop("institution", None),
        }
        payload.update(extra)
        return WaitlistModel.objects.create(**payload)

    def _create_admin_user(self, active_role="SuperAdmin", phone="2348111111111"):
        return User.objects.create_user(
            phone_number=phone,
            password="StrongPass123!",
            first_name="Admin",
            last_name="User",
            country="NG",
            state="Lagos",
            city="Ikeja",
            active_role=active_role,
            is_verified=True,
        )

    def test_join_waitlist_get_returns_slots_and_reward(self):
        self._create_waitlist_user(idx=1)

        response = self.client.get(self.join_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "success")
        self.assertEqual(response.data["data"]["waitlist_target"], WAITLIST_TARGET)
        self.assertEqual(response.data["data"]["total_joined"], 1)
        self.assertEqual(response.data["data"]["remaining_slots"], WAITLIST_TARGET - 1)
        self.assertEqual(response.data["data"]["reward"], WAITLIST_REWARD)

    def test_join_waitlist_post_creates_user_and_returns_remaining_slots(self):
        payload = {
            "f_name": "Kemi",
            "l_name": "Stone",
            "email": "kemi@example.com",
            "phone": "2348022222222",
            "is_student": True,
            "institution": "University of Lagos",
        }

        response = self.client.post(self.join_url, data=payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], "success")
        self.assertEqual(response.data["data"]["email"], payload["email"])
        self.assertEqual(response.data["data"]["points"], 10)
        self.assertEqual(
            response.data["data"]["remaining_slots"],
            WAITLIST_TARGET - WaitlistModel.objects.count(),
        )
        created = WaitlistModel.objects.get(email=payload["email"])
        self.assertIsNotNone(created.joined_at)

    def test_join_waitlist_post_rejects_institution_for_non_student(self):
        payload = {
            "f_name": "Seun",
            "l_name": "Kay",
            "email": "seun@example.com",
            "phone": "2348033333333",
            "is_student": False,
            "institution": "Some School",
        }

        response = self.client.post(self.join_url, data=payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["status"], "fail")

    def test_waitlist_dashboard_requires_email(self):
        response = self.client.get(self.dashboard_url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["status"], "fail")

    def test_waitlist_dashboard_returns_user_details(self):
        user = self._create_waitlist_user(idx=2, email="dash@example.com", points=55)

        response = self.client.get(self.dashboard_url, {"email": user.email})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "success")
        self.assertEqual(response.data["data"]["email"], user.email)
        self.assertEqual(response.data["data"]["points"], user.points)

    def test_public_waitlist_list_returns_joined_at(self):
        self._create_waitlist_user(idx=3, points=20)
        self._create_waitlist_user(idx=4, points=50)

        response = self.client.get(self.public_list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("results", response.data)
        self.assertIn("remaining_slots", response.data)
        first_item = response.data["results"][0]
        self.assertIn("joined_at", first_item)
        self.assertEqual(first_item["points"], 50)

    def test_admin_waitlist_list_requires_authentication(self):
        self._create_waitlist_user(idx=5, points=40)

        response = self.client.get(self.admin_list_url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_admin_waitlist_list_returns_encrypted_payload_for_superadmin(self):
        self._create_waitlist_user(idx=6, points=10)
        self._create_waitlist_user(idx=7, points=90)
        admin = self._create_admin_user(active_role="SuperAdmin")
        self.client.force_authenticate(user=admin)

        response = self.client.get(self.admin_list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsInstance(response.data, str)

        decrypted = decrypt(response.data)
        self.assertIn("results", decrypted)
        self.assertIn("remaining_slots", decrypted)
        first = decrypted["results"][0]
        self.assertIn("joined_at", first)
        self.assertIsInstance(first["joined_at"], str)
