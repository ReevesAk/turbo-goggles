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


def verifybvn(bvn):
    bearer_token = login()
    resource = "https://test1.providusbank.com/api/v3/account/ops/external/validate_bvn"
    payload = {"BVN": bvn}
    headers = {
        "accept": "application/json",
        "content-Type": "application/json",
        "Authorization": bearer_token,
    }
    try:
        response = requests.post(
            url=resource,
            json=payload,
            headers=headers,
        )
        print(response.json())
        print(response.json()["Phone"])
    except Exception as e:
        print(e)


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
    def Open(
        addr,
        tc,
        acc_type,
        religion,
        ms,
        gn,
        branch,
        bvn,
        state,
        lga,
        country,
        altEmail,
        altPhone,
        currentAddress,
        passport,
        identity,
        utility,
        signature,
        nin,
    ):
        resource = "https://test1.providusbank.com/api/v3/account/ops/external/individual_account_api"
        print(bvn)
        payload = {
            "address": addr,
            "tc": tc,
            "accountType": acc_type,
            "religion": religion,
            "ms": ms,
            "gn": gn,
            "branch": branch,
            "bvn": bvn,
            "state": state,
            "lga": lga,
            "country": country,
            "alt_email": altEmail,
            "alt_phone": altPhone,
            "currentAddress": currentAddress,
            "NIN": nin,
        }
        print(payload)

        # Convert the TemporaryUploadedFile to a BufferedReader
        def convert_to_buffered_reader(temp_file):
            # Write the temporary file to disk
            with open(temp_file.name, "wb") as f:
                for chunk in temp_file.chunks():
                    f.write(chunk)
            # Open it as a BufferedReader
            return open(temp_file.name, "rb")

        passport_buffer = convert_to_buffered_reader(passport)
        identity_buffer = convert_to_buffered_reader(identity)
        utility_buffer = convert_to_buffered_reader(utility)
        signature_buffer = convert_to_buffered_reader(signature)

        files = {
            "passport": ("passport.png", passport_buffer, "image/png"),
            "identity": ("identity.png", identity_buffer, "image/png"),
            "utility": ("utility.png", utility_buffer, "image/png"),
            "signature": ("signature.png", signature_buffer, "image/png"),
        }

        bearer_token = login()
        verifybvn(bvn=bvn)
        headers = {
            "accept": "application/json",
            "Authorization": bearer_token,
        }

        try:
            response = requests.post(
                url=resource, json=payload, headers=headers, files=files
            )
            return response
        except requests.exceptions.RequestException as e:
            logging.error(f"Account creation API request error: {str(e)}")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

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
