from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth.hashers import make_password
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import AccountType, User
from support.models import Ticket


def _create_user(**overrides):
    seed = uuid4().hex[:8]
    data = {
        "phone_number": f"23482{seed[:7]}",
        "password": "StrongPass123!",
        "first_name": "Support",
        "last_name": "User",
        "email": f"support.{seed}@example.com",
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


class TicketModelBehaviorTests(TestCase):
    def test_ticket_number_is_generated_on_first_save(self):
        user = _create_user()
        ticket = Ticket.objects.create(
            user=user,
            title="Issue",
            category="General",
            channel="Email",
            description="Need help",
            priority="Low",
            status="New",
        )

        self.assertIsNotNone(ticket.number)
        self.assertTrue(ticket.number.startswith("TCK-"))

    def test_remaining_time_is_none_without_opened_at(self):
        user = _create_user()
        ticket = Ticket.objects.create(
            user=user,
            title="Issue",
            category="General",
            channel="Email",
            description="Need help",
            priority="Low",
            status="New",
            resolution_hours=6,
        )
        self.assertIsNone(ticket.remaining_time)

    def test_remaining_time_counts_down_from_opened_at(self):
        user = _create_user()
        ticket = Ticket.objects.create(
            user=user,
            title="Issue",
            category="General",
            channel="Email",
            description="Need help",
            priority="Low",
            status="In-Progress",
            resolution_hours=4,
            opened_at=timezone.now() - timedelta(hours=1),
        )

        remaining = ticket.remaining_time
        self.assertIsNotNone(remaining)
        self.assertGreater(remaining, timedelta(hours=2))


class SupportEndpointBehaviorTests(APITestCase):
    def setUp(self):
        self.manager = _create_user(active_role="Manager")
        self.manager.agent_pin = make_password("12345")
        self.manager.save(update_fields=["agent_pin"])

        self.customer = _create_user(active_role="Member")
        self.create_ticket_url = "/v1/support/create"

    def _ticket_payload(self, **overrides):
        data = {
            "email": self.customer.email,
            "pin": "12345",
            "customer_name": "Jane Doe",
            "customer_email": self.customer.email,
            "customer_phone_number": self.customer.phone_number,
            "title": "Unable to complete transfer",
            "priority": "Low",
            "resolution_hours": 6,
            "category": "Payments",
            "channel": "Email",
            "description": "Transfer keeps failing with timeout.",
        }
        data.update(overrides)
        return data

    def test_create_ticket_requires_authentication(self):
        response = self.client.post(self.create_ticket_url, data={})
        self.assertIn(response.status_code, [401, 403])

    def test_create_ticket_rejects_non_support_roles(self):
        member = _create_user(active_role="Member")
        self.client.force_authenticate(user=member)

        response = self.client.post(
            self.create_ticket_url,
            data=self._ticket_payload(),
        )

        self.assertIn(response.status_code, [400, 403])

    def test_create_ticket_rejects_incorrect_pin(self):
        self.client.force_authenticate(user=self.manager)

        response = self.client.post(
            self.create_ticket_url,
            data=self._ticket_payload(pin="99999"),
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data["status"], "fail")
        self.assertEqual(response.data["message"], "Incorrect pin")
        self.assertEqual(Ticket.objects.count(), 0)

    def test_create_ticket_returns_404_for_unknown_customer_email(self):
        self.client.force_authenticate(user=self.manager)

        response = self.client.post(
            self.create_ticket_url,
            data=self._ticket_payload(email="unknown@example.com"),
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("User not found", str(response.data))
        self.assertEqual(Ticket.objects.count(), 0)

    def test_create_ticket_success_creates_ticket_number(self):
        self.client.force_authenticate(user=self.manager)

        response = self.client.post(
            self.create_ticket_url,
            data=self._ticket_payload(),
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], "success")
        ticket = Ticket.objects.get(customer_email=self.customer.email)
        self.assertTrue(ticket.number)
        self.assertTrue(ticket.number.startswith("TCK"))

    def test_get_all_support_tickets_returns_created_ticket(self):
        ticket = Ticket.objects.create(
            user=self.customer,
            title="Issue",
            category="General",
            channel="Email",
            description="Need help",
            priority="Low",
            status="New",
        )

        self.client.force_authenticate(user=self.manager)
        response = self.client.get("/v1/support/get-all")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "success")
        ticket_numbers = [item["ticket_number"] for item in response.data["data"]]
        self.assertIn(ticket.number, ticket_numbers)

    def test_get_single_ticket_sets_opened_at_on_first_view(self):
        ticket = Ticket.objects.create(
            user=self.customer,
            title="Issue",
            category="General",
            channel="Email",
            description="Need help",
            resolution_hours=6,
            priority="Low",
            status="New",
        )
        ticket.number = "TCK-TEST-001"
        ticket.save(update_fields=["number"])
        self.assertIsNone(ticket.opened_at)

        self.client.force_authenticate(user=self.manager)
        response = self.client.get(f"/v1/support/get-single-ticket/{ticket.number}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "success")
        ticket.refresh_from_db()
        self.assertIsNotNone(ticket.opened_at)


class SupportForgotPasswordBehaviorTests(APITestCase):
    def test_returns_generic_success_for_unknown_email(self):
        response = self.client.post(
            "/v1/support/support-forgot-password",
            data={"email": "missing-user@example.com"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "success")

    def test_rejects_non_staff_account_for_password_reset(self):
        member = _create_user(active_role="Member")

        response = self.client.post(
            "/v1/support/support-forgot-password",
            data={"email": member.email},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["status"], "fail")

    def test_accepts_manager_account_for_password_reset(self):
        manager = _create_user(active_role="Manager")
        AccountType.objects.create(user=manager, user_type="Manager")

        with patch("support.views.otp_manager.create_otp", return_value="123456"):
            with patch("support.views.Messaging.send_email", return_value=None):
                response = self.client.post(
                    "/v1/support/support-forgot-password",
                    data={"email": manager.email},
                    format="json",
                )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], "success")
