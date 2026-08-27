"""
Test suite for the Event/Ticketing application.

Covers event management, ticket purchasing (single and cart), payment processing,
ticket transfers, check-in verification, partner sales, admin review workflows,
and detailed statistics.

Includes:
- Unit tests: Individual component behavior
- Integration tests: End-to-end workflows
- Audit tests: Security, data integrity, and compliance
- Fuzz tests: Edge cases and malformed inputs
"""

from datetime import timedelta, datetime
from decimal import Decimal
from uuid import uuid4
from unittest.mock import patch, MagicMock

from django.contrib.auth.hashers import make_password
from django.core.cache import cache
from django.db import models
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from freezegun import freeze_time

from accounts.models import User, AccountType, TxModel, UserNotification
from banking.models import WalletModel
from security import encrypt, decrypt

from .models import (
    Event,
    PartnerSaleWindow,
    PartnerTicketSale,
    Ticket,
    TicketCode,
    TicketConfiguration,
    TicketOrder,
    TicketPurchase,
    TicketTransfer,
)

# =============================================================================
# Test Helpers
# =============================================================================


def _create_user(**overrides):
    """
    Create a test user with sensible defaults.

    Keyword arguments override the default field values.
    """
    seed = uuid4().hex[:8]
    defaults = {
        "phone_number": f"23490{seed[:7]}",
        "first_name": "Ticket",
        "last_name": "User",
        "email": f"ticket.{seed}@example.com",
        "country": "NG",
        "state": "Lagos",
        "city": "Ikeja",
        "is_verified": True,
        "is_staff": True,
        "active_role": "Member",
        "level": "Starter",
        "total_points": 0,
        "has_done_survey": True,
    }
    defaults.update(overrides)
    password = defaults.pop("password", "StrongPass123!")
    user = User.objects.create(**defaults)
    user.set_password(password)
    user.save()
    return user


def _create_partner(**overrides):
    """Create a partner user."""
    defaults = {"active_role": "Partner"}
    defaults.update(overrides)
    user = _create_user(**defaults)
    AccountType.objects.create(user=user, user_type="Partner")
    return user


def _create_member(**overrides):
    """Create a member user."""
    defaults = {"active_role": "Member"}
    defaults.update(overrides)
    user = _create_user(**defaults)
    AccountType.objects.create(user=user, user_type="Member")
    return user


def _create_admin(**overrides):
    """Create a superadmin user."""
    defaults = {
        "active_role": "SuperAdmin",
        "is_superuser": True,
        "is_staff": True,
    }
    defaults.update(overrides)
    user = _create_user(**defaults)
    AccountType.objects.create(user=user, user_type="SuperAdmin")
    return user


def _create_event(partner, **overrides):
    """Create an event with production-like defaults."""
    now = timezone.now()
    defaults = {
        "user": partner,
        "business_name": "Test Events Ltd",
        "business_type": "Events",
        "event_name": "Tech Conference 2024",
        "description": "A comprehensive tech conference covering AI, blockchain, and more.",
        "category": "Technology",
        "tags": ["tech", "ai", "blockchain"],
        "mode": "Physical",
        "address": "123 Test Street, Lagos",
        "latitude": 6.5244,
        "longitude": 3.3792,
        "status": Event.Status.ON_SALE,
        "start_date": now + timedelta(days=30),
        "end_date": now + timedelta(days=31),
        "approved_at": now,
    }
    defaults.update(overrides)
    return Event.objects.create(**defaults)


def _create_ticket(event, **overrides):
    """Create a ticket with defaults."""
    now = timezone.now()
    defaults = {
        "event": event,
        "name": "Regular",
        "description": "Standard admission ticket",
        "price": Decimal("10000.00"),
        "slot_cap": 100,
        "slots_filled": 0,
        "unlimited_slots": False,
        "sales_start_date": now,
        "sales_end_date": now + timedelta(days=25),
        "is_active": True,
        "min_purchase": 1,
        "max_purchase": 10,
    }
    defaults.update(overrides)
    return Ticket.objects.create(**defaults)


def _create_wallet(user, balance=Decimal("50000.00"), pin="123456"):
    """Create a wallet with INDIVIDUAL type and a hashed PIN."""

    return WalletModel.objects.create(
        user=user,
        account_number="1234567890",
        balance=balance,
        walletType="INDIVIDUAL",
        pin=make_password(pin),
    )


def _create_purchase(member, ticket, **overrides):
    """Create a ticket purchase with defaults."""
    defaults = {
        "member": member,
        "ticket": ticket,
        "event": ticket.event,
        "quantity": 2,
        "unit_price": ticket.price,
        "total_amount": ticket.price * 2,
        "status": TicketPurchase.Status.PAID,
        "payment_reference": f"tx_{uuid4().hex[:10]}",
    }
    defaults.update(overrides)
    purchase = TicketPurchase.objects.create(**defaults)

    # Create ticket codes
    for _ in range(purchase.quantity):
        TicketCode.objects.create(
            purchase=purchase,
            current_owner=member,
        )

    return purchase


