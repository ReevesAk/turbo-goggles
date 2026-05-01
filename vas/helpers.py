import logging
import random
import string
import requests
from decouple import config

from rest_framework import status
from rest_framework.response import Response

vas_username = config("VAS_USERNAME")
vas_password = config("VAS_PASSWORD")
vas_base_url = config("VAS_BASE_URL")


def _build_vas_url(resource):
    return f"{vas_base_url.rstrip('/')}/{resource.lstrip('/')}"


class VAS:
    @staticmethod
    def generate_unique_code(prefix="Pica"):
        min_length = 18
        max_length = 25

        # Calculate available length for the random part
        prefix_part = f"{prefix}-"
        remaining_length = random.randint(min_length, max_length) - len(prefix_part)
        remaining_length = max(1, remaining_length)

        random_part = "".join(random.choices(string.digits, k=remaining_length))

        return f"{prefix_part}{random_part}"

    @staticmethod
    def authenticate():
        PAYLOAD = {
            "username": vas_username,
            "password": vas_password,
        }
        HEADERS = {"Content-Type": "application/json"}
        AUTH_URL = vas_base_url + "/identity/api/v1/authenticate"

        try:
            resp = requests.post(
                url=AUTH_URL, json=PAYLOAD, headers=HEADERS, timeout=10
            )
            resp.raise_for_status()
            if resp.json().get("message") == "Authentication Successful":
                token = resp.json()["data"].get("accessToken")
                logging.info("VAS authentication successful. Token: %s", token)
                return token
            logging.warning("VAS authentication failed: %s", resp.json().get("message"))
            return None
        except requests.RequestException as e:
            logging.error("VAS authentication failed: %s", e)
            return None

    @staticmethod
    def status(tx_ref, bearer_token):
        resource = f"identity/api/v1/topup/status?transReference={tx_ref}"

        HEADERS = {
            "Authorization": f"Bearer {bearer_token}",
            "Content-Type": "application/json",
        }

        logging.info(
            f"VAS status REQUEST: url=%s, headers=%s", _build_vas_url(resource), HEADERS
        )
        try:
            resp = requests.get(
                url=_build_vas_url(resource), headers=HEADERS, timeout=10
            )
            try:
                resp_json = resp.json()
            except Exception:
                resp_json = resp.text
            logging.info(
                f"VAS status RESPONSE: status=%s, body=%s", resp.status_code, resp_json
            )
            return resp
        except requests.RequestException as e:
            logging.error("VAS status check failed: %s", e)
            return None

    @staticmethod
    def airtime_topup(
        network, bearer_token, amount, debitAccount, phone_number, tx_ref
    ):
        resource = "vas/api/v1/topup/airtime"
        payload = {
            "network": network,
            "amount": amount,
            "phoneNumber": phone_number,
            "transactionReference": tx_ref,
        }
        # Some providers reject null debitAccount with 5xx; only send when available.
        if debitAccount:
            payload["debitAccount"] = debitAccount
        headers = {
            "Authorization": f"Bearer {bearer_token}",
            "Content-Type": "application/json",
        }
        # Log to logger and print to terminal
        logging.info(
            "VAS airtime_topup REQUEST: url=%s, payload=%s, headers=%s",
            _build_vas_url(resource),
            payload,
            headers,
        )
        import sys

        print("VAS airtime_topup REQUEST:")
        print(f"  url: {_build_vas_url(resource)}")
        print(f"  payload: {payload}")
        print(f"  headers: {headers}")
        sys.stdout.flush()
        try:
            response = requests.post(
                url=_build_vas_url(resource),
                json=payload,
                headers=headers,
                timeout=15,
            )
            # Log the actual request payload and raw response
            try:
                req_body = response.request.body
            except Exception:
                req_body = None
            try:
                resp_json = response.json()
            except Exception:
                resp_json = response.text
            logging.info("VAS airtime_topup RAW REQUEST BODY: %s", req_body)
            logging.info(
                "VAS airtime_topup RESPONSE: status=%s, body=%s",
                response.status_code,
                resp_json,
            )
            return response
        except requests.exceptions.RequestException as e:
            logging.error(f"Airtime topup API request error: {str(e)}")
            return None

    @staticmethod
    def data(
        network, bearer_token, amount, productId, debitAccount, phone_number, tx_ref
    ):
        resource = "vas/api/v1/topup/data"
        payload = {
            "network": network,
            "debitAccount": debitAccount,
            "amount": amount,
            "phoneNumber": phone_number,
            "productId": productId,
            "transactionReference": tx_ref,
        }
        # Log the payload and parameters being sent
        logging.info(
            "VAS.data REQUEST: url=%s, payload=%s, headers=%s",
            _build_vas_url(resource),
            payload,
            {
                "Authorization": f"Bearer {bearer_token}",
                "Content-Type": "application/json",
            },
        )
        headers = {
            "Authorization": f"Bearer {bearer_token}",
            "Content-Type": "application/json",
        }
        try:
            response = requests.post(
                url=_build_vas_url(resource),
                json=payload,
                headers=headers,
                timeout=15,
            )
            return response
        except requests.exceptions.RequestException as e:
            logging.error(f"Data topup API request error: {str(e)}")
            return None

    @staticmethod
    def bill_payment_categories(bearer_token, category_id):
        resource = f"vas/api/v1/billspayment/billers/{category_id}"
        headers = {
            "Authorization": f"Bearer {bearer_token}",
            "Content-Type": "application/json",
        }
        try:
            response = requests.get(
                url=_build_vas_url(resource),
                headers=headers,
            )
            return response
        except requests.exceptions.RequestException as e:
            logging.error(f"Biller Payment categories API request error: {str(e)}")
            return None

    @staticmethod
    def billers_categories(bearer_token, biller_id):
        resource = f"vas/api/v1/billspayment/fields/{biller_id}"
        headers = {
            "Authorization": f"Bearer {bearer_token}",
            "Content-Type": "application/json",
        }
        try:
            response = requests.get(
                url=_build_vas_url(resource),
                headers=headers,
            )
            return response
        except requests.exceptions.RequestException as e:
            logging.error(f"Billers categories API request error: {str(e)}")
            return None

    @staticmethod
    def verify_bill_payer(bearer_token, billerId, customerId, itemId, amount):
        resource = "vas/api/v1/billspayment/validate"
        headers = {
            "Authorization": f"Bearer {bearer_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "billerId": billerId,
            "customerId": customerId,
            "itemId": itemId,
            "amount": amount,
        }
        try:
            response = requests.post(
                url=_build_vas_url(resource),
                headers=headers,
                json=payload,
            )
            return response
        except requests.exceptions.RequestException as e:
            logging.error(f"Verify bill payer API request error: {str(e)}")
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
        debitAccount,
        transactionReference,
    ):
        resource = "vas/api/v1/billspayment/pay"
        payload = {
            "customerId": customerId,
            "billerId": billerId,
            "itemId": itemId,
            "customerPhone": customerPhone,
            "customerName": customerName,
            "otherField": otherField,
            "amount": amount,
            "debitAccount": debitAccount,
            "transactionReference": transactionReference,
        }
        headers = {
            "Authorization": f"Bearer {bearer_token}",
            "Content-Type": "application/json",
        }

        try:
            response = requests.post(
                url=vas_base_url + resource,
                json=payload,
                headers=headers,
            )
            return response
        except requests.exceptions.RequestException as e:
            logging.error(f"Bill payment API request error: {str(e)}")
            return None
