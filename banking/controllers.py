import logging
import requests
from decouple import config

from rest_framework import status
from rest_framework.response import Response

username = config("USERNAME")
password = config("PASSWORD")
base_url = config("PROVIDUS_BASEURL")


def login():
    resource = "login"
    payload = {"username": username, "password": password}
    try:
        response = requests.post(
            url=base_url + resource,
            json=payload,
        )
        return response.json()["accessToken"]
    except Exception as e:
        logging.DEBUG(e)


class BVN:
    @staticmethod
    def verify(bvn):
        resource = "validate_bvn"
        payload = {
            "BVN": bvn,
        }
        bearer_token = login()
        headers = {
            "accept": "application/json",
            "content-Type": "application/json",
            "Authorization": bearer_token,
        }

        try:
            response = requests.post(
                url=base_url + resource,
                json=payload,
                headers=headers,
            )
            return response
        except requests.exceptions.RequestException as e:
            logging.error(f"BVN API request error: {str(e)}")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class Customer:
    @staticmethod
    def create(f_name, l_name, email, country):
        resource = "customers"
        payload = {
            "first_name": f_name,
            "last_name": l_name,
            "email": email,
            "country": country,
        }
        bearer_token = login()
        headers = {
            "accept": "application/json",
            "content-Type": "application/json",
            "Authorization": bearer_token,
        }
        try:
            response = requests.post(
                url=base_url + resource,
                json=payload,
                headers=headers,
            )
            return response
        except requests.exceptions.RequestException as e:
            logging.error(f"Enroll customer API request error: {str(e)}")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @staticmethod
    def upgradeTier1(id, dob, phone, street, street2, city, state, postal_code, bvn):
        resource = "customers/upgrade/tier1"
        payload = {
            "dob": dob,
            "phone": {"phone_country_code": "+234", "phone_number": phone[1:]},
            "address": {
                "street": street,
                "street2": street2,
                "city": city,
                "state": state,
                "country": "NG",
                "postal_code": postal_code,
            },
            "customer_id": id,
            "identification_number": bvn,
        }
        bearer_token = login()
        headers = {
            "accept": "application/json",
            "content-Type": "application/json",
            "Authorization": bearer_token,
        }

        try:
            response = requests.patch(
                url=base_url + resource,
                json=payload,
                headers=headers,
            )
            return response

        except requests.exceptions.RequestException as e:
            logging.error(f"Upgrade customer to Tier 1 API request error: {str(e)}")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @staticmethod
    def upgradeTier2(id_type, id_no, id_img, customer_id):
        resource = "customers/upgrade/tier2"
        payload = {
            "identity": {
                "type": id_type,
                "image": id_img,
                "number": id_no,
                "country": "NG",
            },
            "customer_id": customer_id,
        }
        bearer_token = login()
        headers = {
            "accept": "application/json",
            "content-Type": "application/json",
            "Authorization": bearer_token,
        }

        try:
            response = requests.post(
                url=base_url + resource,
                json=payload,
                headers=headers,
            )
            return response

        except requests.exceptions.RequestException as e:
            logging.error(f"Upgrade customer to Tier 1 API request error: {str(e)}")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class VirtualCard:
    @staticmethod
    def fund(id, amount):
        resource = f"issuing/{id}/fund"
        payload = {
            "amount": amount,
        }
        bearer_token = login()
        headers = {
            "accept": "application/json",
            "content-Type": "application/json",
            "Authorization": bearer_token,
        }

        try:
            response = requests.post(
                url=base_url + resource,
                json=payload,
                headers=headers,
            )
            return response

        except requests.exceptions.RequestException as e:
            logging.error(f"Fund a USD card API request error: {str(e)}")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @staticmethod
    def Freeze(id):
        resource = f"issuing/{id}/freeze"
        bearer_token = login()
        headers = {
            "accept": "application/json",
            "content-Type": "application/json",
            "Authorization": bearer_token,
        }

        try:
            response = requests.post(
                url=base_url + resource,
                headers=headers,
            )
            return response

        except requests.exceptions.RequestException as e:
            logging.error(f"Freezing a USD card API request error: {str(e)}")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def Unfreeze(id):
        resource = f"issuing/{id}/unfreeze"
        bearer_token = login()
        headers = {
            "accept": "application/json",
            "content-Type": "application/json",
            "Authorization": bearer_token,
        }

        try:
            response = requests.post(
                url=base_url + resource,
                headers=headers,
            )
            return response

        except requests.exceptions.RequestException as e:
            logging.error(f"Unfreezing a USD card API request error: {str(e)}")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class Account:
    @staticmethod
    def Debit(amount, reason):
        resource = "transfers"
        payload = {
            "bank_code": "C34",
            "account_number": "6192168285",
            "amount": amount,
            "reason": reason,
        }
        bearer_token = login()
        headers = {
            "accept": "application/json",
            "content-Type": "application/json",
            "Authorization": bearer_token,
        }

        try:
            response = requests.post(
                url=base_url + resource,
                json=payload,
                headers=headers,
            )
            return response

        except requests.exceptions.RequestException as e:
            logging.error(f"Debiting an account API request error: {str(e)}")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @staticmethod
    def Credit(acct_no, amount, reason):
        resource = "transfers"
        payload = {
            "bank_code": "C34",
            "account_number": acct_no,
            "amount": amount,
            "reason": reason,
        }
        bearer_token = login()
        headers = {
            "accept": "application/json",
            "content-Type": "application/json",
            "Authorization": bearer_token,
        }

        try:
            response = requests.post(
                url=base_url + resource,
                json=payload,
                headers=headers,
            )
            return response

        except requests.exceptions.RequestException as e:
            logging.error(
                f"Crediting a failed transaction account API request error: {str(e)}"
            )
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class Forex:
    @staticmethod
    def generate_quote():
        resource = "fx/quote"

        payload = {"source_currency": "NGN", "target_currency": "USD", "amount": 10000}
        bearer_token = login()
        headers = {
            "accept": "application/json",
            "content-Type": "application/json",
            "Authorization": bearer_token,
        }

        try:
            response = requests.post(
                url=base_url + resource,
                json=payload,
                headers=headers,
            )
            return response
        except requests.exceptions.RequestException as e:
            logging.error(f"Generate quote request error: {str(e)}")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @staticmethod
    def exchange(reference):
        resource = "fx"

        payload = {"quote_reference": reference}
        bearer_token = login()
        headers = {
            "accept": "application/json",
            "content-Type": "application/json",
            "Authorization": bearer_token,
        }

        try:
            response = requests.post(
                url=base_url + resource,
                json=payload,
                headers=headers,
            )
            return response
        except requests.exceptions.RequestException as e:
            logging.error(f"Forex exchange request error: {str(e)}")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
