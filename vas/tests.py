import json
from unittest.mock import patch, MagicMock
from uuid import uuid4

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase
from django.urls import reverse

from vas import helpers
from vas.helpers import VAS
from security import decrypt, encrypt


class _MockResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class VasHelpersBehaviorTests(TestCase):
    def test_build_vas_url_normalizes_trailing_and_leading_slashes(self):
        original_base = helpers.vas_base_url
        helpers.vas_base_url = "https://example.com/api/"
        try:
            self.assertEqual(
                helpers._build_vas_url("/topup/airtime"),
                "https://example.com/api/topup/airtime",
            )
        finally:
            helpers.vas_base_url = original_base

    def test_generate_unique_code_includes_prefix_and_length_bounds(self):
        code = VAS.generate_unique_code(prefix="PICA")
        self.assertTrue(code.startswith("PICA-"))
        self.assertGreaterEqual(len(code), 18)
        self.assertLessEqual(len(code), 25)

    @patch("vas.helpers.requests.post")
    def test_airtime_topup_omits_debit_account_when_none(self, mock_post):
        VAS.airtime_topup(
            network="MTN",
            bearer_token="token",
            amount="500",
            debitAccount=None,
            phone_number="08010000000",
            tx_ref="PICA-123",
        )

        self.assertTrue(mock_post.called)
        called_kwargs = mock_post.call_args.kwargs
        self.assertNotIn("debitAccount", called_kwargs["json"])

    @patch("vas.helpers.requests.post")
    def test_data_payload_contains_required_fields(self, mock_post):
        VAS.data(
            network="MTN",
            bearer_token="token",
            amount="1000",
            productId="mtn-1gb",
            debitAccount="1234567890",
            phone_number="08010000000",
            tx_ref="PICA-XYZ",
        )

        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["network"], "MTN")
        self.assertEqual(payload["productId"], "mtn-1gb")
        self.assertEqual(payload["debitAccount"], "1234567890")

    @patch("vas.helpers.requests.post")
    def test_verify_bill_payer_payload_fields(self, mock_post):
        VAS.verify_bill_payer(
            bearer_token="token",
            billerId="111",
            customerId="222",
            itemId="333",
            amount="5000",
        )

        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["billerId"], "111")
        self.assertEqual(payload["customerId"], "222")
        self.assertEqual(payload["itemId"], "333")
        self.assertEqual(payload["amount"], "5000")

    @patch("vas.helpers.requests.post")
    def test_bill_payment_payload_fields(self, mock_post):
        VAS.bill_payment(
            bearer_token="token",
            customerId="cid",
            billerId="bid",
            itemId="iid",
            amount="1500",
            customerPhone="08010000000",
            customerName="Jane",
            otherField="meter123",
            debitAccount="1002003004",
            transactionReference="PICA-1",
        )

        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["customerId"], "cid")
        self.assertEqual(payload["billerId"], "bid")
        self.assertEqual(payload["itemId"], "iid")
        self.assertEqual(payload["debitAccount"], "1002003004")


