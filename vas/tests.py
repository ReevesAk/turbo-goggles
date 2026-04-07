from unittest.mock import patch

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from vas import helpers
from vas.helpers import VAS
from security import decrypt


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
