from datetime import datetime
import random
import logging
import requests
from decouple import config

from rest_framework import status
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError

api_key = config("MONNIFY_API_KEY")
secret_key = config("MONNIFY_SECRET_KEY")
base_url = config("MONNIFY_BASE_URL")
contractCode = config("CONTRACT_CODE")

auth = (api_key, secret_key)


def generate_timestamp_code(prefix="TX"):
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    sequence = str(random.randint(1000, 9999))
    return f"{prefix}{timestamp}{sequence}"


class UseCard:
    @staticmethod
    def initialize_payment(
        amount,
        customerName,
        customerEmail,
        paymentDescription,
    ):
        payment_ref = generate_timestamp_code()

        login_resource = "api/v1/auth/login"
        try:
            response = requests.post(
                url=base_url + login_resource,
                auth=auth,
            )
            if response.status_code == 200:
                token = response.json()["responseBody"]["accessToken"]
                try:
                    initialize_payament_resource = (
                        "api/v1/merchant/transactions/init-transaction"
                    )
                    payload = {
                        "amount": amount,
                        "customerName": customerName,
                        "customerEmail": customerEmail,
                        "paymentReference": payment_ref,
                        "paymentDescription": paymentDescription,
                        "currencyCode": "NGN",
                        "contractCode": contractCode,
                        "redirectUrl": "",
                        "paymentMethods": ["CARD"],
                    }

                    payment_headers = {
                        "bearer": token,
                    }
                    payment_response = requests.post(
                        url=base_url + initialize_payament_resource,
                        headers=payment_headers,
                        json=payload,
                    )
                    return payment_response
                except requests.exceptions.RequestException as e:
                    logging.error(
                        f"Initialize card payment API request error: {str(e)}"
                    )
                    return Response(
                        {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )

            else:
                raise ValidationError(
                    "Sorry, error while initializing payment, try again later."
                )

        except requests.exceptions.RequestException as e:
            logging.error(f"Merchant login API request error: {str(e)}")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @staticmethod
    def charge(transactionReference, number, expiryMonth, expiryYear, pin, cvv):
        login_resource = "api/v1/auth/login"

        try:
            response = requests.post(
                url=base_url + login_resource,
                auth=auth,
            )
            if response.status_code == 200:
                token = response.json()["responseBody"]["accessToken"]
                try:
                    resource = "api/v1/merchant/cards/charge"
                    headers = {
                        "bearer": token,
                    }

                    payload = {
                        "transactionReference": transactionReference,
                        "collectionChannel": "API_NOTIFICATION",
                        "card": {
                            "number": number,
                            "expiryMonth": expiryMonth,
                            "expiryYear": expiryYear,
                            "pin": pin,
                            "cvv": cvv,
                        },
                    }

                    response = requests.post(
                        url=base_url + resource, header=headers, json=payload
                    )
                    return response
                except requests.exceptions.RequestException as e:
                    logging.error(f"Charge from card API request error: {str(e)}")
                    return Response(
                        {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )
        except requests.exceptions.RequestException as e:
            logging.error(f"Merchant login API request error: {str(e)}")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @staticmethod
    def validate_otp(transactionReference, tokenId, token):
        login_resource = "api/v1/auth/login"

        try:
            response = requests.post(
                url=base_url + login_resource,
                auth=auth,
            )
            if response.status_code == 200:
                token = response.json()["responseBody"]["accessToken"]
                try:
                    resource = "api/v1/merchant/cards/charge"
                    headers = {
                        "bearer": token,
                    }

                    payload = {
                        "transactionReference": transactionReference,
                        "collectionChannel": "API_NOTIFICATION",
                        "tokenId": tokenId,
                        "token": token,
                    }

                    response = requests.post(
                        url=base_url + resource, header=headers, json=payload
                    )
                    return response
                except requests.exceptions.RequestException as e:
                    logging.error(f"Charge from card API request error: {str(e)}")
                    return Response(
                        {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )
        except requests.exceptions.RequestException as e:
            logging.error(f"Merchant login API request error: {str(e)}")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
