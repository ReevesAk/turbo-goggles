import logging
import json
import requests
from decouple import config

from rest_framework import status
from rest_framework.response import Response

username = config("USERNAME")
password = config("PASSWORD")
base_url = config("PROVIDUS_BASEURL")
tf_base_url = config("TRANSFERS_URL")
tf_username = config("TRANSFERS_USERNAME")
tf_password = config("TRANSFERS_PASSWORD")


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
        resource = "individual_account_api"
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
            "altEmail": altEmail,
            "altPhone": altPhone,
            "currentAddress": currentAddress,
            "NIN": nin,
        }

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
        headers = {
            "accept": "application/json",
            "Authorization": bearer_token,
        }

        data = {"data": json.dumps(payload)}
        try:
            response = requests.post(
                url=base_url + resource,
                data=data,
                headers=headers,
                files=files,
                timeout=180,
            )
            return response
        except requests.exceptions.RequestException as e:
            logging.error(f"Account creation API request error: {str(e)}")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @staticmethod
    def Debit(debitAccount, amount, reason, transactionReference):
        resource = "ProvidusFundTransfer"
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        payload = {
            "creditAccount": "6504533161",  # Placeholder for picadailys account number
            "debitAccount": debitAccount,
            "currencyCode": "NGN",
            "transactionAmount": amount,
            "narration": reason,
            "transactionReference": transactionReference,
            "userName": tf_username,
            "password": tf_password,
        }

        try:
            response = requests.post(
                url=tf_base_url + resource, headers=headers, json=payload
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


class Transfers:
    @staticmethod
    def getAllBanks():
        resource = "GetNIPBanks"
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        try:
            response = requests.get(
                url=tf_base_url + resource,
                headers=headers,
            )
            return response
        except requests.exceptions.RequestException as e:
            logging.error(f"Get all banks API request error: {str(e)}")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @staticmethod
    def getProvidusAccount(acct_num):
        resource = "GetProvidusAccount"
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        payload = {
            "accountNumber": acct_num,
            "userName": tf_username,
            "password": tf_password,
        }

        try:
            response = requests.post(
                url=tf_base_url + resource, headers=headers, json=payload
            )
            return response
        except requests.exceptions.RequestException as e:
            logging.error(f"Get Providus account API request error: {str(e)}")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @staticmethod
    def getAccount(acct_num, bank_code):
        resource = "GetNIPAccount"
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        payload = {
            "accountNumber": acct_num,
            "beneficiaryBank": bank_code,
            "userName": tf_username,
            "password": tf_password,
        }

        try:
            response = requests.post(
                url=tf_base_url + resource, headers=headers, json=payload
            )
            return response
        except requests.exceptions.RequestException as e:
            logging.error(f"Get account API request error: {str(e)}")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @staticmethod
    def Intra_bank_transfer(
        creditAccount,
        debitAccount,
        transactionAmount,
        narration,
        transactionReference,
    ):
        resource = "ProvidusFundTransfer"
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        payload = {
            "creditAccount": creditAccount,
            "debitAccount": debitAccount,
            "currencyCode": "NGN",
            "transactionAmount": transactionAmount,
            "narration": narration,
            "transactionReference": transactionReference,
            "userName": tf_username,
            "password": tf_password,
        }

        try:
            response = requests.post(
                url=tf_base_url + resource, headers=headers, json=payload
            )
            return response
        except requests.exceptions.RequestException as e:
            logging.error(
                f"Transfer from Picadailys to Picadailys API request error: {str(e)}"
            )
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @staticmethod
    def IntraBankStatus(
        transactionReference,
    ):
        resource = "GetProvidusTransactionStatus"
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        payload = {
            "transactionReference": transactionReference,
            "userName": tf_username,
            "password": tf_password,
        }

        try:
            response = requests.post(
                url=tf_base_url + resource, headers=headers, json=payload
            )
            return response
        except requests.exceptions.RequestException as e:
            logging.error(f"Get transfers status API request error: {str(e)}")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @staticmethod
    def Inter_bank_transfer(
        beneficiaryAccountName,
        transactionAmount,
        narration,
        beneficiaryBank,
        transactionReference,
        beneficiaryAccountNumber,
    ):
        resource = "NIPFundTransfer"
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        payload = {
            "beneficiaryAccountName": beneficiaryAccountName,
            "transactionAmount": transactionAmount,
            "currencyCode": "NGN",
            "narration": narration,
            "sourceAccountName": "Nnamdi Adebayo Hamzat",
            "beneficiaryAccountNumber": beneficiaryAccountNumber,
            "beneficiaryBank": beneficiaryBank,
            "transactionReference": transactionReference,
            "userName": tf_username,
            "password": tf_password,
        }

        try:
            response = requests.post(
                url=tf_base_url + resource, headers=headers, json=payload
            )
            return response
        except requests.exceptions.RequestException as e:
            logging.error(f"Transfer to other banks API request error: {str(e)}")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @staticmethod
    def InterBankStatus(
        transactionReference,
    ):
        resource = "GetNIPTransactionStatus"
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        payload = {
            "transactionReference": transactionReference,
            "userName": tf_username,
            "password": tf_password,
        }

        try:
            response = requests.post(
                url=tf_base_url + resource, headers=headers, json=payload
            )
            return response
        except requests.exceptions.RequestException as e:
            logging.error(f"Get transfers status API request error: {str(e)}")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
