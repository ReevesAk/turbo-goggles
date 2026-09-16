import logging
import random
import string
import time
import requests
from decouple import config
from django.core.cache import cache

vas_username = config("VAS_USERNAME")
vas_password = config("VAS_PASSWORD")
vas_base_url = config("VAS_BASE_URL")

_VAS_TOKEN_KEY = "vas_bearer_token"
_VAS_TOKEN_TTL = 25 * 60  # 25 minutes

logger = logging.getLogger(__name__)


def _build_vas_url(resource):
    return f"{vas_base_url.rstrip('/')}/{resource.lstrip('/')}"


def _log_request(label, url, payload=None, headers=None):
    logger.warning(
        "VAS %s REQUEST: url=%s | payload=%s | headers=%s", label, url, payload, headers
    )


def _log_response(label, response):
    try:
        body = response.json()
    except Exception:
        body = response.text
    logger.warning(
        "VAS %s RESPONSE: status=%s | body=%s", label, response.status_code, body
    )


class VAS:
    @staticmethod
    def is_success(response):
        """
        An explicit envelope failure (e.g. {"status": "fail", ...}) always
        wins, regardless of what any nested transaction status claims.
        Otherwise, a nested transaction status - when the payload has one -
        is authoritative over the envelope: seen in production, a 200
        response whose envelope says {"status": "success", ...} while the
        nested transaction record said {"transactionStatus": "failed",
        "description": "Transaction with reference '...' not found"} - the
        wallet was still debited, but treating the envelope alone as
        success told the customer the purchase succeeded when it hadn't.
        Also seen: 9PSB's status-check response, which carries a nested
        transactionStatus but no top-level status/message envelope at all -
        treating that missing envelope as failure discarded a genuine
        nested success. Only fall back to the bare envelope when there's no
        nested status to read.
        """
        if not response or response.status_code != 200:
            return False
        try:
            body = response.json()
        except Exception:
            return False
        raw_status = body.get("status")
        msg = (body.get("message") or "").lower()
        status = raw_status or ""
        envelope_success = "success" in msg or status in ("00", "SUCCESS", "success")
        envelope_explicit_failure = (raw_status is not None or bool(msg)) and (
            not envelope_success
        )
        if envelope_explicit_failure:
            return False

        data = body.get("data") if isinstance(body.get("data"), dict) else None
        if data is None and isinstance(body.get("content"), dict):
            content = body["content"]
            data = content.get("transactions", content)
        if isinstance(data, dict):
            nested_status = str(data.get("transactionStatus", "")).lower()
            if nested_status:
                return nested_status in ("success", "successful", "00")

        return envelope_success

    @staticmethod
    def is_pending(response):
        """
        True if the provider explicitly said it's still processing this
        transaction (e.g. responseCode 202) rather than confirming success
        or failure - distinct from is_success() being False, which alone
        doesn't mean the transaction failed.
        """
        if not response:
            return False
        try:
            body = response.json()
            status = (body.get("status") or "").lower()
            return status == "pending" or str(body.get("responseCode")) == "202"
        except Exception:
            return False

    @staticmethod
    def generate_unique_code(prefix="Pica"):
        min_length = 18
        max_length = 25
        prefix_part = f"{prefix}-"
        remaining_length = random.randint(min_length, max_length) - len(prefix_part)
        remaining_length = max(1, remaining_length)
        random_part = "".join(random.choices(string.digits, k=remaining_length))
        return f"{prefix_part}{random_part}"

    @staticmethod
    def _fetch_fresh_token():
        payload = {"username": vas_username, "password": vas_password}
        headers = {"Content-Type": "application/json"}
        url = _build_vas_url("identity/api/v1/authenticate")
        _log_request(
            "authenticate",
            url,
            payload={"username": vas_username, "password": "***"},
            headers=headers,
        )
        try:
            resp = requests.post(url=url, json=payload, headers=headers, timeout=10)
            _log_response("authenticate", resp)
            resp.raise_for_status()
            if resp.json().get("message") == "Authentication Successful":
                token = resp.json()["data"].get("accessToken")
                if token:
                    cache.set(_VAS_TOKEN_KEY, token, _VAS_TOKEN_TTL)
                return token
            return None
        except requests.RequestException as e:
            logger.warning("VAS authenticate ERROR: %s", e)
            return None

    @staticmethod
    def authenticate(force_refresh=False):
        """Return cached VAS token; fetch a fresh one only when missing or force_refresh=True."""
        if not force_refresh:
            token = cache.get(_VAS_TOKEN_KEY)
            if token:
                return token
        return VAS._fetch_fresh_token()

    @staticmethod
    def status(tx_ref, bearer_token):
        resource = f"vas/api/v1/topup/status?transReference={tx_ref}"
        url = _build_vas_url(resource)
        headers = {
            "Authorization": f"Bearer {bearer_token}",
            "Content-Type": "application/json",
        }
        _log_request("status", url, headers=headers)
        try:
            resp = requests.get(url=url, headers=headers, timeout=10)
            if resp.status_code == 401:
                fresh = VAS.authenticate(force_refresh=True)
                if fresh:
                    headers["Authorization"] = f"Bearer {fresh}"
                    resp = requests.get(url=url, headers=headers, timeout=10)
            _log_response("status", resp)
            return resp
        except requests.RequestException as e:
            logger.warning("VAS status ERROR: %s", e)
            return None

    @staticmethod
    def confirm_status(tx_ref, bearer_token, delays=(10, 15, 20)):
        """Poll for a final status with backoff before calling a purchase failed -
        9PSB says settlement can lag, so a quick miss isn't a real failure.

        ~85s worst case (45s sleep + 4 requests @ 10s timeout), under gunicorn's
        120s --timeout with room to spare - a killed worker is worse than a
        premature pending."""
        status_resp = None
        for attempt, delay in enumerate(delays):
            status_resp = VAS.status(tx_ref=tx_ref, bearer_token=bearer_token)
            if status_resp and VAS.is_success(status_resp):
                return status_resp
            if attempt < len(delays) - 1:
                time.sleep(delay)
        return status_resp

    @staticmethod
    def resolve_outcome(response, tx_ref, bearer_token):
        """
        Decide the final outcome of a purchase whose initial response wasn't
        an immediate success. If the provider explicitly flagged it as still
        processing (is_pending), poll patiently via confirm_status - a bare
        "not success" on a pending response doesn't mean it failed, just that
        it hasn't resolved yet. Otherwise (no response, or an explicit
        non-pending failure), fall back to a single status check.

        Returns (final_response, outcome) where outcome is one of
        "success", "pending", "failed".
        """
        if VAS.is_pending(response):
            polled = VAS.confirm_status(tx_ref=tx_ref, bearer_token=bearer_token)
        else:
            polled = VAS.status(tx_ref=tx_ref, bearer_token=bearer_token)

        if polled and VAS.is_success(polled):
            return polled, "success"
        if polled and VAS.is_pending(polled):
            return polled, "pending"
        if not polled or polled.status_code != 200:
            return (polled or response), "pending"
        return polled, "failed"

    @staticmethod
    def airtime_topup(
        network, bearer_token, amount, debitAccount, phone_number, tx_ref
    ):
        resource = "vas/api/v1/topup/airtime"
        url = _build_vas_url(resource)
        payload = {
            "network": network,
            "amount": amount,
            "phoneNumber": phone_number,
            "transactionReference": tx_ref,
        }
        if debitAccount:
            payload["debitAccount"] = debitAccount
        headers = {
            "Authorization": f"Bearer {bearer_token}",
            "Content-Type": "application/json",
        }
        _log_request("airtime_topup", url, payload=payload, headers=headers)
        try:
            response = requests.post(url=url, json=payload, headers=headers, timeout=30)
            if response.status_code == 401:
                fresh = VAS.authenticate(force_refresh=True)
                if fresh:
                    headers["Authorization"] = f"Bearer {fresh}"
                    response = requests.post(
                        url=url, json=payload, headers=headers, timeout=30
                    )
            _log_response("airtime_topup", response)
            return response
        except requests.RequestException as e:
            logger.warning("VAS airtime_topup ERROR: %s", e)
            return None

    @staticmethod
    def dataplans(bearer_token, phone_number):
        resource = f"/vas/api/v1/topup/dataPlans?phone={phone_number}"
        url = _build_vas_url(resource)
        headers = {
            "Authorization": f"Bearer {bearer_token}",
            "Content-Type": "application/json",
        }
        _log_request("dataplans", url, headers=headers)
        try:
            response = requests.get(url=url, headers=headers, timeout=15)
            if response.status_code == 401:
                fresh = VAS.authenticate(force_refresh=True)
                if fresh:
                    headers["Authorization"] = f"Bearer {fresh}"
                    response = requests.get(url=url, headers=headers, timeout=15)
            _log_response("dataplans", response)
            return response
        except requests.RequestException as e:
            logger.warning("VAS dataplans ERROR: %s", e)
            return None

    @staticmethod
    def data(
        network,
        bearer_token,
        amount,
        productId,
        phone_number,
        tx_ref,
        debitAccount=None,
    ):
        resource = "vas/api/v1/topup/data"
        url = _build_vas_url(resource)
        payload = {
            "network": network,
            "amount": amount,
            "phoneNumber": phone_number,
            "productId": productId,
            "transactionReference": tx_ref,
        }
        if debitAccount:
            payload["debitAccount"] = debitAccount
        headers = {
            "Authorization": f"Bearer {bearer_token}",
            "Content-Type": "application/json",
        }
        _log_request("data", url, payload=payload, headers=headers)
        try:
            response = requests.post(url=url, json=payload, headers=headers, timeout=30)
            if response.status_code == 401:
                fresh = VAS.authenticate(force_refresh=True)
                if fresh:
                    headers["Authorization"] = f"Bearer {fresh}"
                    response = requests.post(
                        url=url, json=payload, headers=headers, timeout=30
                    )
            _log_response("data", response)
            return response
        except requests.RequestException as e:
            logger.warning("VAS data ERROR: %s", e)
            return None

    @staticmethod
    def get_categories(bearer_token):
        resource = "vas/api/v1/billspayment/catergories"
        url = _build_vas_url(resource)
        headers = {
            "Authorization": f"Bearer {bearer_token}",
            "Content-Type": "application/json",
        }
        _log_request("get_categories", url, headers=headers)
        try:
            response = requests.get(url=url, headers=headers, timeout=15)
            if response.status_code == 401:
                fresh = VAS.authenticate(force_refresh=True)
                if fresh:
                    headers["Authorization"] = f"Bearer {fresh}"
                    response = requests.get(url=url, headers=headers, timeout=15)
            _log_response("get_categories", response)
            return response
        except requests.RequestException as e:
            logger.warning("VAS get_categories ERROR: %s", e)
            return None

    @staticmethod
    def bill_payment_categories(bearer_token, category_id):
        resource = f"vas/api/v1/billspayment/billers/{category_id}"
        url = _build_vas_url(resource)
        headers = {
            "Authorization": f"Bearer {bearer_token}",
            "Content-Type": "application/json",
        }
        _log_request("bill_payment_categories", url, headers=headers)
        try:
            response = requests.get(url=url, headers=headers, timeout=15)
            if response.status_code == 401:
                fresh = VAS.authenticate(force_refresh=True)
                if fresh:
                    headers["Authorization"] = f"Bearer {fresh}"
                    response = requests.get(url=url, headers=headers, timeout=15)
            _log_response("bill_payment_categories", response)
            return response
        except requests.RequestException as e:
            logger.warning("VAS bill_payment_categories ERROR: %s", e)
            return None

    @staticmethod
    def billers_categories(bearer_token, biller_id):
        resource = f"vas/api/v1/billspayment/fields/{biller_id}"
        url = _build_vas_url(resource)
        headers = {
            "Authorization": f"Bearer {bearer_token}",
            "Content-Type": "application/json",
        }
        _log_request("billers_categories", url, headers=headers)
        try:
            response = requests.get(url=url, headers=headers, timeout=15)
            if response.status_code == 401:
                fresh = VAS.authenticate(force_refresh=True)
                if fresh:
                    headers["Authorization"] = f"Bearer {fresh}"
                    response = requests.get(url=url, headers=headers, timeout=15)
            _log_response("billers_categories", response)
            return response
        except requests.RequestException as e:
            logger.warning("VAS billers_categories ERROR: %s", e)
            return None

    @staticmethod
    def verify_bill_payer(bearer_token, billerId, customerId, itemId, amount):
        resource = "vas/api/v1/billspayment/validate"
        url = _build_vas_url(resource)
        payload = {
            "billerId": billerId,
            "customerId": customerId,
            "amount": amount,
        }
        if itemId:
            payload["itemId"] = itemId
        headers = {
            "Authorization": f"Bearer {bearer_token}",
            "Content-Type": "application/json",
        }
        _log_request("verify_bill_payer", url, payload=payload, headers=headers)
        try:
            response = requests.post(url=url, headers=headers, json=payload, timeout=15)
            if response.status_code == 401:
                fresh = VAS.authenticate(force_refresh=True)
                if fresh:
                    headers["Authorization"] = f"Bearer {fresh}"
                    response = requests.post(
                        url=url, headers=headers, json=payload, timeout=15
                    )
            _log_response("verify_bill_payer", response)
            return response
        except requests.RequestException as e:
            logger.warning("VAS verify_bill_payer ERROR: %s", e)
            return None

    @staticmethod
    def bill_payment(
        bearer_token,
        customerId,
        billerId,
        itemId,
        amount,
        customerPhone,
        customerName,
        otherField,
        transactionReference,
        debitAccount=None,
    ):
        resource = "vas/api/v1/billspayment/pay"
        url = _build_vas_url(resource)
        payload = {
            "customerId": customerId,
            "billerId": billerId,
            "itemId": itemId,
            "customerPhone": customerPhone,
            "customerName": customerName,
            "otherField": otherField,
            "amount": amount,
            "transactionReference": transactionReference,
        }
        if debitAccount:
            payload["debitAccount"] = debitAccount
        headers = {
            "Authorization": f"Bearer {bearer_token}",
            "Content-Type": "application/json",
        }
        _log_request("bill_payment", url, payload=payload, headers=headers)
        try:
            response = requests.post(url=url, json=payload, headers=headers, timeout=30)
            if response.status_code == 401:
                fresh = VAS.authenticate(force_refresh=True)
                if fresh:
                    headers["Authorization"] = f"Bearer {fresh}"
                    response = requests.post(
                        url=url, json=payload, headers=headers, timeout=30
                    )
            _log_response("bill_payment", response)
            return response
        except requests.RequestException as e:
            logger.warning("VAS bill_payment ERROR: %s", e)
            return None
