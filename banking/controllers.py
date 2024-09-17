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
