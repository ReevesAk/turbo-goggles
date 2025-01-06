from django.test import TestCase
from django.utils.timezone import now
from decimal import Decimal
from .models import User
from unittest.mock import patch, MagicMock
from rest_framework.test import APIClient
from rest_framework import status
from .models import AccountType
from roles.models import ActivityModel


class UserModelTest(TestCase):
    def setUp(self):
        self.user_data = {
            "first_name": "John",
            "last_name": "Doe",
            "phone_number": "+1234567890",
            "email": "john.doe@example.com",
            "country": "USA",
            "state": "California",
            "city": "Los Angeles",
            "password": "securepassword",
        }

    def test_user_creation(self):
        """Test that a user can be created successfully."""
        user = User.objects.create(**self.user_data)
        self.assertEqual(user.first_name, "John")
        self.assertEqual(user.last_name, "Doe")
        self.assertEqual(user.phone_number, "+1234567890")
        self.assertEqual(user.email, "john.doe@example.com")
        self.assertEqual(user.country, "USA")
        self.assertFalse(user.is_bvn_verified)
        self.assertEqual(user.welcome_bonus, Decimal("0.00"))
        self.assertTrue(user.is_active)

    def test_default_values(self):
        """Test the default values for boolean and other fields."""
        user = User.objects.create(**self.user_data)
        self.assertFalse(user.is_bvn_verified)
        self.assertFalse(user.has_wallet)
        self.assertFalse(user.is_verified)
        self.assertFalse(user.done_survey)
        self.assertFalse(user.has_bonus)
        self.assertFalse(user.has_card)
        self.assertFalse(user.has_promoted)
        self.assertIsNone(user.last_login)
        self.assertIsNone(user.admin_pin)

    def test_string_representation(self):
        """Test the string representation of the user model."""
        user = User.objects.create(**self.user_data)
        self.assertEqual(str(user), user.phone_number)

    def test_user_creation_without_optional_fields(self):
        """Test user creation with only required fields."""
        minimal_user_data = {
            "phone_number": "+1234567890",
            "email": "minimal@example.com",
            "country": "USA",
            "state": "California",
            "city": "Los Angeles",
        }
        user = User.objects.create(**minimal_user_data)
        self.assertEqual(user.phone_number, "+1234567890")
        self.assertEqual(user.email, "minimal@example.com")

    def test_active_role_field(self):
        """Test that the active_role field can be set and retrieved."""
        user = User.objects.create(**self.user_data, active_role="Admin")
        self.assertEqual(user.active_role, "Admin")

    def test_last_login_field(self):
        """Test that the last_login field can be set and updated."""
        user = User.objects.create(**self.user_data)
        login_time = now()
        user.last_login = login_time
        user.save()
        self.assertEqual(user.last_login, login_time)

    def test_unique_phone_number(self):
        """Test that the phone_number field must be unique."""
        User.objects.create(**self.user_data)
        with self.assertRaises(Exception):
            User.objects.create(**self.user_data)

    def test_email_is_unique(self):
        """Test that the email field must be unique."""
        User.objects.create(**self.user_data)
        duplicate_data = self.user_data.copy()
        duplicate_data["phone_number"] = "+9876543210"  # Change phone_number to avoid collision
        with self.assertRaises(Exception):
            User.objects.create(**duplicate_data)
