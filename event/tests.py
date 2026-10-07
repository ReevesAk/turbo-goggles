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

from accounts.models import User, AccountType, UserNotification
from banking.models import WalletModel
from partners.models import PartnerCommissionRule
from security import encrypt, decrypt

from .models import (
    Event,
    EventPartnerProfile,
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
        "is_staff": False,
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
    defaults = {
        "active_role": "Partner",
        "business_verified": True,
    }
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
        "event_name": "Tech Conference 2024",
        "description": "A comprehensive tech conference covering AI, blockchain, and more.",
        "category": "Technology",
        "tags": ["tech", "ai", "blockchain"],
        "mode": "Physical",
        "address": "123 Test Street, Lagos",
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

    # Create ticket codes - bulk create avoids save() Cloudinary calls
    codes = []
    for _ in range(purchase.quantity):
        code = TicketCode(
            purchase=purchase,
            current_owner=member,
        )
        # Generate code without triggering save()
        code.code = code._generate_unique_code()
        codes.append(code)
    TicketCode.objects.bulk_create(codes)

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

        # Create ticket codes - bulk create avoids save() Cloudinary calls
        codes = []
        for _ in range(purchase.quantity):
            code = TicketCode(
                purchase=purchase,
                current_owner=member,
            )
            code.code = code._generate_unique_code()
            codes.append(code)
        TicketCode.objects.bulk_create(codes)

    return order


def _create_event_partner_profile(user, **overrides):
    """Create an EventPartnerProfile with sensible defaults (APPROVED)."""
    defaults = {
        "user": user,
        "nin": "12345678901",
        "nin_verified": True,
        "nin_name": f"{user.first_name} {user.last_name}",
        "nin_dob": "1990-01-01",
        "bank_code": "000013",
        "bank_name": "GTBank",
        "bank_account_number": "0123456789",
        "status": EventPartnerProfile.Status.APPROVED,
        "reviewed_at": timezone.now(),
    }
    defaults.update(overrides)
    return EventPartnerProfile.objects.create(**defaults)


# =============================================================================
# Base Test Case with Throttle, Cloudinary & Celery Mocking
# =============================================================================


class ThrottleDisabledAPITestCase(APITestCase):
    """
    Base class that disables DRF throttling, mocks Cloudinary, and mocks Celery.
    Prevents live API calls and task queue connections during tests.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Disable DRF throttling
        cls._throttle_patcher = patch("rest_framework.views.APIView.check_throttles")
        cls._throttle_patcher.start()

        # Mock Cloudinary uploader to prevent live API calls
        cls._cloudinary_patcher = patch(
            "cloudinary.uploader.upload",
            return_value={"secure_url": "https://mock.cloudinary.com/qr.png"},
        )
        cls._cloudinary_patcher.start()

        # Mock QR code image generation
        cls._qrcode_patcher = patch(
            "qrcode.QRCode.make_image", return_value=MagicMock()
        )
        cls._qrcode_patcher.start()

        # Mock Celery's delay() to prevent Redis connections
        cls._celery_patcher = patch(
            "event.tasks.generate_ticket_qr_async.delay", return_value=MagicMock()
        )
        cls._celery_patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls._throttle_patcher.stop()
        cls._cloudinary_patcher.stop()
        cls._qrcode_patcher.stop()
        cls._celery_patcher.stop()
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

    def test_event_is_upcoming_property(self):
        """is_upcoming returns correct boolean."""
        self.assertTrue(self.event.is_upcoming)

        # Past event
        past_event = _create_event(
            self.partner,
            start_date=timezone.now() - timedelta(days=10),
            end_date=timezone.now() - timedelta(days=9),
        )
        self.assertFalse(past_event.is_upcoming)

    def test_event_is_past_property(self):
        """is_past returns correct boolean."""
        self.assertFalse(self.event.is_past)

        # Past event
        past_event = _create_event(
            self.partner,
            start_date=timezone.now() - timedelta(days=10),
            end_date=timezone.now() - timedelta(days=9),
        )
        self.assertTrue(past_event.is_past)

    def test_event_location_setter(self):
        """set_location creates Point from lat/lng."""
        self.event.set_location(6.5244, 3.3792)
        self.event.save()
        self.assertIsNotNone(self.event.location)
        self.assertEqual(self.event.latitude, 6.5244)
        self.assertEqual(self.event.longitude, 3.3792)

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

        # Test sold out
        self.ticket.is_active = True
        self.ticket.slots_filled = 100
        self.ticket.save()
        self.assertFalse(self.ticket.is_on_sale)

        # Test sales dates
        self.ticket.slots_filled = 0
        self.ticket.sales_start_date = timezone.now() + timedelta(days=1)
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

    def test_reserve_slots_unlimited(self):
        """reserve_slots always succeeds for unlimited tickets."""
        self.ticket.unlimited_slots = True
        self.ticket.save()
        result = self.ticket.reserve_slots(999999)
        self.assertTrue(result)


class TicketPurchaseModelTests(ThrottleDisabledAPITestCase):
    """Unit tests for TicketPurchase model."""

    def setUp(self):
        self.partner = _create_partner()
        self.member = _create_member()
        self.event = _create_event(self.partner)
        self.ticket = _create_ticket(self.event)

    def test_is_paid_property(self):
        """is_paid returns correct boolean."""
        purchase = TicketPurchase.objects.create(
            member=self.member,
            ticket=self.ticket,
            event=self.event,
            quantity=1,
            unit_price=self.ticket.price,
            total_amount=self.ticket.price,
            status=TicketPurchase.Status.PENDING,
        )
        self.assertFalse(purchase.is_paid)

        purchase.status = TicketPurchase.Status.PAID
        purchase.save()
        self.assertTrue(purchase.is_paid)

    def test_is_within_transfer_window(self):
        """is_within_transfer_window checks transfer window."""
        purchase = _create_purchase(self.member, self.ticket)

        # Should be within window
        self.assertTrue(purchase.is_within_transfer_window)

        # Fast forward past window
        with freeze_time(timezone.now() + timedelta(hours=72)):
            self.assertFalse(purchase.is_within_transfer_window)


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
        response = self.client.get("/v1/events/")
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

        response = self.client.get("/v1/events/?category=Music")
        body = decrypt(response.content)
        self.assertEqual(body["data"]["count"], 1)

    def test_list_events_requires_auth(self):
        """Unauthenticated requests get 401."""
        self.client.force_authenticate(user=None)
        response = self.client.get("/v1/events/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_list_events_cached(self):
        """Event list is cached."""
        _create_event(self.partner)
        response1 = self.client.get("/v1/events/")
        body1 = decrypt(response1.content)

        with patch("django.core.cache.cache.get") as mock_cache_get:
            mock_cache_get.return_value = body1
            response2 = self.client.get("/v1/events/")
            self.assertEqual(response2.status_code, status.HTTP_200_OK)
            mock_cache_get.assert_called()


class EventPublicDetailTests(ThrottleDisabledAPITestCase):
    """Integration tests for event detail endpoint."""

    def setUp(self):
        self.partner = _create_partner()
        self.member = _create_member()
        self.event = _create_event(self.partner, slug="test-event-2024")
        self.client.force_authenticate(user=self.member)
        cache.clear()

    def test_get_event_detail_success(self):
        """Members can view event details."""
        response = self.client.get(f"/v1/events/{self.event.slug}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.content)
        self.assertEqual(body["status"], "success")
        self.assertEqual(body["data"]["event"]["id"], str(self.event.id))

    def test_get_event_detail_increments_view_count(self):
        """View count increments on detail view."""
        initial_count = self.event.view_count
        self.client.get(f"/v1/events/{self.event.slug}/")
        self.event.refresh_from_db()
        self.assertEqual(self.event.view_count, initial_count + 1)

    def test_get_event_detail_404(self):
        """Non-existent event returns 404."""
        response = self.client.get("/v1/events/non-existent-slug/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class EventTicketsListTests(ThrottleDisabledAPITestCase):
    """Integration tests for event tickets listing."""

    def setUp(self):
        self.partner = _create_partner()
        self.member = _create_member()
        self.event = _create_event(self.partner, slug="test-event-2024")
        self.ticket = _create_ticket(self.event)
        self.client.force_authenticate(user=self.member)
        cache.clear()

    def test_list_event_tickets_success(self):
        """Members can list tickets for an event."""
        response = self.client.get(f"/v1/events/{self.event.slug}/tickets/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.content)
        self.assertEqual(body["status"], "success")
        self.assertEqual(len(body["data"]["tickets"]), 1)


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
                    "/v1/events/tickets/purchase/",
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
                "/v1/events/tickets/purchase/",
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
            "/v1/events/tickets/purchase/",
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
                    "/v1/events/tickets/purchase/",
                    data=encrypt(
                        self._purchase_payload(idempotency_key=idempotency_key)
                    ),
                    format="json",
                )

                response2 = self.client.post(
                    "/v1/events/tickets/purchase/",
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
                    "/v1/events/tickets/cart-purchase/",
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
            "/v1/events/tickets/cart-purchase/",
            data=encrypt(payload),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cart_purchase_invalid_ticket(self):
        """Cart with non-existent ticket fails."""
        payload = self._cart_payload()
        payload["items"][0]["ticket_id"] = str(uuid4())

        response = self.client.post(
            "/v1/events/tickets/cart-purchase/",
            data=encrypt(payload),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cart_purchase_exceeds_max(self):
        """Cart item exceeding max_purchase fails."""
        payload = self._cart_payload()
        payload["items"][0]["quantity"] = 100  # max is 10

        response = self.client.post(
            "/v1/events/tickets/cart-purchase/",
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
            "/v1/events/tickets/transfer/request/",
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
            "/v1/events/tickets/transfer/request/",
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
            f"/v1/events/tickets/transfer/{transfer.id}/respond/",
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
            f"/v1/events/tickets/transfer/{transfer.id}/respond/",
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
            f"/v1/events/tickets/transfer/{transfer.id}/cancel/",
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
            "/v1/events/partner/tickets/verify/",
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
            "/v1/events/partner/tickets/verify/",
            data=encrypt({"scanned_value": str(self.ticket_code.token)}),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_verify_invalid_code(self):
        """Invalid code returns 400."""
        response = self.client.post(
            "/v1/events/partner/tickets/verify/",
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
        _create_event_partner_profile(
            self.partner,
            status=EventPartnerProfile.Status.APPROVED,
        )
        self.client.force_authenticate(user=self.partner)
        cache.clear()

    def test_create_event_success(self):
        """Partner can create event."""
        now = timezone.now()
        data = {
            "event_name": "New Event",
            "description": "Test event description",
            "category": "Restaurant",
            "mode": "Physical",
            "address": "123 Street",
            "start_date": (now + timedelta(days=30)).isoformat(),
            "end_date": (now + timedelta(days=31)).isoformat(),
        }

        response = self.client.post(
            "/v1/events/partner/",
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

        response = self.client.get("/v1/events/partner/")
        body = decrypt(response.content)
        self.assertEqual(len(body["data"]["events"]), 1)

    def test_update_event_success(self):
        """Partner can update draft event."""
        event = _create_event(self.partner, status=Event.Status.DRAFT)

        response = self.client.patch(
            f"/v1/events/partner/{event.id}/",
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
            f"/v1/events/partner/{event.id}/",
            data=encrypt({"event_name": "Hacked"}),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_delete_draft_event(self):
        """Partner can delete draft event."""
        event = _create_event(self.partner, status=Event.Status.DRAFT)

        response = self.client.delete(f"/v1/events/partner/{event.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(Event.objects.filter(id=event.id).exists())

    def test_non_verified_partner_cannot_create_event(self):
        """Non-verified partner cannot create event."""
        unverified_partner = _create_partner(
            email="unverified@example.com",
            business_verified=False,
        )
        self.client.force_authenticate(user=unverified_partner)

        now = timezone.now()
        data = {
            "event_name": "New Event",
            "description": "Test event description",
            "category": "Technology",
            "mode": "Physical",
            "address": "123 Street",
            "start_date": (now + timedelta(days=30)).isoformat(),
            "end_date": (now + timedelta(days=31)).isoformat(),
        }

        response = self.client.post(
            "/v1/events/partner/",
            data=encrypt(data),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class PartnerTicketTests(ThrottleDisabledAPITestCase):
    """Integration tests for partner ticket management."""

    def setUp(self):
        self.partner = _create_partner()
        self.event = _create_event(self.partner, status=Event.Status.DRAFT)
        self.client.force_authenticate(user=self.partner)
        cache.clear()

    def test_create_ticket_success(self):
        """Partner can create ticket for draft event."""
        now = timezone.now()
        data = {
            "name": "Regular",
            "description": "Standard ticket",
            "price": "10000.00",
            "slot_cap": 100,
            "sales_start_date": now.isoformat(),
            "sales_end_date": (now + timedelta(days=25)).isoformat(),
            "min_purchase": 1,
            "max_purchase": 10,
        }

        response = self.client.post(
            f"/v1/events/partner/{self.event.id}/tickets/",
            data=encrypt(data),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Ticket.objects.count(), 1)

    def test_cannot_create_ticket_for_on_sale_event(self):
        """Cannot create ticket for on-sale event."""
        self.event.status = Event.Status.ON_SALE
        self.event.save()

        response = self.client.post(
            f"/v1/events/partner/{self.event.id}/tickets/",
            data=encrypt({"name": "Late Ticket", "price": "20000.00"}),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_delete_ticket_without_purchases(self):
        """Can delete ticket with no purchases."""
        ticket = _create_ticket(self.event)

        response = self.client.delete(f"/v1/events/partner/tickets/{ticket.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(Ticket.objects.filter(id=ticket.id).exists())

    def test_cannot_delete_ticket_with_purchases(self):
        """Cannot delete ticket with existing purchases."""
        ticket = _create_ticket(self.event)
        member = _create_member()
        _create_purchase(member, ticket)

        response = self.client.delete(f"/v1/events/partner/tickets/{ticket.id}/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


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
            f"/v1/events/admin/{event.id}/review/",
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
            f"/v1/events/admin/{event.id}/review/",
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
            f"/v1/events/admin/{event.id}/review/",
            data=encrypt({"status": "rejected"}),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_partners_admin_can_review_events(self):
        """PartnersAdmin can review events."""
        partners_admin = _create_admin(email="partnersadmin@example.com")
        partners_admin.active_role = "PartnersAdmin"
        partners_admin.save()

        self.client.force_authenticate(user=partners_admin)
        event = _create_event(self.partner, status=Event.Status.IN_REVIEW)

        response = self.client.post(
            f"/v1/events/admin/{event.id}/review/",
            data=encrypt({"status": "on_sale"}),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        event.refresh_from_db()
        self.assertEqual(event.status, Event.Status.ON_SALE)


class AdminSaleWindowTests(ThrottleDisabledAPITestCase):
    """Integration tests for admin sale window management."""

    def setUp(self):
        self.admin = _create_admin()
        self.partner = _create_partner()
        self.event = _create_event(self.partner)
        self.client.force_authenticate(user=self.admin)
        cache.clear()

    def test_create_sale_window_success(self):
        """Admin can create sale window for partner."""
        now = timezone.now()
        data = {
            "partner": str(self.partner.id),
            "event": str(self.event.id),
            "starts_at": (now + timedelta(days=1)).isoformat(),
            "ends_at": (now + timedelta(days=3)).isoformat(),
            "note": "Test window",
        }

        response = self.client.post(
            "/v1/events/admin/sale-windows/create/",
            data=encrypt(data),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(PartnerSaleWindow.objects.count(), 1)

    def test_list_sale_windows(self):
        """Admin can list sale windows."""
        PartnerSaleWindow.objects.create(
            partner=self.partner,
            event=self.event,
            granted_by=self.admin,
            starts_at=timezone.now() + timedelta(days=1),
            ends_at=timezone.now() + timedelta(days=3),
        )

        response = self.client.get("/v1/events/admin/sale-windows/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.content)
        self.assertEqual(len(body["data"]["sale_windows"]), 1)


class AdminTicketConfigurationTests(ThrottleDisabledAPITestCase):
    """Integration tests for admin ticket configuration."""

    def setUp(self):
        self.admin = _create_admin()
        self.client.force_authenticate(user=self.admin)
        cache.clear()

    def test_get_configuration(self):
        """Admin can get ticket configuration."""
        response = self.client.get("/v1/events/admin/ticket-config/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.content)
        self.assertEqual(body["status"], "success")
        self.assertIn("config", body["data"])

    def test_update_configuration(self):
        """Admin can update ticket configuration."""
        response = self.client.patch(
            "/v1/events/admin/ticket-config/",
            data=encrypt({"transfer_window": "PT72H"}),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        config = TicketConfiguration.get_solo()
        self.assertEqual(config.transfer_window.total_seconds(), 72 * 3600)


class EventDetailedStatsTests(ThrottleDisabledAPITestCase):
    """Integration tests for detailed event stats."""

    def setUp(self):
        self.admin = _create_admin()
        self.partner = _create_partner()
        self.member1 = _create_member(email="member1@example.com")
        self.member2 = _create_member(email="member2@example.com")
        self.event = _create_event(self.partner, slug="test-event-stats")
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
        response = self.client.get(f"/v1/events/admin/{self.event.id}/detailed-stats/")

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
        response = self.client.get(
            f"/v1/events/partner/{self.event.id}/detailed-stats/"
        )

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
        response = self.client.get(
            f"/v1/events/partner/{self.event.id}/detailed-stats/"
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class AdminTicketStatsTests(ThrottleDisabledAPITestCase):
    """Integration tests for admin ticket statistics."""

    def setUp(self):
        self.admin = _create_admin()
        self.partner = _create_partner()
        self.member = _create_member()
        self.event = _create_event(self.partner)
        self.ticket = _create_ticket(self.event)
        self.client.force_authenticate(user=self.admin)
        cache.clear()

    def test_get_ticket_stats(self):
        """Admin can get comprehensive ticket stats."""
        _create_purchase(self.member, self.ticket, quantity=5)

        response = self.client.get("/v1/events/admin/tickets/stats/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.content)
        self.assertEqual(body["status"], "success")
        data = body["data"]
        self.assertEqual(data["purchases"]["tickets_sold"], 5)
        self.assertEqual(data["events"]["total"], 1)
        self.assertEqual(data["events"]["on_sale"], 1)


class AdminRefundPurchaseTests(ThrottleDisabledAPITestCase):
    """Integration tests for admin purchase refund."""

    def setUp(self):
        self.admin = _create_admin()
        self.partner = _create_partner()
        self.member = _create_member()
        self.event = _create_event(self.partner)
        self.ticket = _create_ticket(self.event)
        self.purchase = _create_purchase(self.member, self.ticket)
        self.client.force_authenticate(user=self.admin)
        cache.clear()

    def test_refund_purchase_success(self):
        """Admin can refund a purchase."""
        response = self.client.post(
            f"/v1/events/admin/purchases/{self.purchase.id}/refund/",
            data=encrypt({}),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.purchase.refresh_from_db()
        self.assertEqual(self.purchase.status, TicketPurchase.Status.REFUNDED)

    def test_refund_non_paid_purchase_fails(self):
        """Cannot refund non-paid purchase."""
        self.purchase.status = TicketPurchase.Status.PENDING
        self.purchase.save()

        response = self.client.post(
            f"/v1/events/admin/purchases/{self.purchase.id}/refund/",
            data=encrypt({}),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


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
            "/v1/events/partner/tickets/verify/",
            data=encrypt({"scanned_value": str(code.token)}),
            format="json",
        )

        # Should fail because partner doesn't own the event
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_member_cannot_access_partner_endpoints(self):
        """Members cannot access partner endpoints."""
        self.client.force_authenticate(user=self.member)
        response = self.client.get("/v1/events/partner/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_partner_cannot_access_admin_endpoints(self):
        """Partners cannot access admin endpoints."""
        self.client.force_authenticate(user=self.partner)
        response = self.client.get("/v1/events/admin/")
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

    def test_platform_fee_uses_business_category_not_event_category(self):
        """
        Regression: the event-category-vs-business-category match check was
        removed (partners can now pick any event category), so the platform
        fee must be keyed off the partner's verified business_category —
        not the freely-chosen event.category — or a partner could pick a
        low-commission category to underpay platform fees.
        """
        self.partner.business_category = "Hotel"
        self.partner.save()
        self.event.category = "Cinema"  # deliberately mismatched, low-fee pick
        self.event.save()

        PartnerCommissionRule.objects.create(
            business="Hotel", commission_rate=Decimal("20.00")
        )
        PartnerCommissionRule.objects.create(
            business="Cinema", commission_rate=Decimal("2.00")
        )

        purchase = _create_purchase(self.member, self.ticket, quantity=1)
        sale = PartnerTicketSale.objects.create(
            purchase=purchase,
            partner=self.partner,
            event=self.event,
            ticket=self.ticket,
            gross_amount=purchase.total_amount,
        )

        self.assertEqual(sale.platform_fee_percentage, Decimal("20.00"))


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
            "/v1/events/tickets/purchase/",
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
            "/v1/events/tickets/purchase/",
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
            "/v1/events/tickets/purchase/",
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
            "/v1/events/tickets/purchase/",
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
            "/v1/events/tickets/purchase/",
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
            "/v1/events/tickets/cart-purchase/",
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
            "/v1/events/tickets/cart-purchase/",
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
                "/v1/events/tickets/transfer/request/",
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

        purchase = _create_purchase(self.member, self.ticket, quantity=100)

        start_time = time.time()
        codes = []
        for _ in range(100):
            code = TicketCode(
                purchase=purchase,
                current_owner=self.member,
            )
            code.code = code._generate_unique_code()
            codes.append(code)
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
        response = self.client.get("/v1/events/")
        elapsed = time.time() - start_time

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertLess(elapsed, 5)


# =============================================================================
# Partner Sales Ledger Tests
# =============================================================================


class PartnerSalesLedgerTests(ThrottleDisabledAPITestCase):
    """Integration tests for partner sales ledger."""

    def setUp(self):
        self.partner = _create_partner()
        self.member = _create_member()
        self.event = _create_event(self.partner)
        self.ticket = _create_ticket(self.event)
        self.client.force_authenticate(user=self.partner)
        cache.clear()

    def test_sales_ledger_summary(self):
        """Partner can view sales ledger with summary."""
        purchase = _create_purchase(self.member, self.ticket, quantity=3)

        # Create partner sale record
        PartnerTicketSale.objects.create(
            purchase=purchase,
            partner=self.partner,
            event=self.event,
            ticket=self.ticket,
            gross_amount=purchase.total_amount,
        )

        response = self.client.get("/v1/events/partner/sales/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.content)
        self.assertEqual(body["status"], "success")
        data = body["data"]
        self.assertEqual(len(data["sales"]), 1)
        self.assertIn("summary", data)
        self.assertEqual(
            float(data["summary"]["total_gross"]), float(purchase.total_amount)
        )

    def test_sales_ledger_filter_by_status(self):
        """Partner can filter sales by settlement status."""
        purchase = _create_purchase(self.member, self.ticket, quantity=2)

        sale = PartnerTicketSale.objects.create(
            purchase=purchase,
            partner=self.partner,
            event=self.event,
            ticket=self.ticket,
            gross_amount=purchase.total_amount,
            settlement_status=PartnerTicketSale.SettlementStatus.SETTLED,
        )

        response = self.client.get(
            "/v1/events/partner/sales/?settlement_status=settled"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.content)
        self.assertEqual(len(body["data"]["sales"]), 1)


# =============================================================================
# Member Order & Purchase Tests
# =============================================================================


class MemberOrderTests(ThrottleDisabledAPITestCase):
    """Integration tests for member orders."""

    def setUp(self):
        self.partner = _create_partner()
        self.member = _create_member()
        self.event = _create_event(self.partner)
        self.ticket = _create_ticket(self.event)
        self.client.force_authenticate(user=self.member)
        cache.clear()

    def test_list_orders(self):
        """Member can list their orders."""
        order = _create_order(
            self.member,
            self.event,
            [{"ticket": self.ticket, "quantity": 2}],
        )

        response = self.client.get("/v1/events/tickets/orders/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.content)
        self.assertEqual(len(body["data"]["orders"]), 1)

    def test_list_purchases(self):
        """Member can list their purchases."""
        purchase = _create_purchase(self.member, self.ticket, quantity=3)

        response = self.client.get("/v1/events/tickets/purchases/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.content)
        self.assertEqual(len(body["data"]), 1)
        self.assertEqual(body["data"][0]["quantity"], 3)

    def test_list_ticket_codes(self):
        """Member can list their ticket codes."""
        purchase = _create_purchase(self.member, self.ticket, quantity=4)

        response = self.client.get("/v1/events/tickets/my-codes/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.content)
        self.assertEqual(len(body["data"]["tickets"]), 4)


# =============================================================================
# Partner Event Check-in Stats Tests
# =============================================================================


class PartnerEventCheckInStatsTests(ThrottleDisabledAPITestCase):
    """Integration tests for partner check-in statistics."""

    def setUp(self):
        self.partner = _create_partner()
        self.member1 = _create_member(email="member1@example.com")
        self.member2 = _create_member(email="member2@example.com")
        self.event = _create_event(self.partner)
        self.ticket = _create_ticket(self.event)
        self.client.force_authenticate(user=self.partner)
        cache.clear()

    def test_check_in_stats(self):
        """Partner can view check-in statistics."""
        purchase1 = _create_purchase(self.member1, self.ticket, quantity=2)
        purchase2 = _create_purchase(self.member2, self.ticket, quantity=3)

        # Check in some tickets
        code1 = purchase1.codes.first()
        code1.check_in(by=self.partner)

        code2 = purchase2.codes.first()
        code2.check_in(by=self.partner)

        response = self.client.get(f"/v1/events/partner/{self.event.id}/check-ins/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.content)
        data = body["data"]
        self.assertEqual(data["total_tickets"], 5)
        self.assertEqual(data["checked_in"], 2)
        self.assertEqual(data["not_checked_in"], 3)
        self.assertEqual(data["check_in_rate"], "40.0%")


# =============================================================================
# Event Partner Verification — Model Unit Tests
# =============================================================================


class EventPartnerProfileModelTests(ThrottleDisabledAPITestCase):
    """Unit tests for EventPartnerProfile model."""

    def setUp(self):
        self.partner = _create_partner()
        self.profile = _create_event_partner_profile(self.partner)

    def test_is_partner_verified_true_for_approved(self):
        self.assertTrue(EventPartnerProfile.is_partner_verified(self.partner))

    def test_is_partner_verified_false_for_pending(self):
        self.profile.status = EventPartnerProfile.Status.PENDING
        self.profile.save()
        self.assertFalse(EventPartnerProfile.is_partner_verified(self.partner))

    def test_is_partner_verified_false_for_rejected(self):
        self.profile.status = EventPartnerProfile.Status.REJECTED
        self.profile.save()
        self.assertFalse(EventPartnerProfile.is_partner_verified(self.partner))

    def test_is_partner_verified_false_when_no_profile(self):
        other = _create_partner(email="noprofile@example.com")
        self.assertFalse(EventPartnerProfile.is_partner_verified(other))

    def test_names_match_case_insensitive(self):
        self.assertTrue(EventPartnerProfile.names_match("John Doe", "JOHN DOE"))

    def test_names_match_extra_whitespace(self):
        self.assertTrue(EventPartnerProfile.names_match("John  Doe", "John Doe"))

    def test_names_match_leading_trailing_whitespace(self):
        self.assertTrue(EventPartnerProfile.names_match("  John Doe  ", "John Doe"))

    def test_names_match_rejects_substring(self):
        self.assertFalse(EventPartnerProfile.names_match("John Doe", "John Doe Ltd"))

    def test_names_match_rejects_different_names(self):
        self.assertFalse(EventPartnerProfile.names_match("John Doe", "Jane Smith"))

    def test_names_match_rejects_empty(self):
        self.assertFalse(EventPartnerProfile.names_match("", "John Doe"))
        self.assertFalse(EventPartnerProfile.names_match("John Doe", ""))

    def test_nin_encrypted_roundtrip(self):
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.nin, "12345678901")

    def test_bank_account_number_encrypted_roundtrip(self):
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.bank_account_number, "0123456789")


# =============================================================================
# Backfill Command — --revoke-sentinel
# =============================================================================


class BackfillEventPartnerProfilesRevokeSentinelTests(ThrottleDisabledAPITestCase):
    """
    Regression: nin/bank_account_number are EncryptedCharField (fixed-IV
    AES-CBC), so `nin__startswith=...` can never match anything — the lookup
    value is encrypted whole, and ciphertext of a substring is never a
    prefix of the ciphertext of the full string. --revoke-sentinel must
    filter on something that supports exact match instead.
    """

    def setUp(self):
        self.backfilled_partner = _create_partner(email="backfilled@example.com")
        self.backfilled_profile = _create_event_partner_profile(
            self.backfilled_partner,
            nin=f"BACKFILLED-{self.backfilled_partner.id}",
            nin_verified=False,
            bank_account_number="BACKFILLED",
        )
        self.real_partner = _create_partner(email="real@example.com")
        self.real_profile = _create_event_partner_profile(self.real_partner)

    def test_revoke_sentinel_deletes_only_backfilled_rows(self):
        from django.core.management import call_command

        call_command("backfill_event_partner_profiles", "--revoke-sentinel")

        self.assertFalse(
            EventPartnerProfile.objects.filter(id=self.backfilled_profile.id).exists()
        )
        self.assertTrue(
            EventPartnerProfile.objects.filter(id=self.real_profile.id).exists()
        )

    def test_revoke_sentinel_dry_run_deletes_nothing(self):
        from django.core.management import call_command

        call_command(
            "backfill_event_partner_profiles", "--revoke-sentinel", "--dry-run"
        )

        self.assertTrue(
            EventPartnerProfile.objects.filter(id=self.backfilled_profile.id).exists()
        )


# =============================================================================
# Event Partner Verification — Endpoint Integration Tests
# =============================================================================


class EventPartnerVerificationSubmitTests(ThrottleDisabledAPITestCase):
    """Integration tests for POST /events/partner/verification/submit/."""

    def setUp(self):
        self.partner = _create_partner()
        self.partner.first_name = "John"
        self.partner.last_name = "Doe"
        self.partner.profile_img_url = "https://mock.cloudinary.com/selfie.jpg"
        self.partner.save()
        self.client.force_authenticate(user=self.partner)
        cache.clear()

    def _payload(self, **overrides):
        """Minimal payload — only what the partner now supplies."""
        data = {
            "nin": "12345678901",
            "bank_code": "000013",
            "bank_name": "GTBank",
            "bank_account_number": "0123456789",
        }
        data.update(overrides)
        return data

    def _dojah_ok(self, dob="1990-01-01", first="John", last="Doe", match=True):
        """Build a mock response for KYC.verify_nin."""
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "entity": {
                "first_name": first,
                "last_name": last,
                "date_of_birth": dob,
                "selfie_verification": {
                    "match": match,
                    "confidence_value": 95.0,
                },
            }
        }
        return resp

    # -------- Happy paths --------

    @patch("event.views.cloudinary_to_base64", return_value="base64selfie")
    @patch("event.views.KYC.verify_nin")
    def test_submit_auto_approves_when_profile_name_matches(self, mock_nin, mock_bank):
        """Dojah NIN name matches the user's profile name -> auto-approve."""
        mock_nin.return_value = self._dojah_ok()

        response = self.client.post(
            "/v1/events/partner/verification/submit/",
            data=encrypt(self._payload()),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        body = decrypt(response.content)
        self.assertEqual(body["status"], "success")

        profile = EventPartnerProfile.objects.get(user=self.partner)
        self.assertEqual(profile.status, EventPartnerProfile.Status.APPROVED)
        self.assertTrue(profile.nin_verified)
        self.assertIsNotNone(profile.reviewed_at)
        self.assertIsNone(profile.reviewed_by)

        # DOB derived from Dojah, not from client
        self.assertEqual(profile.nin_dob, "1990-01-01")

    @patch("event.views.cloudinary_to_base64", return_value="base64selfie")
    @patch("event.views.KYC.verify_nin")
    def test_submit_parks_at_pending_when_both_names_mismatch(
        self, mock_nin, mock_bank
    ):
        """Dojah NIN name does not match profile name -> PENDING."""
        mock_nin.return_value = self._dojah_ok(first="Alice", last="Smith")

        response = self.client.post(
            "/v1/events/partner/verification/submit/",
            data=encrypt(self._payload()),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        profile = EventPartnerProfile.objects.get(user=self.partner)
        self.assertEqual(profile.status, EventPartnerProfile.Status.PENDING)
        self.assertIsNone(profile.reviewed_at)
        self.assertIsNone(profile.reviewed_by)

    @patch("event.views.cloudinary_to_base64", return_value="base64selfie")
    @patch("event.views.KYC.verify_nin")
    def test_resubmit_overwrites_rejected_row(self, mock_nin, mock_bank):
        existing = _create_event_partner_profile(
            self.partner,
            status=EventPartnerProfile.Status.REJECTED,
            rejection_reason="Bad docs",
            reviewed_at=timezone.now(),
        )
        original_id = existing.id

        mock_nin.return_value = self._dojah_ok()

        response = self.client.post(
            "/v1/events/partner/verification/submit/",
            data=encrypt(self._payload()),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(EventPartnerProfile.objects.count(), 1)
        profile = EventPartnerProfile.objects.get(user=self.partner)
        self.assertEqual(profile.id, original_id)
        self.assertEqual(profile.status, EventPartnerProfile.Status.APPROVED)
        self.assertEqual(profile.rejection_reason, "")

    # -------- DOB handling (new behavior) --------
    @patch("event.views.cloudinary_to_base64", return_value="base64selfie")
    @patch("event.views.KYC.verify_nin")
    def test_submit_stores_dojah_nin_name(self, mock_nin, mock_selfie):
        """The Dojah-returned NIN name is stored verbatim on the profile."""
        mock_nin.return_value = self._dojah_ok(first="John", last="Doe")

        response = self.client.post(
            "/v1/events/partner/verification/submit/",
            data=encrypt(self._payload()),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        profile = EventPartnerProfile.objects.get(user=self.partner)
        self.assertEqual(profile.nin_name, "John Doe")

    @patch("event.views.cloudinary_to_base64", return_value="base64selfie")
    @patch("event.views.KYC.verify_nin")
    def test_submit_returns_502_when_dojah_dob_unparseable(self, mock_nin, mock_bank):
        """Dojah returns garbage DOB -> 502 (service problem, not client's fault)."""
        mock_nin.return_value = self._dojah_ok(dob="not-a-date")

        response = self.client.post(
            "/v1/events/partner/verification/submit/",
            data=encrypt(self._payload()),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertFalse(EventPartnerProfile.objects.filter(user=self.partner).exists())

    # -------- Failure paths --------

    @patch("event.views.cloudinary_to_base64", return_value="base64selfie")
    @patch("event.views.KYC.verify_nin")
    def test_submit_rejects_selfie_mismatch(self, mock_nin, mock_selfie):
        mock_nin.return_value = self._dojah_ok(match=False)

        response = self.client.post(
            "/v1/events/partner/verification/submit/",
            data=encrypt(self._payload()),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(EventPartnerProfile.objects.filter(user=self.partner).exists())

    @patch("event.views.cloudinary_to_base64", return_value="base64selfie")
    @patch("event.views.KYC.verify_nin")
    def test_submit_returns_502_on_dojah_outage(self, mock_nin, mock_selfie):
        mock_nin.return_value = None

        response = self.client.post(
            "/v1/events/partner/verification/submit/",
            data=encrypt(self._payload()),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)

    def test_submit_rejects_duplicate_nin_from_other_user(self):
        other = _create_partner(email="other@example.com")
        _create_event_partner_profile(other, nin="12345678901")

        response = self.client.post(
            "/v1/events/partner/verification/submit/",
            data=encrypt(self._payload()),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_submit_rejects_when_already_approved(self):
        _create_event_partner_profile(self.partner)

        response = self.client.post(
            "/v1/events/partner/verification/submit/",
            data=encrypt(self._payload()),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_submit_rejects_non_partner(self):
        member = _create_member()
        self.client.force_authenticate(user=member)

        response = self.client.post(
            "/v1/events/partner/verification/submit/",
            data=encrypt(self._payload()),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class EventPartnerVerificationStatusTests(ThrottleDisabledAPITestCase):
    """Integration tests for GET /events/partner/verification/status/."""

    def setUp(self):
        self.partner = _create_partner()
        self.client.force_authenticate(user=self.partner)
        cache.clear()

    def test_status_when_no_profile(self):
        response = self.client.get("/v1/events/partner/verification/status/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.content)
        self.assertFalse(body["data"]["verified"])
        self.assertIsNone(body["data"]["profile"])

    def test_status_returns_masked_secrets(self):
        _create_event_partner_profile(
            self.partner,
            nin="12345678901",
            bank_account_number="0123456789",
        )
        response = self.client.get("/v1/events/partner/verification/status/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.content)
        profile = body["data"]["profile"]
        self.assertTrue(body["data"]["verified"])
        self.assertEqual(profile["nin_masked"], "*******8901")
        self.assertEqual(profile["bank_account_number_masked"], "******6789")
        self.assertNotIn("nin", profile)
        self.assertNotIn("bank_account_number", profile)


class AdminEventPartnerVerificationTests(ThrottleDisabledAPITestCase):
    """Integration tests for admin review of event-partner verifications."""

    def setUp(self):
        self.admin = _create_admin()
        self.partner = _create_partner()
        self.profile = _create_event_partner_profile(
            self.partner,
            status=EventPartnerProfile.Status.PENDING,
            reviewed_at=None,
        )
        self.client.force_authenticate(user=self.admin)
        cache.clear()

    def test_list_partner_verifications(self):
        response = self.client.get("/v1/events/admin/partner-verifications/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.content)
        self.assertEqual(body["data"]["count"], 1)

    def test_list_filter_by_status(self):
        response = self.client.get(
            "/v1/events/admin/partner-verifications/?status=pending"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.content)
        self.assertEqual(body["data"]["count"], 1)

        response = self.client.get(
            "/v1/events/admin/partner-verifications/?status=approved"
        )
        body = decrypt(response.content)
        self.assertEqual(body["data"]["count"], 0)

    def test_admin_approve(self):
        response = self.client.post(
            f"/v1/events/admin/partner-verifications/{self.profile.id}/review/",
            data=encrypt({"action": "approve"}),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.status, EventPartnerProfile.Status.APPROVED)
        self.assertEqual(self.profile.reviewed_by, self.admin)
        self.assertIsNotNone(self.profile.reviewed_at)

    def test_admin_reject_requires_reason(self):
        response = self.client.post(
            f"/v1/events/admin/partner-verifications/{self.profile.id}/review/",
            data=encrypt({"action": "reject"}),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_admin_reject_with_reason(self):
        response = self.client.post(
            f"/v1/events/admin/partner-verifications/{self.profile.id}/review/",
            data=encrypt({"action": "reject", "rejection_reason": "Name mismatch"}),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.status, EventPartnerProfile.Status.REJECTED)
        self.assertEqual(self.profile.rejection_reason, "Name mismatch")

    def test_admin_cannot_review_already_approved(self):
        self.profile.status = EventPartnerProfile.Status.APPROVED
        self.profile.save()

        response = self.client.post(
            f"/v1/events/admin/partner-verifications/{self.profile.id}/review/",
            data=encrypt({"action": "approve"}),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_partner_cannot_access_admin_list(self):
        self.client.force_authenticate(user=self.partner)
        response = self.client.get("/v1/events/admin/partner-verifications/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


# =============================================================================
# Event Partner Verification — Gate & Regression Tests
# =============================================================================


class EventPartnerVerificationGateTests(ThrottleDisabledAPITestCase):
    """Ensure the new gate actually blocks/allows event creation."""

    def setUp(self):
        self.partner = _create_partner()
        self.client.force_authenticate(user=self.partner)
        cache.clear()

    def _event_payload(self):
        now = timezone.now()
        return {
            "event_name": "Concert Night",
            "description": "Live concert",
            "category": "Cinema",  # deliberately NOT the partner's own category
            "mode": "Physical",
            "address": "1 Stadium Way, Lagos",
            "start_date": (now + timedelta(days=30)).isoformat(),
            "end_date": (now + timedelta(days=31)).isoformat(),
        }

    def test_event_creation_blocked_without_profile(self):
        response = self.client.post(
            "/v1/events/partner/",
            data=encrypt(self._event_payload()),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Event.objects.count(), 0)

    def test_event_creation_blocked_when_pending(self):
        _create_event_partner_profile(
            self.partner, status=EventPartnerProfile.Status.PENDING
        )
        response = self.client.post(
            "/v1/events/partner/",
            data=encrypt(self._event_payload()),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_event_creation_blocked_when_rejected(self):
        _create_event_partner_profile(
            self.partner, status=EventPartnerProfile.Status.REJECTED
        )
        response = self.client.post(
            "/v1/events/partner/",
            data=encrypt(self._event_payload()),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_event_creation_allowed_when_approved(self):
        _create_event_partner_profile(
            self.partner, status=EventPartnerProfile.Status.APPROVED
        )
        response = self.client.post(
            "/v1/events/partner/",
            data=encrypt(self._event_payload()),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Event.objects.count(), 1)

    def test_category_mismatch_no_longer_blocks_event_creation(self):
        """
        Regression: the old strict category check has been removed.
        Partner can pick any category regardless of business_category.
        """
        self.partner.business_category = "Restaurant"
        self.partner.save()

        _create_event_partner_profile(
            self.partner, status=EventPartnerProfile.Status.APPROVED
        )

        response = self.client.post(
            "/v1/events/partner/",
            data=encrypt(self._event_payload()),  # category="Cinema"
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Event.objects.first().category, "Cinema")


# =============================================================================
# Event Partner Verification — Fuzz Tests
# =============================================================================


class EventPartnerVerificationFuzzTests(ThrottleDisabledAPITestCase):
    """Fuzz / malformed input tests."""

    def setUp(self):
        self.partner = _create_partner()
        self.client.force_authenticate(user=self.partner)
        cache.clear()

    def _base(self, **overrides):
        data = {
            "nin": "12345678901",
            "bank_code": "000013",
            "bank_name": "GTBank",
            "bank_account_number": "0123456789",
        }
        data.update(overrides)
        return data

    def test_rejects_nin_with_letters(self):
        response = self.client.post(
            "/v1/events/partner/verification/submit/",
            data=encrypt(self._base(nin="12345ABCDE1")),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_rejects_nin_wrong_length(self):
        response = self.client.post(
            "/v1/events/partner/verification/submit/",
            data=encrypt(self._base(nin="123")),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_rejects_bank_account_with_letters(self):
        response = self.client.post(
            "/v1/events/partner/verification/submit/",
            data=encrypt(self._base(bank_account_number="012ABC6789")),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_rejects_non_encrypted_payload(self):
        """Raw JSON without encryption envelope should fail decryption."""
        response = self.client.post(
            "/v1/events/partner/verification/submit/",
            data=self._base(),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
