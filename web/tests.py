from rest_framework import status
from rest_framework.test import APITestCase

from web.models import NewsletterSubscribers


class NewsletterAndContactBehaviorTests(APITestCase):
    def test_newsletter_rejects_missing_email(self):
        response = self.client.post(
            "/v1/web/newsletter/subscribe/",
            data={},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["status"], "fail")
        self.assertIn("Email is required", response.data["message"])

    def test_newsletter_subscribe_and_prevent_duplicate(self):
        email = "newsletter.behavior@example.com"

        first = self.client.post(
            "/v1/web/newsletter/subscribe/",
            data={"email": email},
            format="json",
        )
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(first.data["status"], "success")
        self.assertTrue(NewsletterSubscribers.objects.filter(email=email).exists())

        second = self.client.post(
            "/v1/web/newsletter/subscribe/",
            data={"email": email},
            format="json",
        )
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(second.data["status"], "fail")
        self.assertIn("already subscribed", second.data["message"])

    def test_newsletter_unsubscribe_rejects_invalid_token(self):
        response = self.client.post(
            "/v1/web/newsletter/unsubscribe/",
            data={"token": "invalid-token"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["status"], "fail")

    def test_contact_us_requires_accept_policy(self):
        payload = {
            "contact_type": "Personal Use",
            "first_name": "John",
            "last_name": "Doe",
            "product_of_interest": "Brand Advertisement",
            "channel": {"type": "Email", "value": "john@example.com"},
            "message": "I would like more information.",
            "accept_policy": False,
        }

        response = self.client.post("/v1/web/contact-us", data=payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("accept_policy", response.data)
