from django.urls import reverse

from rest_framework.test import APITestCase


# Create your tests here.
class TestSetup(APITestCase):
    def setUp(self):
        self.register_url = reverse("register-partners")

        self.user_data = {
            "first_name": "partner",
            "last_name": "user",
            "account_type": "Partner",
            "country": "Nigeria",
            "state": "Rivers",
            "city": "Port Harcourt",
            "phone_number": "924824414143",
            "business_name": "bus_name",
            "business_category": "924824414143",
            "website": "website.com",
            "email": "old@gmail.com",
            "password": "password",
        }

        return super().setUp

    def tearDown(self):
        return super().tearDown


class TestViews(TestSetup):
    def test_user_can_register(self):
        res = self.client.post(self.register_url, self.user_data, format="json")
        self.assertEqual(res.status_code, 201)
