import uuid
import logging
import requests
from decouple import config

vtpass_api_key = config("VT_PASS_API_KEY")
vtpass_public_key = config("VT_PASS_PUBLIC_KEY")
vtpass_secret_key = config("VT_PASS_SECRET_KEY")
vtpass_base_url = config("VT_PASS_BASE_URL").rstrip(
    "/"
)  # https://sandbox.vtpass.com/api or https://vtpass.com/api

logger = logging.getLogger(__name__)


def _log_request(label, url, payload=None):
    logger.warning("VTPass %s REQUEST: url=%s | payload=%s", label, url, payload)


def _log_response(label, response):
    try:
        body = response.json()
    except Exception:
        body = response.text
    logger.warning(
        "VTPass %s RESPONSE: status=%s | body=%s", label, response.status_code, body
    )


class VTPass:
    @staticmethod
    def _get_headers(method="POST"):
        if method == "GET":
            return {
                "api-key": vtpass_api_key,
                "public-key": vtpass_public_key,
            }
        return {
            "api-key": vtpass_api_key,
            "secret-key": vtpass_secret_key,
            "Content-Type": "application/json",
        }

    @staticmethod
    def generate_request_id(prefix="PICA"):
        return f"{prefix}-{uuid.uuid4().hex[:20]}"

    @staticmethod
    def is_success(response):
        """VTPass returns code '000' for a successful transaction."""
        try:
            return response.json().get("code") == "000"
        except Exception:
            return False

    @staticmethod
    def requery(request_id):
        """Check the status of a previous transaction."""
        url = f"{vtpass_base_url}/requery"
        headers = VTPass._get_headers("GET")
        _log_request("requery", url, payload={"request_id": request_id})
        try:
            resp = requests.get(
                url, headers=headers, params={"request_id": request_id}, timeout=15
            )
            _log_response("requery", resp)
            return resp
        except requests.RequestException as e:
            logger.warning("VTPass requery ERROR: %s", e)
            return None

    @staticmethod
    def service_variations(serviceID):
        """
        Get available plans/variations for a service.
        serviceID examples: mtn-data | glo-data | airtel-data | etisalat-data | dstv | gotv | startimes
        """
        url = f"{vtpass_base_url}/service-variations"
        headers = VTPass._get_headers("GET")
        _log_request("service_variations", url, payload={"serviceID": serviceID})
        try:
            resp = requests.get(
                url, headers=headers, params={"serviceID": serviceID}, timeout=15
            )
            _log_response("service_variations", resp)
            return resp
        except requests.RequestException as e:
            logger.warning("VTPass service_variations ERROR: %s", e)
            return None

    @staticmethod
    def airtime(serviceID, amount, phone, request_id):
        """
        Buy airtime.
        serviceID: mtn | glo | airtel | etisalat
        """
        url = f"{vtpass_base_url}/pay"
        payload = {
            "request_id": request_id,
            "serviceID": serviceID,
            "amount": amount,
            "phone": phone,
        }
        headers = VTPass._get_headers("POST")
        _log_request("airtime", url, payload=payload)
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=15)
            _log_response("airtime", resp)
            return resp
        except requests.RequestException as e:
            logger.warning("VTPass airtime ERROR: %s", e)
            return None

    @staticmethod
    def data(serviceID, variation_code, amount, phone, request_id):
        """
        Buy a data bundle.
        serviceID: mtn-data | glo-data | airtel-data | etisalat-data
        variation_code: from service_variations() response
        """
        url = f"{vtpass_base_url}/pay"
        payload = {
            "request_id": request_id,
            "serviceID": serviceID,
            "billersCode": phone,
            "variation_code": variation_code,
            "amount": amount,
            "phone": phone,
        }
        headers = VTPass._get_headers("POST")
        _log_request("data", url, payload=payload)
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=15)
            _log_response("data", resp)
            return resp
        except requests.RequestException as e:
            logger.warning("VTPass data ERROR: %s", e)
            return None

    @staticmethod
    def verify_merchant(serviceID, billersCode, meter_type=None):
        """
        Verify a meter number (electricity) or decoder/smart card number (cable TV).
        meter_type: 'prepaid' | 'postpaid' — required for electricity only.
        """
        url = f"{vtpass_base_url}/merchant-verify"
        payload = {
            "billersCode": billersCode,
            "serviceID": serviceID,
        }
        if meter_type:
            payload["type"] = meter_type
        headers = VTPass._get_headers("POST")
        _log_request("verify_merchant", url, payload=payload)
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=15)
            _log_response("verify_merchant", resp)
            return resp
        except requests.RequestException as e:
            logger.warning("VTPass verify_merchant ERROR: %s", e)
            return None

    @staticmethod
    def pay(
        serviceID,
        variation_code,
        amount,
        phone,
        request_id,
        billersCode=None,
        quantity=1,
    ):
        """
        Pay a bill — electricity or cable TV.
        serviceID: ikeja-electric | eko-electric | dstv | gotv | startimes | etc.
        variation_code: prepaid | postpaid (electricity) or package code (cable)
        billersCode: meter number (electricity) or smart card / IUC number (cable)
        """
        url = f"{vtpass_base_url}/pay"
        payload = {
            "request_id": request_id,
            "serviceID": serviceID,
            "billersCode": billersCode,
            "variation_code": variation_code,
            "amount": amount,
            "phone": phone,
            "quantity": quantity,
        }
        headers = VTPass._get_headers("POST")
        _log_request("pay", url, payload=payload)
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=30)
            _log_response("pay", resp)
            return resp
        except requests.RequestException as e:
            logger.warning("VTPass pay ERROR: %s", e)
            return None
