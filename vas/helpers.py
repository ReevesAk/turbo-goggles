import logging
import random
import string
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
        if not response or response.status_code != 200:
            return False
        try:
            body = response.json()
            msg = (body.get("message") or "").lower()
            status = body.get("status") or ""
            return "success" in msg or status in ("00", "SUCCESS", "success")
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
        resource = f"identity/api/v1/topup/status?transReference={tx_ref}"
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
            response = requests.post(url=url, json=payload, headers=headers, timeout=15)
            if response.status_code == 401:
                fresh = VAS.authenticate(force_refresh=True)
                if fresh:
                    headers["Authorization"] = f"Bearer {fresh}"
                    response = requests.post(
                        url=url, json=payload, headers=headers, timeout=15
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
            response = requests.post(url=url, json=payload, headers=headers, timeout=15)
            if response.status_code == 401:
                fresh = VAS.authenticate(force_refresh=True)
                if fresh:
                    headers["Authorization"] = f"Bearer {fresh}"
                    response = requests.post(
                        url=url, json=payload, headers=headers, timeout=15
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
