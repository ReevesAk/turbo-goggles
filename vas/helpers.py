import sys
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
        AUTH_URL = "http://102.216.128.75:9090/identity/api/v1/authenticate"

        try:
            resp = requests.post(
                url=AUTH_URL, json=PAYLOAD, headers=HEADERS, timeout=10
            )
            resp.raise_for_status()
            if resp.json().get("message") == "successful":
                token = resp.json().get("accessToken")
                return token
        except requests.RequestException as e:
            logging.error("Request failed: %s", e)
            sys.exit(1)

    @staticmethod
    def status(tx_ref, bearer_token):
        resource = f"topup/status?transReference={tx_ref}"

        HEADERS = {
            "Authorization": f"Bearer {bearer_token}",
            "Content-Type": "application/json",
        }

        try:
            resp = requests.get(
                url=vas_base_url + resource, headers=HEADERS, timeout=10
            )
            return resp
        except requests.RequestException as e:
            logging.error("Request failed: %s", e)
            sys.exit(1)

    @staticmethod
    def airtime_topup(
        network, bearer_token, amount, debitAccount, phone_number, tx_ref
    ):
        resource = "topup/airtime"
        payload = {
            "network": network,
            "debitAccount": debitAccount,
            "amount": amount,
            "phoneNumber": phone_number,
            "transactionReference": tx_ref,
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
            logging.error(f"Airtime topup API request error: {str(e)}")
            return response

    @staticmethod
    def data(
        network, bearer_token, amount, productId, debitAccount, phone_number, tx_ref
    ):
        resource = "topup/data"
        payload = {
            "network": network,
            "debitAccount": debitAccount,
            "amount": amount,
            "phoneNumber": phone_number,
            "productId": productId,
            "transactionReference": tx_ref,
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
            logging.error(f"Airtime topup API request error: {str(e)}")
            return response

    @staticmethod
    def bill_payment_categories(bearer_token, category_id):
        resource = f"billspayment/billers/{category_id}"
        headers = {
            "Authorization": f"Bearer {bearer_token}",
            "Content-Type": "application/json",
        }
        try:
            response = requests.get(
                url=vas_base_url + resource,
                headers=headers,
            )
            return response
        except requests.exceptions.RequestException as e:
            logging.error(f"Biller Payment categories API request error: {str(e)}")
            return response

    @staticmethod
    def billers_categories(bearer_token, biller_id):
        resource = f"billspayment/fields/{biller_id}"
        headers = {
            "Authorization": f"Bearer {bearer_token}",
            "Content-Type": "application/json",
        }
        try:
            response = requests.get(
                url=vas_base_url + resource,
                headers=headers,
            )
            return response
        except requests.exceptions.RequestException as e:
            logging.error(f"Billers categories API request error: {str(e)}")
            return response

    @staticmethod
    def verify_bill_payer(bearer_token, billerId, customerId, itemId, itemName, amount):
        resource = "billspayment/validate"
        headers = {
            "Authorization": f"Bearer {bearer_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "billerId": billerId,
            "customerId": customerId,
            "itemId": itemId,
            "itemName": itemName,
            "amount": amount,
        }
        try:
            response = requests.get(
                url=vas_base_url + resource,
                headers=headers,
                json=payload,
            )
            return response
        except requests.exceptions.RequestException as e:
            logging.error(f"Verify bill payer API request error: {str(e)}")
            return response

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
        resource = "billspayment/pay"
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
            logging.error(f"Electricity Purchase API request error: {str(e)}")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
