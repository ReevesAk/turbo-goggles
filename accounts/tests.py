# from rest_framework.test import APITestCase, APIRequestFactory
# from rest_framework import status
# from .views import Register
#
# from django.urls import reverse
#
#
# class CreateAccountTestCase(APITestCase):
#     def setUp(self):
#         self.factory = APIRequestFactory()
#         self.view = Register.as_view()
#         self.url = reverse('register')
#
#     def test_account_creation(self):
#         request = self.factory.get(path=self.url)
#
#         response = self.view(request)
#
#         self.assertEqual(response.status_code, status.HTTP_201_CREATED)
