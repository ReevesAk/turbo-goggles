import json as _json
import time
import uuid
from datetime import timedelta
from unittest.mock import patch, MagicMock

from django.contrib.auth.hashers import check_password, make_password
from django.utils import timezone

from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import OTP, User
from security import decrypt, encrypt
from .models import TransferModel, WalletModel


def _make_payload(**kwargs):
    return _json.dumps(encrypt(kwargs))


def _create_user(**overrides):
    data = {
        "phone_number": "2347000000001",
        "password": "StrongPass123!",
        "first_name": "Bank",
        "last_name": "User",
        "full_name": "Bank User",
        "email": "bank.user@example.com",
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


def _expire_otp(otp):
    otp_obj = OTP.objects.get(otp=otp)
    otp_obj.expires_at = timezone.now() - timedelta(seconds=1)
    otp_obj.save(update_fields=["expires_at"])
    return otp_obj


def _create_wallet(user, **overrides):
    data = {
        "user": user,
        "account_number": "1234567890",
        "acct_name": f"{user.first_name} {user.last_name}",
        "transactionTrackingRef": "PICA123456",
        "balance": "1500.00",
        "cashback_balance": "25.50",
        "pin": None,
    }
    data.update(overrides)
    return WalletModel.objects.create(**data)


class BankingModelTests(APITestCase):
    def test_wallet_defaults(self):
        user = _create_user(
            phone_number="2347000000010", email="wallet.default@example.com"
        )
        wallet = _create_wallet(user)

        self.assertEqual(wallet.tier_level, 1)
        self.assertTrue(wallet.status)

    def test_transfer_string_representation(self):
        user = _create_user(
            phone_number="2347000000011", email="transfer.user@example.com"
        )
        transfer = TransferModel.objects.create(
            user=user,
            tx_reference="TX-REF-1234",
            beneficiary_name="John Doe",
        )

        self.assertIn("TX-REF-1234", str(transfer))
        self.assertIn("John Doe", str(transfer))


class GetCashbackBalanceTests(APITestCase):
    url = "/v1/banking/get-cashback-balance"

    def test_requires_authentication(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_returns_cashback_balance_for_authenticated_user(self):
        user = _create_user(
            phone_number="2347000000012", email="cashback.user@example.com"
        )
        _create_wallet(user, cashback_balance="99.10")
        self.client.force_authenticate(user=user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.data)
        self.assertEqual(body["status"], "success")
        self.assertEqual(body["cashback_balance"], "99.10")


@patch("banking.views.Wallet.getWalletDetails")
class GetAccountDetailsTests(APITestCase):
    url = "/v1/banking/account-details"

    def test_returns_404_when_wallet_does_not_exist(self, mock_live_wallet):
        user = _create_user(
            phone_number="2347000000013", email="acct.missing@example.com"
        )
        self.client.force_authenticate(user=user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        body = decrypt(response.data)
        self.assertEqual(body["status"], "fail")

    def test_returns_live_account_details_when_live_enquiry_succeeds(
        self, mock_live_wallet
    ):
        user = _create_user(phone_number="2347000000014", email="acct.live@example.com")
        wallet = _create_wallet(user, account_number="1111222233")
        self.client.force_authenticate(user=user)

        # Mock with .json() method as expected by the view
        mock_live_wallet.return_value = MagicMock(
            json=lambda: {
                "status": "SUCCESS",
                "data": {
                    "name": wallet.acct_name,
                    "nuban": wallet.account_number,
                    "number": "CUST-001",
                    "availableBalance": "2500.00",
                    "tier": "1",
                },
            }
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.data)
        self.assertEqual(body["status"], "success")
        self.assertEqual(body["data"]["account_number"], "1111222233")

    def test_returns_warning_payload_when_live_enquiry_fails(self, mock_live_wallet):
        user = _create_user(
            phone_number="2347000000015", email="acct.fallback@example.com"
        )
        _create_wallet(user, account_number="9999888877", balance="4500.00")
        self.client.force_authenticate(user=user)
        mock_live_wallet.return_value = {"status": "FAILED"}

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.data)
        self.assertEqual(body["status"], "warning")
        self.assertTrue(body["data"]["live_enquiry_failed"])


@patch("banking.views.create_activity.delay")
@patch("banking.views.create_notification.delay")
@patch("banking.views.send_alert_notification.delay")
@patch("banking.views.Messaging")
class WalletPinFlowTests(APITestCase):
    """
    send_alert_notification/create_notification/create_activity .delay
    are mocked since they're real Celery tasks (SetWalletPin/
    ForgotWalletPin/PinResendOTP background their SMS/email/notification/
    activity-log writes now instead of doing them inline - see
    send_alert_notification's docstring in banking/tasks.py) - letting
    them actually enqueue would hit the broker, which isn't available in
    tests.
    """

    set_pin_url = "/v1/banking/set-wallet-pin"
    forgot_pin_url = "/v1/banking/forgot-wallet-pin"
    resend_otp_url = "/v1/banking/resend-otp"
    verify_otp_url = "/v1/banking/verify-otp"
    reset_pin_url = "/v1/banking/reset-wallet-pin"

    def setUp(self):
        self.user = _create_user(
            phone_number="2347000000016", email="pin.flow@example.com"
        )
        self.wallet = _create_wallet(self.user)
        self.client.force_authenticate(user=self.user)

    def test_set_wallet_pin_requires_wallet(self, mock_msg, mock_send_alert, mock_create_notification, mock_create_activity):
        self.wallet.delete()

        response = self.client.post(
            self.set_pin_url,
            data=_make_payload(pin="1234", pin2="1234"),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        body = decrypt(response.data)
        self.assertIn("Wallet not found", body["error"])

    def test_set_wallet_pin_rejects_mismatch(self, mock_msg, mock_send_alert, mock_create_notification, mock_create_activity):
        response = self.client.post(
            self.set_pin_url,
            data=_make_payload(pin="1234", pin2="4321"),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = decrypt(response.data)
        self.assertIn("Pins do not match", body["error"])

    def test_set_wallet_pin_success_hashes_pin(self, mock_msg, mock_send_alert, mock_create_notification, mock_create_activity):
        response = self.client.post(
            self.set_pin_url,
            data=_make_payload(pin="1234", pin2="1234"),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        body = decrypt(response.data)
        self.assertEqual(body["status"], "success")
        self.wallet.refresh_from_db()
        self.user.refresh_from_db()
        self.assertTrue(check_password("1234", self.wallet.pin))
        self.assertTrue(self.user.has_created_pin)

    def test_forgot_wallet_pin_creates_otp(self, mock_msg, mock_send_alert, mock_create_notification, mock_create_activity):
        response = self.client.post(self.forgot_pin_url)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        body = decrypt(response.data)
        self.assertEqual(body["status"], "success")
        self.assertTrue(OTP.objects.filter(user_id=self.user.id).exists())

    def test_resend_wallet_pin_otp_creates_new_otp(self, mock_msg, mock_send_alert, mock_create_notification, mock_create_activity):
        response = self.client.post(self.resend_otp_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.data)
        self.assertEqual(body["status"], "success")
        self.assertTrue(OTP.objects.filter(user_id=self.user.id).exists())

    def test_verify_wallet_pin_otp_rejects_invalid_otp(self, mock_msg, mock_send_alert, mock_create_notification, mock_create_activity):
        response = self.client.post(
            self.verify_otp_url,
            data=_make_payload(otp="9999"),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = decrypt(response.data)
        self.assertIn("Invalid or expired OTP", body["error"])

    def test_verify_wallet_pin_otp_success(self, mock_msg, mock_send_alert, mock_create_notification, mock_create_activity):
        from accounts.otp import otp_manager

        otp = otp_manager.create_otp(user_id=str(self.user.id))
        _expire_otp(otp)

        response = self.client.post(
            self.verify_otp_url,
            data=_make_payload(otp=otp),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.data)
        self.assertEqual(body["status"], "success")

    def test_reset_wallet_pin_requires_valid_otp(self, mock_msg, mock_send_alert, mock_create_notification, mock_create_activity):
        response = self.client.post(
            self.reset_pin_url,
            data=_make_payload(otp="9999", pin="1234", pin2="1234"),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = decrypt(response.data)
        self.assertIn("Invalid or expired OTP", body["error"])

    def test_reset_wallet_pin_rejects_pin_mismatch(self, mock_msg, mock_send_alert, mock_create_notification, mock_create_activity):
        from accounts.otp import otp_manager

        otp = otp_manager.create_otp(user_id=str(self.user.id))
        _expire_otp(otp)

        response = self.client.post(
            self.reset_pin_url,
            data=_make_payload(otp=otp, pin="1234", pin2="4321"),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = decrypt(response.data)
        self.assertIn("Pins do not match", body["error"])


class BankingEndpointSmokeTests(APITestCase):
    """Smoke tests to ensure every banking route is exercised at least once."""

    def _assert_status_in(self, response, allowed):
        self.assertIn(response.status_code, allowed)

    def test_verify_bvn_endpoint(self):
        response = self.client.post("/v1/banking/verify-bvn")
        self._assert_status_in(response, [401, 403])

    def test_verify_nin_endpoint(self):
        response = self.client.post("/v1/banking/verify-nin")
        self._assert_status_in(response, [401, 403])

    def test_create_wallet_endpoint(self):
        response = self.client.post("/v1/banking/create-wallet")
        self._assert_status_in(response, [401, 403])

    def test_upgrade_to_tier2_endpoint(self):
        response = self.client.post("/v1/banking/upgrade-to-tier2")
        self._assert_status_in(response, [401, 403])

    def test_request_upgrade_to_tier3_endpoint(self):
        response = self.client.get("/v1/banking/request-upgrade-to-tier3")
        self._assert_status_in(response, [401, 403])

    def test_notification_endpoint(self):
        response = self.client.post("/v1/banking/notification", data={}, format="json")
        self._assert_status_in(response, [400, 404, 415])

    def test_get_all_banks_endpoint(self):
        response = self.client.get("/v1/banking/transfers/get-all-banks")
        self._assert_status_in(response, [401, 403])

    def test_get_9psb_wallet_endpoint(self):
        response = self.client.post("/v1/banking/transfers/get-9psb-wallet")
        self._assert_status_in(response, [401, 403])

    def test_validate_other_bank_account_endpoint(self):
        response = self.client.post("/v1/banking/transfers/validate-account")
        self._assert_status_in(response, [401, 403])

    def test_intra_bank_transfer_endpoint(self):
        response = self.client.post("/v1/banking/transfers/intra-bank")
        self._assert_status_in(response, [401, 403])

    def test_inter_bank_transfer_endpoint(self):
        response = self.client.post("/v1/banking/transfers/inter-bank")
        self._assert_status_in(response, [401, 403])

    def test_transfer_status_endpoint(self):
        response = self.client.get("/v1/banking/transfers/123/status")
        self._assert_status_in(response, [401, 403])

    def test_pay_with_card_endpoint(self):
        response = self.client.post("/v1/banking/pay-with-card")
        self._assert_status_in(response, [400, 401, 403])

    def test_fund_wallet_endpoint(self):
        response = self.client.post(
            "/v1/banking/fund-picadailys-wallet-with-other-cards-yesandyes",
            data=_make_payload(),
            content_type="application/json",
        )
        self._assert_status_in(response, [400, 401, 403, 404])

    def test_create_refund_endpoint(self):
        response = self.client.post("/v1/banking/create-refund")
        self._assert_status_in(response, [400, 401, 403])

    def test_all_transactions_endpoint(self):
        response = self.client.get("/v1/banking/transactions/get-all")
        self._assert_status_in(response, [401, 403])

    def test_retrieve_transaction_endpoint(self):
        response = self.client.get(
            "/v1/banking/transactions/get-single/11111111-1111-1111-1111-111111111111/"
        )
        self._assert_status_in(response, [401, 403])

    def test_paystack_webhook_endpoint(self):
        response = self.client.post(
            "/v1/banking/paystack/webhook/",
            data={},
            format="json",
            HTTP_X_PAYSTACK_SIGNATURE="invalid-signature",
        )
        self._assert_status_in(response, [400])

    def test_webhook_dispatcher_endpoint(self):
        response = self.client.post("/v1/banking/webhook", data={})
        self._assert_status_in(response, [400])

    def test_webhook_transfer_endpoint(self):
        response = self.client.post("/v1/banking/webhook/transfer", data={})
        self._assert_status_in(response, [400, 401])

    def test_webhook_account_upgrade_endpoint(self):
        response = self.client.post("/v1/banking/webhook/account-upgrade", data={})
        self._assert_status_in(response, [400, 401])

    def test_webhook_address_verification_endpoint(self):
        response = self.client.post("/v1/banking/webhook/address-verification", data={})
        self._assert_status_in(response, [400, 404, 500])

    def test_verify_card_deposit_endpoint(self):
        response = self.client.get("/v1/banking/verify-card-deposit/abc-ref-123/")
        self._assert_status_in(response, [400, 401, 403, 404])

    def test_redirecting_endpoint(self):
        response = self.client.get("/v1/banking/redirecting")
        self._assert_status_in(response, [200])

    def test_dojah_redirect_endpoint(self):
        response = self.client.get("/v1/banking/dojah/redirect")
        self._assert_status_in(response, [200])

    def test_generate_statement_endpoint(self):
        response = self.client.post("/v1/banking/generate-statement")
        self._assert_status_in(response, [401, 403])
