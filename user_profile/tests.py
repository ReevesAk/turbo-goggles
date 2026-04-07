import json as _json

from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from security import decrypt, encrypt


def _make_payload(**kwargs):
    return _json.dumps(encrypt(kwargs))


def _create_user(**overrides):
    data = {
        "phone_number": "2349011111111",
        "password": "StrongPass123!",
        "first_name": "Profile",
        "last_name": "User",
        "email": "profile.user@example.com",
        "country": "NG",
        "state": "Lagos",
        "city": "Ikeja",
        "is_verified": True,
        "active_role": "Member",
        "alert_type_choice": "Both",
    }
    data.update(overrides)
    password = data.pop("password")
    user = User.objects.create(**data)
    user.set_password(password)
    user.save()
    return user


class ChooseAlertTypeViewTests(APITestCase):
    url = "/v1/user_profile/alert-type"

    def setUp(self):
        self.user = _create_user()

    def test_requires_authentication(self):
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_rejects_empty_alert_choice(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            self.url,
            data=_make_payload(),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = decrypt(response.data)
        self.assertEqual(body["status"], "fail")
        self.assertIn("cannot be empty", body["message"])

    def test_rejects_invalid_alert_choice(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            self.url,
            data=_make_payload(alert_type_choice="PUSH"),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = (
            response.data if isinstance(response.data, dict) else decrypt(response.data)
        )
        self.assertIn("alert_type_choice", body)

    def test_updates_alert_choice_for_valid_values(self):
        self.client.force_authenticate(user=self.user)

        for choice in ["SMS", "Email", "Both"]:
            response = self.client.post(
                self.url,
                data=_make_payload(alert_type_choice=choice),
                content_type="application/json",
            )

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            body = decrypt(response.data)
            self.assertEqual(body["status"], "success")
            self.assertEqual(body["data"]["alert choice"], choice)
            self.user.refresh_from_db()
            self.assertEqual(self.user.alert_type_choice, choice)


class UserProfileAuthSmokeTests(APITestCase):
    def test_get_user_profile_requires_auth(self):
        response = self.client.get("/v1/user_profile/get-user-profile")
        self.assertIn(response.status_code, [401, 403])

    def test_change_password_requires_auth(self):
        response = self.client.post("/v1/user_profile/change-password")
        self.assertIn(response.status_code, [401, 403])
