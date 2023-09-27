from django.urls import reverse

from rest_framework.test import APITestCase


# Create your tests here.
# Create your tests here.
class TestSetup(APITestCase):
    def setUp(self):
        self.create_url = reverse("create-virtual-account")

        self.user_data = {
            "first_name": "Fincra",
            "last_name": "Developer",
            "bvn": "01234567891",
            "currency": "NGN",
            "accountType": "individual",
            "channel": "providus",
        }

        return super().setUp

    def tearDown(self):
        return super().tearDown


class TestViews(TestSetup):
    def test_user_can_create(self):
        res = self.client.post(self.create_url, self.user_data, format="json")
        self.assertEqual(res.status_code, 201)
