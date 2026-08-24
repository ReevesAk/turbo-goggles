import json
from unittest.mock import patch, MagicMock
from uuid import uuid4

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase
from django.urls import reverse

from vas import helpers
from vas.helpers import VAS
from vas.views import _bill_payment_category, collection_account
from security import decrypt, encrypt
from gamification.models import Points as PointsModel
from banking.models import FundWithCard


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


class BillPaymentCategoryTests(TestCase):
    """_bill_payment_category - classifies a BillPaymentView purchase as
    Electricity Bill vs Cable TV from its billerId, for failed/pending
    purchases where _handle_success's token-presence detection can't run
    (no provider response to inspect)."""

    def test_known_electricity_billerId_returns_electricity_bill(self):
        self.assertEqual(_bill_payment_category("ikeja-electric"), "Electricity Bill")

    def test_known_cable_billerId_returns_cable_tv(self):
        self.assertEqual(_bill_payment_category("dstv"), "Cable TV")

    def test_unknown_billerId_defaults_to_cable_tv(self):
        self.assertEqual(_bill_payment_category("some-new-biller"), "Cable TV")

    def test_none_billerId_defaults_to_cable_tv(self):
        self.assertEqual(_bill_payment_category(None), "Cable TV")


class VasEndpointCoverageTests(APITestCase):
    @patch("vas.views.VAS.authenticate", return_value="token")
    @patch("vas.views.VAS.dataplans")
    def test_get_network_provider_rejects_unsupported_network(
        self, mock_dataplans, _mock_auth
    ):
        """
        GetDataPlans (vas/views.py) has no network whitelist of its own -
        "UNKNOWN" is passed straight through to VAS.dataplans, same as any
        other network string. What actually happens is whatever the
        provider itself says about it; simulated here as a failure response
        rather than hitting the live VAS test endpoint (this test used to
        do that unmocked, which made it depend on real external network
        access and valid test credentials that don't hold up in CI/sandboxed
        runs).
        """
        mock_dataplans.return_value = MagicMock(
            status_code=200, json=lambda: {"status": "fail", "message": "error"}
        )

        response = self.client.get("/v1/vas/get-productIds/UNKNOWN/")

        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        body = decrypt(response.data)
        self.assertEqual(
            body["message"], "Failed to fetch data plans from VAS provider."
        )

    @patch("vas.views.VAS.authenticate", return_value=None)
    def test_bill_categories_returns_502_when_vas_unavailable(self, _mock_auth):
        response = self.client.get("/v1/vas/bill-payment-categories/electricity/")

        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        body = decrypt(response.data)
        self.assertEqual(body["status"], "fail")

    @patch("vas.views.VAS.authenticate", return_value="token")
    @patch("vas.views.VAS.bill_payment_categories")
    def test_bill_categories_success_response_shape(self, mock_cats, _mock_auth):
        # status_code=200 + a "status": "success" body - VAS.is_success()
        # checks response.status_code, which the old bare _MockResponse
        # (json() only) didn't have, and the raw provider body is passed
        # through under the response's "data" key (BillPaymentCategoriesView
        # doesn't reshape it into a top-level "categories" key).
        mock_cats.return_value = MagicMock(
            status_code=200,
            json=lambda: {"status": "success", "data": [{"id": "cat-1"}]},
        )

        response = self.client.get("/v1/vas/bill-payment-categories/electricity/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.data)
        self.assertEqual(body["status"], "success")
        self.assertEqual(len(body["data"]["data"]), 1)

    @patch("vas.views.VAS.authenticate", return_value="token")
    @patch("vas.views.VAS.billers_categories")
    def test_billers_categories_success_response_shape(self, mock_billers, _mock_auth):
        mock_billers.return_value = MagicMock(
            status_code=200,
            json=lambda: {"status": "success", "data": [{"id": "biller-1"}]},
        )

        response = self.client.get("/v1/vas/billers-categories/1/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = decrypt(response.data)
        self.assertEqual(body["status"], "success")
        self.assertEqual(len(body["data"]["data"]), 1)

    def test_vas_endpoints_surface_is_captured(self):
        routes = [
            ("POST", "/v1/vas/airtime-topup", {}, [400, 401, 403, 500, 502]),
            ("GET", "/v1/vas/get-productIds/MTN/", None, [200, 400, 404, 500, 502]),
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
    @patch("vas.views.Pay.refund_pts")
    @patch("vas.views.VAS.data")
    @patch("vas.views.VAS.status")
    @patch("vas.views.VAS.authenticate", return_value="token")
    def test_data_subscription_hybrid_points_wallet_flow(
        self, mock_auth, mock_status, mock_data, mock_refund_pts
    ):
        """
        Hybrid payment: points cover the full purchase, VAS is called with
        the central collection account (not the user's own wallet) - see
        DataSubscriptionView.post's "Hybrid: cashback/points cover full
        purchase" branch. Points are refunded if VAS fails - there's no
        separate Wallet.Debit/Credit call in this flow; the debit itself
        happens provider-side via VAS.data's debitAccount, and points are
        deducted/refunded locally via commons.Pay.with_pts/refund_pts.
        """
        mock_status.return_value = MagicMock(
            json=lambda: {"data": {"transactionStatus": "fail", "responseCode": 500}}
        )
        mock_data.return_value = None  # Simulate VAS failure

        user = self.create_and_login_user()
        # Influencer tier (TIER_VALUES rate 1.00/point) with 1000 points
        # covers the ₦1000 purchase exactly.
        PointsModel.objects.create(user=user, balance=1000, tier="Influencer")

        payload = encrypt(
            {
                "payment_option": "WALLET",
                "phone_number": "08010000000",
                "amount": "1000",
                "network": "MTN",
                "product_id": "mtn-1gb",
                "use_points": True,
                "pin": "1234",
            }
        )
        response = self.client.post(
            reverse("vas:data_subscription"),
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(mock_data.called)
        self.assertEqual(mock_data.call_args.kwargs["debitAccount"], collection_account)
        self.assertTrue(mock_refund_pts.called)

    @patch("vas.views.post_vas_update.delay")
    @patch("vas.views.VAS.data")
    @patch("vas.views.VAS.status")
    @patch("vas.views.VAS.authenticate", return_value="token")
    def test_data_subscription_wallet_only_flow(
        self, mock_auth, mock_status, mock_data, mock_post_vas_update
    ):
        """
        Wallet-only: no separate Wallet.Debit call - VAS.data is called
        directly with the user's own wallet account_number as debitAccount,
        so the provider debits it as part of the purchase request.
        post_vas_update.delay is mocked since it's a real Celery task (SMS/
        balance sync) - letting it actually enqueue would hit the broker.
        """
        mock_status.return_value = MagicMock(
            status_code=200,
            json=lambda: {"status": "success", "data": {}},
        )
        # status_code=200 + a body VAS.is_success recognizes ("status":
        # "success") - without status_code the mock's default (a truthy
        # MagicMock, never == 200) makes is_success() false, which pushes
        # the response through the resolve_outcome/is_pending fallback and
        # returns 202 instead of the 200 these tests expect.
        mock_data.return_value = MagicMock(
            status_code=200,
            json=lambda: {"status": "success", "data": {}},
        )

        user = self.create_and_login_user()

        payload = encrypt(
            {
                "payment_option": "WALLET",
                "phone_number": "08010000000",
                "amount": "1000",
                "network": "MTN",
                "product_id": "mtn-1gb",
                "pin": "1234",
            }
        )
        response = self.client.post(
            reverse("vas:data_subscription"),
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(mock_data.call_args.kwargs["debitAccount"], "1234567890")

    @patch("vas.views.VAS.data")
    @patch("vas.views.VAS.status")
    @patch("vas.views.VAS.authenticate", return_value="token")
    def test_data_subscription_card_flow_marks_funding_processed(
        self, mock_auth, mock_status, mock_data
    ):
        """
        Guest card payment: purchase succeeds against a pre-captured
        FundWithCard row and marks it processed. Unlike WALLET, CARD passes
        no debitAccount to VAS.data at all - funds already moved when the
        card charge was captured (see verify_card_payment), there's no
        wallet (central or otherwise) to debit at purchase time.
        """
        mock_status.return_value = MagicMock(
            status_code=200,
            json=lambda: {"status": "success", "data": {}},
        )
        # status_code=200 + a body VAS.is_success recognizes ("status":
        # "success") - without status_code the mock's default (a truthy
        # MagicMock, never == 200) makes is_success() false, which pushes
        # the response through the resolve_outcome/is_pending fallback and
        # returns 202 instead of the 200 these tests expect.
        mock_data.return_value = MagicMock(
            status_code=200,
            json=lambda: {"status": "success", "data": {}},
        )

        FundWithCard.objects.create(
            txn_reference="CARD-REF-1",
            user=None,
            status="success",
            amount=1000,
            is_processed=False,
        )
        payload = encrypt(
            {
                "payment_option": "CARD",
                "phone_number": "08010000000",
                "amount": "1000",
                "network": "MTN",
                "product_id": "mtn-1gb",
                "card_reference": "CARD-REF-1",
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
        self.assertNotIn("debitAccount", kwargs)
        self.assertTrue(
            FundWithCard.objects.get(txn_reference="CARD-REF-1").is_processed
        )

    def create_and_login_user(self):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        user = User.objects.create_user(phone_number="08010000001", password="testpass")
        from vas.test_utils import ensure_wallet_for_user

        ensure_wallet_for_user(user)
        # force_login sets a session cookie, but this API authenticates via
        # JWT (see permissions.IsAuthenticatedOrGuestWithValidId) - DRF's
        # force_authenticate is what actually makes request.user non-
        # anonymous for these views.
        self.client.force_authenticate(user=user)
        return user
