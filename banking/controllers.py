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

secret_key = config("PAYSTACK_SECRET_KEY")
headers = {
    "Authorization": f"Bearer {secret_key}",
    "Content-Type": "application/json",
}

logger = logging.getLogger(__name__)


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
        logging.debug(e)


class BVN:
    @staticmethod
    def verify(bvn):
        resource = "validate_bvn"
        payload = {
            "BVN": bvn,
        }
        bearer_token = login()

        if not bearer_token:
            logging.error("Bearer token is invalid or missing")
            return Response(
                {"error": "Bearer token missing or invalid"},
                status=status.HTTP_400_BAD_REQUEST,
            )

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
        # def convert_to_buffered_reader(temp_file):
        #     # Write the temporary file to disk
        #     with open(temp_file.name, "wb") as f:
        #         for chunk in temp_file.chunks():
        #             f.write(chunk)
        #     # Open it as a BufferedReader
        #     return open(temp_file.name, "rb")

        # passport_buffer = convert_to_buffered_reader(passport)
        # identity_buffer = convert_to_buffered_reader(identity)
        # utility_buffer = convert_to_buffered_reader(utility)
        # signature_buffer = convert_to_buffered_reader(signature)

        # files = {
        #     "passport": ("passport.png", passport_buffer, "image/png"),
        #     "identity": ("identity.png", identity_buffer, "image/png"),
        #     "utility": ("utility.png", utility_buffer, "image/png"),
        #     "signature": ("signature.png", signature_buffer, "image/png"),
        # }

        files = {
            "passport": (None, passport),
            "identity": (None, identity),
            "utility": (None, utility),
            "signature": (None, signature),
        }

        bearer_token = login()

        if not bearer_token:
            logging.error("Bearer token is invalid or missing")
            return Response(
                {"error": "Bearer token missing or invalid"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        headers = {
            "accept": "application/json",
            "Authorization": bearer_token,
        }

        data = {"data": json.dumps(payload)}
        logger.info(f"Account Creation Payload:\n{json.dumps(payload, indent=4)}")
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
    def Credit(acct_no, amount, reason, transactionReference):
        resource = "ProvidusFundTransfer"
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        payload = {
            "creditAccount": acct_no,
            "debitAccount": "6504533161",  # Picadailys account
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


class Paystack:
    @staticmethod
    def generate_url(email, amount):
        generate_url_resource = "https://api.paystack.co/transaction/initialize"
        payload = {"email": email, "amount": amount}

        try:
            response = requests.post(
                url=generate_url_resource, json=payload, headers=headers
            )
            return response
        except requests.exceptions.RequestException as e:
            logging.error(f"Generate paystack payment url API request error: {str(e)}")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