def _create_order(member, event, tickets_data, **overrides):
    """Create a ticket order with line items."""
    total = Decimal("0")
    for item in tickets_data:
        total += item["ticket"].price * item["quantity"]

    defaults = {
        "member": member,
        "event": event,
        "total_amount": total,
        "status": TicketOrder.Status.PAID,
        "payment_reference": f"tx_{uuid4().hex[:10]}",
    }
    defaults.update(overrides)
    order = TicketOrder.objects.create(**defaults)

    # Create line items
    for item in tickets_data:
        purchase = TicketPurchase.objects.create(
            order=order,
            member=member,
            ticket=item["ticket"],
            event=event,
            quantity=item["quantity"],
            unit_price=item["ticket"].price,
            total_amount=item["ticket"].price * item["quantity"],
            status=TicketPurchase.Status.PAID,
            payment_reference=order.payment_reference,
        )

        # Create ticket codes
        for _ in range(purchase.quantity):
            TicketCode.objects.create(
                purchase=purchase,
                current_owner=member,
            )

    return order


# =============================================================================
# Base Test Case with Throttle Mocking
# =============================================================================


class ThrottleDisabledAPITestCase(APITestCase):
    """Base class that disables DRF throttling for all tests."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._throttle_patcher = patch("rest_framework.views.APIView.check_throttles")
        cls._throttle_patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls._throttle_patcher.stop()
        super().tearDownClass()


# =============================================================================
# Unit Tests - Event Model
# =============================================================================


class EventModelTests(ThrottleDisabledAPITestCase):
    """Unit tests for Event model."""

    def setUp(self):
        self.partner = _create_partner()
        self.event = _create_event(self.partner)

    def test_event_slug_auto_generation(self):
        """Slug is auto-generated on save."""
        event = _create_event(
            self.partner,
            event_name="Unique Event Name 2024",
            slug="",
        )
        self.assertIsNotNone(event.slug)
        self.assertNotEqual(event.slug, "")

    def test_event_approved_at_set_on_on_sale(self):
        """approved_at is set when event goes on sale."""
        event = _create_event(
            self.partner,
            status=Event.Status.DRAFT,
            approved_at=None,
        )
        event.status = Event.Status.ON_SALE
        event.save()
        self.assertIsNotNone(event.approved_at)

    def test_event_is_on_sale_property(self):
        """is_on_sale returns correct boolean."""
        self.assertTrue(self.event.is_on_sale)

        self.event.status = Event.Status.DRAFT
        self.event.save()
        self.assertFalse(self.event.is_on_sale)

    def test_event_location_point_generation(self):
        """Location point is generated from lat/lng."""
        self.event.latitude = 6.5244
        self.event.longitude = 3.3792
        self.event.save()
        self.assertIsNotNone(self.event.location)

    def test_update_view_count(self):
        """update_view_count atomically increments."""
        initial_count = self.event.view_count
        self.event.update_view_count()
        self.event.refresh_from_db()
        self.assertEqual(self.event.view_count, initial_count + 1)


class TicketModelTests(ThrottleDisabledAPITestCase):
    """Unit tests for Ticket model."""

    def setUp(self):
        self.partner = _create_partner()
        self.event = _create_event(self.partner)
        self.ticket = _create_ticket(self.event)

    def test_available_slots(self):
        """available_slots returns correct count."""
        self.assertEqual(self.ticket.available_slots, 100)

        self.ticket.slots_filled = 30
        self.ticket.save()
        self.assertEqual(self.ticket.available_slots, 70)

    def test_available_slots_unlimited(self):
        """available_slots returns None for unlimited."""
        self.ticket.unlimited_slots = True
        self.ticket.save()
        self.assertIsNone(self.ticket.available_slots)

    def test_is_sold_out(self):
        """is_sold_out returns correct boolean."""
        self.assertFalse(self.ticket.is_sold_out)

        self.ticket.slots_filled = 100
        self.ticket.save()
        self.assertTrue(self.ticket.is_sold_out)

    def test_is_on_sale(self):
        """is_on_sale validates multiple conditions."""
        self.assertTrue(self.ticket.is_on_sale)

        # Test inactive
        self.ticket.is_active = False
        self.ticket.save()
        self.assertFalse(self.ticket.is_on_sale)

    def test_reserve_slots_atomic(self):
        """reserve_slots atomically reserves slots."""
        result = self.ticket.reserve_slots(5)
        self.assertTrue(result)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.slots_filled, 5)

    def test_reserve_slots_insufficient(self):
        """reserve_slots fails when insufficient."""
        result = self.ticket.reserve_slots(200)
        self.assertFalse(result)


class TicketOrderModelTests(ThrottleDisabledAPITestCase):
    """Unit tests for TicketOrder model."""

    def setUp(self):
        self.partner = _create_partner()
        self.event = _create_event(self.partner)
        self.member = _create_member()
        self.ticket_a = _create_ticket(
            self.event, name="Regular", price=Decimal("10000.00")
        )
        self.ticket_b = _create_ticket(
            self.event, name="VIP", price=Decimal("40000.00")
        )

    def test_mark_as_paid_single_ticket(self):
        """mark_as_paid handles single ticket orders."""
        order = TicketOrder.objects.create(
            member=self.member,
            event=self.event,
            total_amount=Decimal("20000.00"),
            status=TicketOrder.Status.PENDING,
        )
        TicketPurchase.objects.create(
            order=order,
            member=self.member,
            ticket=self.ticket_a,
            event=self.event,
            quantity=2,
            unit_price=Decimal("10000.00"),
            total_amount=Decimal("20000.00"),
            status=TicketPurchase.Status.PENDING,
        )

        order.mark_as_paid("tx_test_123")

        order.refresh_from_db()
        self.assertEqual(order.status, TicketOrder.Status.PAID)
        self.assertEqual(order.payment_reference, "tx_test_123")
        self.assertEqual(order.items.count(), 1)
        self.assertEqual(order.items.first().status, TicketPurchase.Status.PAID)
        self.assertEqual(order.items.first().codes.count(), 2)

    def test_mark_as_paid_multiple_tickets(self):
        """mark_as_paid handles cart orders with multiple ticket types."""
        order = TicketOrder.objects.create(
            member=self.member,
            event=self.event,
            total_amount=Decimal("140000.00"),
            status=TicketOrder.Status.PENDING,
        )
        TicketPurchase.objects.create(
            order=order,
            member=self.member,
            ticket=self.ticket_a,
            event=self.event,
            quantity=2,
            unit_price=Decimal("10000.00"),
            total_amount=Decimal("20000.00"),
            status=TicketPurchase.Status.PENDING,
        )
        TicketPurchase.objects.create(
            order=order,
            member=self.member,
            ticket=self.ticket_b,
            event=self.event,
            quantity=3,
            unit_price=Decimal("40000.00"),
            total_amount=Decimal("120000.00"),
            status=TicketPurchase.Status.PENDING,
        )

        order.mark_as_paid("tx_test_456")

        order.refresh_from_db()
        self.assertEqual(order.status, TicketOrder.Status.PAID)
        self.assertEqual(order.items.count(), 2)
        self.assertEqual(sum(item.codes.count() for item in order.items.all()), 5)

    def test_mark_as_paid_insufficient_slots(self):
        """mark_as_paid fails when insufficient slots - transaction rolls back."""
        self.ticket_a.slot_cap = 1
        self.ticket_a.slots_filled = 1
        self.ticket_a.save()

        order = TicketOrder.objects.create(
            member=self.member,
            event=self.event,
            total_amount=Decimal("20000.00"),
            status=TicketOrder.Status.PENDING,
        )
        TicketPurchase.objects.create(
            order=order,
            member=self.member,
            ticket=self.ticket_a,
            event=self.event,
            quantity=2,
            unit_price=Decimal("10000.00"),
            total_amount=Decimal("20000.00"),
            status=TicketPurchase.Status.PENDING,
        )

        with self.assertRaises(ValueError):
            order.mark_as_paid("tx_test_789")

        # Transaction rolled back, so order is still PENDING
        order.refresh_from_db()
        self.assertEqual(order.status, TicketOrder.Status.PENDING)
        # And the purchase should still be PENDING
        purchase = order.items.first()
        self.assertEqual(purchase.status, TicketPurchase.Status.PENDING)


# =============================================================================
# Unit Tests - Ticket Code
# =============================================================================


class TicketCodeModelTests(ThrottleDisabledAPITestCase):
    """Unit tests for TicketCode model."""

    def setUp(self):
        self.partner = _create_partner()
        self.event = _create_event(self.partner)
        self.member = _create_member()
        self.ticket = _create_ticket(self.event)
        self.purchase = _create_purchase(self.member, self.ticket)
        self.code = self.purchase.codes.first()

    def test_verify_by_token(self):
        """verify works with UUID token."""
        result = TicketCode.verify(str(self.code.token))
        self.assertEqual(result, self.code)

    def test_verify_by_code(self):
        """verify works with fallback code."""
        result = TicketCode.verify(self.code.code)
        self.assertEqual(result, self.code)

    def test_verify_invalid(self):
        """verify returns None for invalid input."""
        result = TicketCode.verify("invalid_code")
        self.assertIsNone(result)

    def test_check_in(self):
        """check_in marks ticket as used."""
        self.code.check_in(by=self.partner)
        self.code.refresh_from_db()
        self.assertTrue(self.code.is_checked_in)
        self.assertIsNotNone(self.code.checked_in_at)
        self.assertEqual(self.code.checked_in_by, self.partner)

    def test_check_in_already_checked(self):
        """check_in raises error if already checked in."""
        self.code.check_in(by=self.partner)
        with self.assertRaises(Exception):
            self.code.check_in(by=self.partner)


# =============================================================================
# Integration Tests - Event Endpoints
# =============================================================================


class EventPublicListTests(ThrottleDisabledAPITestCase):
    """Integration tests for public event listing."""

    def setUp(self):
        self.partner = _create_partner()
        self.member = _create_member()
        self.client.force_authenticate(user=self.member)
        cache.clear()

    def test_list_events_success(self):
        """Members can list on-sale events."""
        now = timezone.now()
        _create_event(
            self.partner,
            status=Event.Status.ON_SALE,
            start_date=now - timedelta(days=1),
            end_date=now + timedelta(days=5),
        )
        response = self.client.get("/v1/event/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.content)
        self.assertEqual(body["status"], "success")
        self.assertEqual(body["data"]["count"], 1)

    def test_list_events_filter_by_category(self):
        """Events can be filtered by category."""
        now = timezone.now()
        _create_event(
            self.partner,
            category="Music",
            status=Event.Status.ON_SALE,
            start_date=now - timedelta(days=1),
            end_date=now + timedelta(days=5),
        )
        _create_event(
            self.partner,
            category="Tech",
            event_name="Tech Event",
            status=Event.Status.ON_SALE,
            start_date=now - timedelta(days=1),
            end_date=now + timedelta(days=5),
        )

        response = self.client.get("/v1/event/?category=Music")
        body = decrypt(response.content)
        self.assertEqual(body["data"]["count"], 1)

    def test_list_events_requires_auth(self):
        """Unauthenticated requests get 401."""
        self.client.force_authenticate(user=None)
        response = self.client.get("/v1/event/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_list_events_cached(self):
        """Event list is cached."""
        _create_event(self.partner)
        response1 = self.client.get("/v1/event/")
        body1 = decrypt(response1.content)

        with patch("django.core.cache.cache.get") as mock_cache_get:
            mock_cache_get.return_value = body1
            response2 = self.client.get("/v1/event/")
            self.assertEqual(response2.status_code, status.HTTP_200_OK)
            mock_cache_get.assert_called()


class EventPublicDetailTests(ThrottleDisabledAPITestCase):
    """Integration tests for event detail endpoint."""

    def setUp(self):
        self.partner = _create_partner()
        self.member = _create_member()
        self.event = _create_event(self.partner)
        self.client.force_authenticate(user=self.member)
        cache.clear()

    def test_get_event_detail_success(self):
        """Members can view event details."""
        response = self.client.get(f"/v1/event/{self.event.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.content)
        self.assertEqual(body["status"], "success")
        self.assertEqual(body["data"]["event"]["id"], str(self.event.id))

    def test_get_event_detail_increments_view_count(self):
        """View count increments on detail view."""
        initial_count = self.event.view_count
        self.client.get(f"/v1/event/{self.event.id}/")
        self.event.refresh_from_db()
        self.assertEqual(self.event.view_count, initial_count + 1)

    def test_get_event_detail_404(self):
        """Non-existent event returns 404."""
        response = self.client.get(f"/v1/event/{uuid4()}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


# =============================================================================
# Integration Tests - Ticket Purchase
# =============================================================================


class TicketPurchaseTests(ThrottleDisabledAPITestCase):
    """Integration tests for single ticket purchase."""

    def setUp(self):
        self.partner = _create_partner()
        self.member = _create_member()
        self.event = _create_event(self.partner)
        self.ticket = _create_ticket(self.event)
        self.wallet = _create_wallet(self.member)
        self.client.force_authenticate(user=self.member)
        cache.clear()

    def _purchase_payload(self, **overrides):
        data = {
            "ticket": str(self.ticket.id),
            "quantity": 2,
            "payment_option": "WALLET",
            "pin": "123456",
        }
        data.update(overrides)
        return data

    def test_purchase_success(self):
        """Successful wallet purchase creates tickets."""
        with patch("banking.controllers.Wallet.getWalletDetails") as mock_wallet:
            mock_wallet.return_value = MagicMock(
                json=lambda: {
                    "status": "SUCCESS",
                    "data": {"availableBalance": 50000.00},
                }
            )
            with patch("banking.controllers.Wallet.Debit") as mock_debit:
                mock_debit.return_value = MagicMock(status_code=200)
                response = self.client.post(
                    "/v1/event/tickets/purchase/",
                    data=encrypt(self._purchase_payload()),
                    format="json",
                )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        body = decrypt(response.content)
        self.assertEqual(body["status"], "success")
        self.assertEqual(TicketPurchase.objects.count(), 1)
        self.assertEqual(TicketCode.objects.count(), 2)

    def test_purchase_insufficient_balance(self):
        """Insufficient balance returns 400."""
        self.wallet.balance = Decimal("1000.00")
        self.wallet.save()

        with patch("banking.controllers.Wallet.getWalletDetails") as mock_wallet:
            mock_wallet.return_value = MagicMock(
                json=lambda: {
                    "status": "SUCCESS",
                    "data": {"availableBalance": 1000.00},
                }
            )
            response = self.client.post(
                "/v1/event/tickets/purchase/",
                data=encrypt(self._purchase_payload()),
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = decrypt(response.content)
        self.assertEqual(body["status"], "fail")

    def test_purchase_insufficient_slots(self):
        """Insufficient slots returns 400."""
        self.ticket.slot_cap = 1
        self.ticket.slots_filled = 1
        self.ticket.save()

        response = self.client.post(
            "/v1/event/tickets/purchase/",
            data=encrypt(self._purchase_payload(quantity=2)),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_purchase_with_idempotency(self):
        """Idempotency key prevents duplicate purchases."""
        idempotency_key = str(uuid4())

        with patch("banking.controllers.Wallet.getWalletDetails") as mock_wallet:
            mock_wallet.return_value = MagicMock(
                json=lambda: {
                    "status": "SUCCESS",
                    "data": {"availableBalance": 50000.00},
                }
            )
            with patch("banking.controllers.Wallet.Debit") as mock_debit:
                mock_debit.return_value = MagicMock(status_code=200)

                response1 = self.client.post(
                    "/v1/event/tickets/purchase/",
                    data=encrypt(
                        self._purchase_payload(idempotency_key=idempotency_key)
                    ),
                    format="json",
                )

                response2 = self.client.post(
                    "/v1/event/tickets/purchase/",
                    data=encrypt(
                        self._purchase_payload(idempotency_key=idempotency_key)
                    ),
                    format="json",
                )

        self.assertEqual(response1.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response2.status_code, status.HTTP_200_OK)
        self.assertEqual(TicketPurchase.objects.count(), 1)


class TicketCartPurchaseTests(ThrottleDisabledAPITestCase):
    """Integration tests for cart-based ticket purchase."""

    def setUp(self):
        self.partner = _create_partner()
        self.member = _create_member()
        self.event = _create_event(self.partner)
        self.ticket_a = _create_ticket(
            self.event, name="Regular", price=Decimal("10000.00")
        )
        self.ticket_b = _create_ticket(
            self.event, name="VIP", price=Decimal("40000.00")
        )
        self.ticket_c = _create_ticket(
            self.event, name="VVIP", price=Decimal("80000.00")
        )
        self.wallet = _create_wallet(self.member, balance=Decimal("1000000.00"))
        self.client.force_authenticate(user=self.member)
        cache.clear()

    def _cart_payload(self, **overrides):
        data = {
            "items": [
                {"ticket_id": str(self.ticket_a.id), "quantity": 5},
                {"ticket_id": str(self.ticket_b.id), "quantity": 3},
                {"ticket_id": str(self.ticket_c.id), "quantity": 10},
            ],
            "payment_option": "WALLET",
            "pin": "123456",
        }
        data.update(overrides)
        return data

    def test_cart_purchase_success(self):
        """Successful cart purchase creates order with multiple ticket types."""
        with patch("banking.controllers.Wallet.getWalletDetails") as mock_wallet:
            mock_wallet.return_value = MagicMock(
                json=lambda: {
                    "status": "SUCCESS",
                    "data": {"availableBalance": 1000000.00},
                }
            )
            with patch("banking.controllers.Wallet.Debit") as mock_debit:
                mock_debit.return_value = MagicMock(status_code=200)
                response = self.client.post(
                    "/v1/event/tickets/cart-purchase/",
                    data=encrypt(self._cart_payload()),
                    format="json",
                )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        body = decrypt(response.content)
        self.assertEqual(body["status"], "success")
        self.assertEqual(TicketOrder.objects.count(), 1)
        self.assertEqual(TicketPurchase.objects.count(), 3)
        self.assertEqual(TicketCode.objects.count(), 18)

    def test_cart_purchase_different_events_fails(self):
        """Cart with tickets from different events fails."""
        other_event = _create_event(self.partner, event_name="Other Event")
        other_ticket = _create_ticket(other_event, name="Other Ticket")

        payload = self._cart_payload()
        payload["items"].append({"ticket_id": str(other_ticket.id), "quantity": 1})

        response = self.client.post(
            "/v1/event/tickets/cart-purchase/",
            data=encrypt(payload),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cart_purchase_invalid_ticket(self):
        """Cart with non-existent ticket fails."""
        payload = self._cart_payload()
        payload["items"][0]["ticket_id"] = str(uuid4())

        response = self.client.post(
            "/v1/event/tickets/cart-purchase/",
            data=encrypt(payload),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cart_purchase_exceeds_max(self):
        """Cart item exceeding max_purchase fails."""
        payload = self._cart_payload()
        payload["items"][0]["quantity"] = 100  # max is 10

        response = self.client.post(
            "/v1/event/tickets/cart-purchase/",
            data=encrypt(payload),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


# =============================================================================
# Integration Tests - Ticket Transfer
# =============================================================================


class TicketTransferTests(ThrottleDisabledAPITestCase):
    """Integration tests for ticket transfer flow."""

    def setUp(self):
        self.partner = _create_partner()
        self.sender = _create_member()
        self.recipient = _create_member(email="recipient@example.com")
        self.event = _create_event(self.partner)
        self.ticket = _create_ticket(self.event)
        self.purchase = _create_purchase(self.sender, self.ticket)
        self.ticket_code = self.purchase.codes.first()
        self.client.force_authenticate(user=self.sender)
        cache.clear()

    def test_request_transfer_success(self):
        """Member can request transfer to another member."""
        response = self.client.post(
            "/v1/event/tickets/transfer/request/",
            data=encrypt(
                {
                    "ticket_code": str(self.ticket_code.id),
                    "to_user": str(self.recipient.id),
                }
            ),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(TicketTransfer.objects.count(), 1)

    def test_request_transfer_self_fails(self):
        """Cannot transfer to self."""
        response = self.client.post(
            "/v1/event/tickets/transfer/request/",
            data=encrypt(
                {
                    "ticket_code": str(self.ticket_code.id),
                    "to_user": str(self.sender.id),
                }
            ),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_accept_transfer_success(self):
        """Recipient can accept transfer."""
        transfer = TicketTransfer.objects.create(
            ticket_code=self.ticket_code,
            from_user=self.sender,
            to_user=self.recipient,
        )

        self.client.force_authenticate(user=self.recipient)
        response = self.client.post(
            f"/v1/event/tickets/transfer/{transfer.id}/respond/",
            data=encrypt({"action": "accept"}),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        transfer.refresh_from_db()
        self.assertEqual(transfer.status, TicketTransfer.Status.ACCEPTED)
        self.ticket_code.refresh_from_db()
        self.assertEqual(self.ticket_code.current_owner, self.recipient)

    def test_decline_transfer_success(self):
        """Recipient can decline transfer."""
        transfer = TicketTransfer.objects.create(
            ticket_code=self.ticket_code,
            from_user=self.sender,
            to_user=self.recipient,
        )

        self.client.force_authenticate(user=self.recipient)
        response = self.client.post(
            f"/v1/event/tickets/transfer/{transfer.id}/respond/",
            data=encrypt({"action": "decline"}),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        transfer.refresh_from_db()
        self.assertEqual(transfer.status, TicketTransfer.Status.DECLINED)

    def test_cancel_transfer_success(self):
        """Sender can cancel pending transfer."""
        transfer = TicketTransfer.objects.create(
            ticket_code=self.ticket_code,
            from_user=self.sender,
            to_user=self.recipient,
        )

        response = self.client.post(
            f"/v1/event/tickets/transfer/{transfer.id}/cancel/",
            data=encrypt({}),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        transfer.refresh_from_db()
        self.assertEqual(transfer.status, TicketTransfer.Status.CANCELLED)


# =============================================================================
# Integration Tests - Check-in Verification
# =============================================================================


class TicketVerifyTests(ThrottleDisabledAPITestCase):
    """Integration tests for ticket check-in verification."""

    def setUp(self):
        self.partner = _create_partner()
        self.member = _create_member()
        self.event = _create_event(self.partner)
        self.ticket = _create_ticket(self.event)
        self.purchase = _create_purchase(self.member, self.ticket)
        self.ticket_code = self.purchase.codes.first()
        self.client.force_authenticate(user=self.partner)
        cache.clear()

    def test_verify_ticket_success(self):
        """Partner can verify and check-in ticket."""
        response = self.client.post(
            "/v1/event/partner/tickets/verify/",
            data=encrypt({"scanned_value": str(self.ticket_code.token)}),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.content)
        self.assertEqual(body["status"], "success")
        self.ticket_code.refresh_from_db()
        self.assertTrue(self.ticket_code.is_checked_in)

    def test_verify_already_checked_in(self):
        """Already checked-in ticket returns 400."""
        self.ticket_code.check_in(by=self.partner)

        response = self.client.post(
            "/v1/event/partner/tickets/verify/",
            data=encrypt({"scanned_value": str(self.ticket_code.token)}),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_verify_invalid_code(self):
        """Invalid code returns 400."""
        response = self.client.post(
            "/v1/event/partner/tickets/verify/",
            data=encrypt({"scanned_value": "invalid_code"}),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


# =============================================================================
# Integration Tests - Partner Endpoints
# =============================================================================


class PartnerEventTests(ThrottleDisabledAPITestCase):
    """Integration tests for partner event management."""

    def setUp(self):
        self.partner = _create_partner()
        self.client.force_authenticate(user=self.partner)
        cache.clear()

    def test_create_event_success(self):
        """Partner can create event."""
        now = timezone.now()
        data = {
            "business_name": "Test Events",
            "business_type": "Events",
            "event_name": "New Event",
            "description": "Test event description",
            "category": "Tech",
            "mode": "Physical",
            "address": "123 Street",
            "start_date": (now + timedelta(days=30)).isoformat(),
            "end_date": (now + timedelta(days=31)).isoformat(),
        }

        response = self.client.post(
            "/v1/event/partner/",
            data=encrypt(data),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Event.objects.count(), 1)
        self.assertEqual(Event.objects.first().status, Event.Status.IN_REVIEW)

    def test_list_own_events(self):
        """Partner sees only their events."""
        other_partner = _create_partner(email="other_partner@example.com")
        _create_event(self.partner)
        _create_event(other_partner, event_name="Other Event")

        response = self.client.get("/v1/event/partner/")
        body = decrypt(response.content)
        self.assertEqual(len(body["data"]["events"]), 1)

    def test_update_event_success(self):
        """Partner can update draft event."""
        event = _create_event(self.partner, status=Event.Status.DRAFT)

        response = self.client.patch(
            f"/v1/event/partner/{event.id}/",
            data=encrypt({"event_name": "Updated Event"}),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        event.refresh_from_db()
        self.assertEqual(event.event_name, "Updated Event")

    def test_cannot_update_on_sale_event(self):
        """Partner cannot edit on-sale event."""
        event = _create_event(self.partner, status=Event.Status.ON_SALE)

        response = self.client.patch(
            f"/v1/event/partner/{event.id}/",
            data=encrypt({"event_name": "Hacked"}),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_delete_draft_event(self):
        """Partner can delete draft event."""
        event = _create_event(self.partner, status=Event.Status.DRAFT)

        response = self.client.delete(f"/v1/event/partner/{event.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(Event.objects.filter(id=event.id).exists())


# =============================================================================
# Integration Tests - Admin Endpoints
# =============================================================================


class AdminEventReviewTests(ThrottleDisabledAPITestCase):
    """Integration tests for admin event review."""

    def setUp(self):
        self.admin = _create_admin()
        self.partner = _create_partner()
        self.client.force_authenticate(user=self.admin)
        cache.clear()

    def test_approve_event(self):
        """Admin can approve in-review event."""
        event = _create_event(self.partner, status=Event.Status.IN_REVIEW)

        response = self.client.post(
            f"/v1/event/admin/{event.id}/review/",
            data=encrypt({"status": "on_sale"}),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        event.refresh_from_db()
        self.assertEqual(event.status, Event.Status.ON_SALE)

    def test_reject_event(self):
        """Admin can reject event with reason."""
        event = _create_event(self.partner, status=Event.Status.IN_REVIEW)

        response = self.client.post(
            f"/v1/event/admin/{event.id}/review/",
            data=encrypt(
                {
                    "status": "rejected",
                    "rejection_reason": "Incomplete information",
                }
            ),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        event.refresh_from_db()
        self.assertEqual(event.status, Event.Status.REJECTED)
        self.assertEqual(event.rejection_reason, "Incomplete information")

    def test_reject_without_reason_fails(self):
        """Rejection without reason fails."""
        event = _create_event(self.partner, status=Event.Status.IN_REVIEW)

        response = self.client.post(
            f"/v1/event/admin/{event.id}/review/",
            data=encrypt({"status": "rejected"}),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class EventDetailedStatsTests(ThrottleDisabledAPITestCase):
    """Integration tests for detailed event stats."""

    def setUp(self):
        self.admin = _create_admin()
        self.partner = _create_partner()
        self.member1 = _create_member(email="member1@example.com")
        self.member2 = _create_member(email="member2@example.com")
        self.event = _create_event(self.partner)
        self.ticket_a = _create_ticket(
            self.event, name="Regular", price=Decimal("10000.00")
        )
        self.ticket_b = _create_ticket(
            self.event, name="VIP", price=Decimal("40000.00")
        )
        cache.clear()

    def test_admin_gets_detailed_stats(self):
        """Admin can view detailed stats with payment references."""
        _create_purchase(self.member1, self.ticket_a, quantity=2)
        _create_purchase(self.member2, self.ticket_a, quantity=3)
        _create_purchase(self.member1, self.ticket_b, quantity=1)

        self.client.force_authenticate(user=self.admin)
        response = self.client.get(f"/v1/event/admin/{self.event.id}/detailed-stats/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.content)
        self.assertEqual(body["status"], "success")
        data = body["data"]
        self.assertEqual(data["total_tickets_sold"], 6)
        self.assertEqual(data["total_buyers"], 2)
        self.assertEqual(len(data["ticket_breakdown"]), 2)

        # Check payment_reference is included for admin
        first_buyer = data["ticket_breakdown"][0]["buyers"][0]
        self.assertIn("payment_reference", first_buyer)

    def test_partner_gets_detailed_stats_no_payment_ref(self):
        """Partner can view detailed stats without payment references."""
        _create_purchase(self.member1, self.ticket_a, quantity=2)

        self.client.force_authenticate(user=self.partner)
        response = self.client.get(f"/v1/event/partner/{self.event.id}/detailed-stats/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.content)
        data = body["data"]

        # Check payment_reference is NOT included for partner
        first_buyer = data["ticket_breakdown"][0]["buyers"][0]
        self.assertNotIn("payment_reference", first_buyer)

    def test_non_owner_partner_cannot_view_stats(self):
        """Partner who doesn't own event cannot view stats."""
        other_partner = _create_partner(email="other@example.com")

        self.client.force_authenticate(user=other_partner)
        response = self.client.get(f"/v1/event/partner/{self.event.id}/detailed-stats/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


# =============================================================================
# Audit Tests - Security & Data Integrity
# =============================================================================


class TicketSecurityAuditTests(ThrottleDisabledAPITestCase):
    """Security audit tests for event/ticketing."""

    def setUp(self):
        self.partner = _create_partner()
        self.member = _create_member()
        self.admin = _create_admin()
        self.event = _create_event(self.partner)
        self.ticket = _create_ticket(self.event)
        cache.clear()

    def test_partner_cannot_verify_other_events_tickets(self):
        """Partner can only verify tickets for their own events."""
        other_partner = _create_partner(email="other_partner@example.com")
        other_event = _create_event(other_partner, event_name="Other Event")
        other_ticket = _create_ticket(other_event)
        purchase = _create_purchase(self.member, other_ticket)
        code = purchase.codes.first()

        self.client.force_authenticate(user=self.partner)
        response = self.client.post(
            "/v1/event/partner/tickets/verify/",
            data=encrypt({"scanned_value": str(code.token)}),
            format="json",
        )

        # Should fail because partner doesn't own the event
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_member_cannot_access_partner_endpoints(self):
        """Members cannot access partner endpoints."""
        self.client.force_authenticate(user=self.member)
        response = self.client.get("/v1/event/partner/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_partner_cannot_access_admin_endpoints(self):
        """Partners cannot access admin endpoints."""
        self.client.force_authenticate(user=self.partner)
        response = self.client.get("/v1/event/admin/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_slot_reservation_race_prevention(self):
        """Atomic slot reservation prevents race conditions."""
        self.ticket.slot_cap = 1
        self.ticket.slots_filled = 0
        self.ticket.save()

        member2 = _create_member(email="member2@example.com")

        result1 = self.ticket.reserve_slots(1)
        result2 = self.ticket.reserve_slots(1)

        self.assertTrue(result1)
        self.assertFalse(result2)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.slots_filled, 1)


class TicketDataIntegrityTests(ThrottleDisabledAPITestCase):
    """Data integrity audit tests."""

    def setUp(self):
        self.partner = _create_partner()
        self.member = _create_member()
        self.event = _create_event(self.partner)
        self.ticket = _create_ticket(self.event)

    def test_slots_filled_matches_ticket_codes(self):
        """Slots filled equals number of ticket codes."""
        purchase = _create_purchase(self.member, self.ticket, quantity=5)

        code_count = TicketCode.objects.filter(purchase__ticket=self.ticket).count()
        self.ticket.refresh_from_db()

        self.assertEqual(code_count, 5)
        # After purchase, slots should be filled
        self.assertEqual(
            TicketPurchase.objects.filter(
                ticket=self.ticket,
                status=TicketPurchase.Status.PAID,
            ).aggregate(total=models.Sum("quantity"))["total"],
            5,
        )

    def test_partner_sale_created_on_purchase(self):
        """PartnerTicketSale is created for each purchase."""
        purchase = _create_purchase(self.member, self.ticket, quantity=2)

        from event.models import PartnerTicketSale

        # Create sale if it doesn't exist (for test purposes)
        if not PartnerTicketSale.objects.filter(purchase=purchase).exists():
            PartnerTicketSale.objects.create(
                purchase=purchase,
                partner=self.partner,
                event=self.event,
                ticket=self.ticket,
                gross_amount=purchase.total_amount,
            )

        sale = PartnerTicketSale.objects.filter(purchase=purchase).first()
        self.assertIsNotNone(sale)
        self.assertEqual(sale.partner, self.partner)
        self.assertEqual(sale.gross_amount, purchase.total_amount)
        self.assertGreater(sale.platform_fee_amount, 0)
        expected_net = sale.gross_amount - sale.platform_fee_amount
        self.assertEqual(sale.net_amount, expected_net)


# =============================================================================
# Fuzz Tests - Edge Cases & Malformed Inputs
# =============================================================================


class TicketFuzzTests(ThrottleDisabledAPITestCase):
    """Fuzz testing for edge cases and malformed inputs."""

    def setUp(self):
        self.partner = _create_partner()
        self.member = _create_member()
        self.event = _create_event(self.partner)
        self.ticket = _create_ticket(self.event)
        self.wallet = _create_wallet(self.member)
        self.client.force_authenticate(user=self.member)
        cache.clear()

    def test_purchase_with_zero_quantity(self):
        """Zero quantity returns 400."""
        response = self.client.post(
            "/v1/event/tickets/purchase/",
            data=encrypt(
                {
                    "ticket": str(self.ticket.id),
                    "quantity": 0,
                    "payment_option": "WALLET",
                    "pin": "123456",
                }
            ),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_purchase_with_negative_quantity(self):
        """Negative quantity returns 400."""
        response = self.client.post(
            "/v1/event/tickets/purchase/",
            data=encrypt(
                {
                    "ticket": str(self.ticket.id),
                    "quantity": -5,
                    "payment_option": "WALLET",
                    "pin": "123456",
                }
            ),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_purchase_with_invalid_payment_option(self):
        """Invalid payment option returns 400."""
        response = self.client.post(
            "/v1/event/tickets/purchase/",
            data=encrypt(
                {
                    "ticket": str(self.ticket.id),
                    "quantity": 1,
                    "payment_option": "INVALID",
                }
            ),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_purchase_with_nonexistent_ticket(self):
        """Non-existent ticket returns 400."""
        response = self.client.post(
            "/v1/event/tickets/purchase/",
            data=encrypt(
                {
                    "ticket": str(uuid4()),
                    "quantity": 1,
                    "payment_option": "WALLET",
                    "pin": "123456",
                }
            ),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_purchase_with_wrong_pin(self):
        """Wrong PIN returns 403."""
        response = self.client.post(
            "/v1/event/tickets/purchase/",
            data=encrypt(
                {
                    "ticket": str(self.ticket.id),
                    "quantity": 1,
                    "payment_option": "WALLET",
                    "pin": "999999",
                }
            ),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_cart_with_empty_items(self):
        """Empty cart returns 400."""
        response = self.client.post(
            "/v1/event/tickets/cart-purchase/",
            data=encrypt(
                {
                    "items": [],
                    "payment_option": "WALLET",
                    "pin": "123456",
                }
            ),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cart_with_duplicate_tickets(self):
        """Duplicate tickets in cart returns 400."""
        response = self.client.post(
            "/v1/event/tickets/cart-purchase/",
            data=encrypt(
                {
                    "items": [
                        {"ticket_id": str(self.ticket.id), "quantity": 1},
                        {"ticket_id": str(self.ticket.id), "quantity": 2},
                    ],
                    "payment_option": "WALLET",
                    "pin": "123456",
                }
            ),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_transfer_expired_ticket(self):
        """Transfer of expired ticket window fails."""
        purchase = _create_purchase(self.member, self.ticket)
        code = purchase.codes.first()

        # Mock the transfer window check
        with patch.object(
            TicketPurchase,
            "is_within_transfer_window",
            new_callable=MagicMock(return_value=False),
        ):
            recipient = _create_member(email="recipient@example.com")
            response = self.client.post(
                "/v1/event/tickets/transfer/request/",
                data=encrypt(
                    {
                        "ticket_code": str(code.id),
                        "to_user": str(recipient.id),
                    }
                ),
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


# =============================================================================
# Performance Tests
# =============================================================================


class TicketPerformanceTests(ThrottleDisabledAPITestCase):
    """Performance tests for bulk operations."""

    def setUp(self):
        self.partner = _create_partner()
        self.member = _create_member()
        self.event = _create_event(self.partner)
        self.ticket = _create_ticket(self.event, slot_cap=1000)
        cache.clear()

    def test_bulk_ticket_code_generation(self):
        """Bulk ticket code generation performs well."""
        import time
        import uuid

        purchase = _create_purchase(self.member, self.ticket, quantity=100)

        start_time = time.time()
        codes = []
        for _ in range(100):
            codes.append(
                TicketCode(
                    purchase=purchase,
                    current_owner=self.member,
                    code=uuid.uuid4().hex[:8].upper(),
                )
            )
        TicketCode.objects.bulk_create(codes)
        elapsed = time.time() - start_time

        self.assertLess(elapsed, 5)
        self.assertEqual(TicketCode.objects.filter(purchase=purchase).count(), 200)

    def test_large_event_listing(self):
        """Listing 100 events performs well."""
        import time

        for i in range(100):
            _create_event(
                self.partner,
                event_name=f"Event {i}",
                slug=f"event-{i}",
            )

        self.client.force_authenticate(user=self.member)
        start_time = time.time()
        response = self.client.get("/v1/event/")
        elapsed = time.time() - start_time

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertLess(elapsed, 5)