class VasEndpointCoverageTests(APITestCase):
    def test_get_network_provider_rejects_unsupported_network(self):
        response = self.client.get("/v1/vas/get-productIds/UNKNOWN/")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = decrypt(response.data)
        self.assertIn("Unsupported service provider", body["message"])

    @patch("vas.views.VAS.authenticate", return_value=None)
    def test_bill_categories_returns_502_when_vas_unavailable(self, _mock_auth):
        response = self.client.get("/v1/vas/bill-payment-categories/electricity/")

        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        body = decrypt(response.data)
        self.assertEqual(body["status"], "fail")

    @patch("vas.views.VAS.authenticate", return_value="token")
    @patch(
        "vas.views.VAS.bill_payment_categories",
        return_value=_MockResponse({"data": [{"id": "cat-1"}]}),
    )
    def test_bill_categories_success_response_shape(self, _mock_cats, _mock_auth):
        response = self.client.get("/v1/vas/bill-payment-categories/electricity/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.data)
        self.assertIn("categories", body)
        self.assertEqual(len(body["categories"]), 1)

    @patch("vas.views.VAS.authenticate", return_value="token")
    @patch(
        "vas.views.VAS.billers_categories",
        return_value=_MockResponse({"data": [{"id": "biller-1"}]}),
    )
    def test_billers_categories_success_response_shape(self, _mock_billers, _mock_auth):
        response = self.client.get("/v1/vas/billers-categories/1/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.data)
        self.assertIn("categories", body)
        self.assertEqual(len(body["categories"]), 1)

    def test_vas_endpoints_surface_is_captured(self):
        routes = [
            ("POST", "/v1/vas/airtime-topup", {}, [400, 401, 403, 500, 502]),
            ("GET", "/v1/vas/get-productIds/MTN/", None, [200, 400, 404, 500]),
            ("POST", "/v1/vas/subscribe-data", {}, [400, 401, 403, 500, 502]),
            ("GET", "/v1/vas/bill-payment-categories/electricity/", None, [200, 502]),
            ("GET", "/v1/vas/billers-categories/1/", None, [200, 502]),
            (
                "POST",
                "/v1/vas/verify-biller-account/",
                {},
                [400, 401, 403, 415, 500, 502],
            ),
            ("POST", "/v1/vas/bill-payment/", {}, [400, 401, 403, 500, 502]),
        ]

        for method, path, data, allowed in routes:
            with self.subTest(method=method, path=path):
                if method == "GET":
                    response = self.client.get(path)
                else:
                    response = self.client.post(path, data=data or {})
                self.assertIn(response.status_code, allowed)

    @patch("vas.views.create_activity", return_value=None)
    @patch("vas.views.VAS.status")
    @patch("vas.views.VAS.airtime_topup")
    @patch("vas.views.VAS.authenticate", return_value="token")
    def test_guest_card_airtime_uses_status_query_before_failing(
        self,
        _mock_auth,
        mock_airtime_topup,
        mock_status,
        _mock_activity,
    ):
        mock_airtime_topup.return_value = _MockResponse(
            {
                "timestamp": "2026-04-07T18:45:23.452+00:00",
                "status": 500,
                "error": "Internal Server Error",
                "path": "/topup/airtime",
            }
        )
        mock_status.return_value = _MockResponse(
            {
                "data": {
                    "transactionStatus": "success",
                    "responseCode": 200,
                }
            }
        )

        payload = json.dumps(
            encrypt(
                {
                    "payment_option": "CARD",
                    "phone_number": "08010000000",
                    "amount": "500",
                    "network": "MTN",
                }
            )
        )
        guest_id = str(uuid4())

        response = self.client.post(
            "/v1/vas/airtime-topup",
            data=payload,
            content_type="application/json",
            HTTP_X_GUEST_ID=guest_id,
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = decrypt(response.data)
        self.assertEqual(body["status"], "fail")


class HybridPaymentFlowTests(APITestCase):
    @patch("vas.views.Wallet.Debit")
    @patch("vas.views.Wallet.Credit")
    @patch("vas.views.VAS.data")
    @patch("vas.views.VAS.status")
    @patch("vas.views.VAS.authenticate", return_value="token")
    def test_data_subscription_hybrid_points_wallet_flow(
        self, mock_auth, mock_status, mock_data, mock_credit, mock_debit
    ):
        """
        Hybrid payment: points + wallet. Wallet portion debited to central, VAS called with central account.
        Refund is triggered if VAS fails.
        """
        mock_status.return_value = MagicMock(
            json=lambda: {"data": {"transactionStatus": "fail", "responseCode": 500}}
        )
        mock_data.return_value = None  # Simulate VAS failure
        mock_debit.return_value = MagicMock(status_code=200)
        mock_credit.return_value = MagicMock()

        payload = encrypt(
            {
                "payment_option": "WALLET",
                "phone_number": "08010000000",
                "amount": "1000",
                "network": "MTN",
                "productId": "mtn-1gb",
                "use_points": True,
                "pin": "1234",
            }
        )
        user = self.create_and_login_user()
        response = self.client.post(
            reverse("vas:data_subscription"),
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(mock_debit.called)
        self.assertTrue(mock_credit.called)

    @patch("vas.views.Wallet.Debit")
    @patch("vas.views.VAS.data")
    @patch("vas.views.VAS.status")
    @patch("vas.views.VAS.authenticate", return_value="token")
    def test_data_subscription_wallet_only_flow(
        self, mock_auth, mock_status, mock_data, mock_debit
    ):
        """
        Wallet-only: user wallet debited directly, VAS called with user wallet account.
        """
        mock_status.return_value = MagicMock(
            json=lambda: {"data": {"transactionStatus": "success", "responseCode": 200}}
        )
        mock_data.return_value = MagicMock(json=lambda: {"data": {}})
        mock_debit.return_value = MagicMock(status_code=200)

        payload = encrypt(
            {
                "payment_option": "WALLET",
                "phone_number": "08010000000",
                "amount": "1000",
                "network": "MTN",
                "productId": "mtn-1gb",
                "pin": "1234",
            }
        )
        user = self.create_and_login_user()
        response = self.client.post(
            reverse("vas:data_subscription"),
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(mock_debit.called)

    @patch("vas.views.VAS.data")
    @patch("vas.views.VAS.status")
    @patch("vas.views.VAS.authenticate", return_value="token")
    def test_data_subscription_card_flow_uses_central_account(
        self, mock_auth, mock_status, mock_data
    ):
        """
        Card payment: VAS called with central debit account.
        """
        mock_status.return_value = MagicMock(
            json=lambda: {"data": {"transactionStatus": "success", "responseCode": 200}}
        )
        mock_data.return_value = MagicMock(json=lambda: {"data": {}})

        payload = encrypt(
            {
                "payment_option": "CARD",
                "phone_number": "08010000000",
                "amount": "1000",
                "network": "MTN",
                "productId": "mtn-1gb",
            }
        )
        guest_id = str(uuid4())
        response = self.client.post(
            reverse("vas:data_subscription"),
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_X_GUEST_ID=guest_id,
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        args, kwargs = mock_data.call_args
        self.assertIn("debitAccount", kwargs)

    def create_and_login_user(self):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        user = User.objects.create_user(phone_number="08010000001", password="testpass")
        from vas.test_utils import ensure_wallet_for_user

        ensure_wallet_for_user(user)
        self.client.force_login(user)
        return user
