import logging
import requests
from decouple import config

from rest_framework import status
from rest_framework.response import Response

from .helpers import generate_random_string, insert_hyphens

api_key = config("FINCRA_API_KEY")
api_secret_key = config("FINCRA_SECRET_KEY")
bus_key = config("PICADIALYS_BUSINESS_KEY")

fincra_base_url = config("FINCRA_BASE_URL")

bus_id = config("PICADIALYS_BUSINESS_ID")


random_string = generate_random_string(20)
customer_reference = insert_hyphens(random_string, 4)


class BVN:
    @staticmethod
    def verify(bvn):
        resource = "core/bvn-verification"
        verify_bvn_headers = {
            "accept": "application/json",
            "api-key": api_secret_key,
            "content-type": "application/json",
        }

        payload = {
            "bvn": bvn,
            "business": bus_id,
        }

        try:
            response = requests.post(
                url=fincra_base_url + resource,
                json=payload,
                headers=verify_bvn_headers,
            )
            if response.status_code == 200:
                resp = response.json()
                date_of_birth = resp["data"]["dateOfBirth"]
                phone_number = resp["data"]["phoneNo"]
                first_name = resp["data"]["firstName"]
                last_name = resp["data"]["lastName"]

                return {
                    "date_of_birth": date_of_birth,
                    "phone_num": phone_number,
                    "first_name": first_name,
                    "last_name": last_name,
                }
            else:
                logging.error(
                    f"BVN API error: {response.status_code} - {response.text}"
                )
                return None
        except requests.exceptions.RequestException as e:
            logging.error(f"BVN API request error: {str(e)}")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class Debit:
    @staticmethod
    def debit_customer(amount, description):
        resource = "disbursements/payouts"
        debit_customer_headers = {
            "accept": "application/json",
            "api-key": api_key,
            "content-type": "application/json",
        }
        payload = {
            "business": bus_id,
            "sourceCurrency": "NGN",
            "destinationCurrency": "NGN",
            "amount": amount,
            "description": description,
            "customerReference": customer_reference,
            "beneficiary": {
                "firstName": "Picadailys",
                "lastName": "Services",
                "accountHolderName": "Picadailys" + " " + "Services",
                "accountNumber": "2639239472",
                "type": "individual",
                "bankCode": "101",
            },
            "paymentDestination": "bank_account",
        }
        try:
            response = requests.post(
                url=fincra_base_url + resource,
                json=payload,
                headers=debit_customer_headers,
            )

            return response

        except requests.exceptions.RequestException as e:
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class Credit:
    @staticmethod
    def credit_customer(first_name, lastname, accNo, bankCode, amount):
        resource = "disbursements/payouts"
        credit_customer_headers = {
            "accept": "application/json",
            "api-key": api_key,
            "content-type": "application/json",
        }
        payload = {
            "business": bus_id,
            "sourceCurrency": "NGN",
            "destinationCurrency": "NGN",
            "amount": amount,
            "description": "Refund of unsucessful transaction",
            "customerReference": customer_reference,
            "beneficiary": {
                "firstName": first_name,
                "lastName": lastname,
                "accountHolderName": first_name + " " + lastname,
                "accountNumber": accNo,
                "type": "individual",
                "bankCode": bankCode,
            },
            "paymentDestination": "bank_account",
        }
        try:
            response = requests.post(
                url=fincra_base_url + resource,
                json=payload,
                headers=credit_customer_headers,
            )

            return response

        except requests.exceptions.RequestException as e:
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
