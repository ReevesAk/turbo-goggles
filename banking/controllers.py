import logging
import json
import string
import random
from datetime import datetime
import uuid
import requests
from decouple import config

from .helpers import cloudinary_to_base64

from rest_framework import status
from rest_framework.response import Response

username = config("NINE_PSB_USERNAME")
password = config("NINE_PSB_PASSWORD")
clientId = config("CLIENT_ID")
clientSecret = config("CLIENT_SECRET")
base_url = config("NINE_PSB_BASEURL")
dojah_base_url = config("DOJAH_BASE_URL")

picadailys_collection_account = config("CENTRAL_COLLECTION_ACCOUNT")

app_id = config("APP_ID")
authorization = config("AUTHORIZATION")

secret_key = config("PAYSTACK_SECRET_KEY")
headers = {
    "Authorization": f"Bearer {secret_key}",
    "Content-Type": "application/json",
}

logger = logging.getLogger(__name__)


def _build_ninepsb_url(resource):
    return f"{base_url.rstrip('/')}/{resource.lstrip('/')}"


def authenticate():
    resource = "authenticate"
    payload = {
        "username": username,
        "password": password,
        "clientId": clientId,
        "clientSecret": clientSecret,
    }
    try:
        response = requests.post(
            url=_build_ninepsb_url(resource),
            json=payload,
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
        token = data.get("accessToken") or data.get("data", {}).get("accessToken")
        if token:
            return token
    except requests.exceptions.RequestException as e:
        logging.error("Authentication request failed: %s", str(e))
        return None
    except (ValueError, Exception) as e:
        logging.error(f"Authentication failed: {str(e)}")
        return None


class KYC:
    @staticmethod
    def verify_bvn(img_file, bvn):
        url = f"{dojah_base_url}/api/v1/kyc/bvn/verify"
        payload = {"selfie_image": img_file, "bvn": bvn}
        headers = {
            "AppId": app_id,
            "Authorization": authorization,
        }

        try:
            response = requests.post(url=url, json=payload, headers=headers, timeout=30)
            logging.info(f"Dojah BVN API response status: {response.status_code}")
            return response

        except requests.exceptions.RequestException as e:
            logging.error(f"Dojah BVN Error: {str(e)}")
            return None

    @staticmethod
    def verify_nin(img_file, nin):
        resource = f"{dojah_base_url}/api/v1/kyc/nin/verify"
        payload = {"selfie_image": img_file, "nin": nin}
        headers = {
            "AppId": app_id,
            "Authorization": authorization,
        }

        try:
            response = requests.post(
                url=resource, json=payload, headers=headers, timeout=30
            )
            return response
        except requests.exceptions.RequestException as e:
            logging.error(f"NIN check API request error: {str(e)}")
            return None


class Wallet:
    def _generate_transaction_id(prefix="PICA"):
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        rand_suffix = "".join(
            random.choices(string.ascii_uppercase + string.digits, k=6)
        )

        # Combine all parts
        tx_id = f"{prefix}{timestamp}{rand_suffix}"

        return tx_id

    @staticmethod
    def generate_unique_code(prefix="Pica"):
        return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"

    @staticmethod
    def Open(
        transactionTrackingRef,
        lastName,
        otherNames,
        accountName,
        gender,
        bvn,
        dateOfBirth,
        email,
        phoneNo,
    ):
        resource = "open_wallet"
        payload = {
            "transactionTrackingRef": transactionTrackingRef,
            "lastName": lastName,
            "otherNames": otherNames,
            "accountName": accountName,
            "gender": gender,
            "bvn": bvn,
            "dateOfBirth": dateOfBirth,
            "email": email,
            "phoneNo": phoneNo,
        }

        bearer_token = authenticate()

        if not bearer_token:
            logging.error("Bearer token is invalid or missing")
            return Response(
                {"error": "Bearer token missing or invalid"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {bearer_token}",
        }

        try:
            response = requests.post(
                url=_build_ninepsb_url(resource),
                json=payload,
                headers=headers,
                timeout=180,
            )
            return response
        except requests.exceptions.RequestException as e:
            logging.error(f"Account creation API request error: {str(e)}")
            return None

    @staticmethod
    def UpgradeToTier2(
        acct_name,
        phone_number,
        email,
        acct_no,
        bvn,
        nin,
        userPhoto,
        idType,
        idNumber,
        idIssueDate,
        idExpiryDate,
        idCardFront,
        idCardBack,
        utilityBill,
        nearestLandmark,
        placeOfBirth,
        state,
        localGovernment,
        houseNumber,
        streetName,
        city,
        pep,
        customerSignature,
    ):
        resource = "wallet_upgrade"
        payload = {
            "accountNumber": acct_no,
            "bvn": bvn,
            "nin": nin,
            "tier": "2",
            "accountName": acct_name,
            "phoneNumber": phone_number,
            "email": email,
            "userPhoto": cloudinary_to_base64(userPhoto),
            "idType": idType,
            "idNumber": idNumber,
            "idIssueDate": idIssueDate,
            "idExpiryDate": idExpiryDate,
            "idCardFront": cloudinary_to_base64(idCardFront),
            "idCardBack": cloudinary_to_base64(idCardBack),
            "houseNumber": houseNumber,
            "streetName": streetName,
            "city": city,
            "state": state,
            "localGovernment": localGovernment,
            "pep": pep,
            "utilityBill": cloudinary_to_base64(utilityBill),
            "nearestLandmark": nearestLandmark,
            "placeOfBirth": placeOfBirth,
            "customerSignature": cloudinary_to_base64(customerSignature),
        }

        logger.info("Wallet Upgrade request initiated.")
        bearer_token = authenticate()

        if not bearer_token:
            logging.error("Bearer token is invalid or missing")
            return Response(
                {"error": "Bearer token missing or invalid"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {bearer_token}",
        }

        try:
            response = requests.post(
                url=base_url + resource,
                json=payload,
                headers=headers,
                timeout=180,
            )
            return response
        except requests.exceptions.RequestException as e:
            logging.error(f"Wallet upgrade API request error: {str(e)}")
            return None

    @staticmethod
    def UpgradefromTier2ToTier3(accountNumber, bvn, nin, proofOfAddressVerification):
        resource = "walletUpgrade-tier3-multipart"
        payload = {
            "accountNumber": accountNumber,
            "bvn": bvn,
            "nin": nin,
            "proofOfAddressVerification": cloudinary_to_base64(
                proofOfAddressVerification
            ),
        }

        bearer_token = authenticate()

        if not bearer_token:
            logging.error("Bearer token is invalid or missing")
            return Response(
                {"error": "Bearer token missing or invalid"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        headers = {
            "Content-Type": "multipart/form-data",
            "Authorization": f"Bearer {bearer_token}",
        }

        try:
            response = requests.post(
                url=base_url + resource,
                data=payload,
                headers=headers,
                timeout=180,
            )
            return response
        except requests.exceptions.RequestException as e:
            logging.error(f"Wallet upgrade to tier 3 API request error: {str(e)}")
            return None

    @staticmethod
    def getWalletDetails(account_number):
        resource = "wallet_enquiry"

        bearer_token = authenticate()

        if not bearer_token:
            logging.error("Bearer token is invalid or missing")
            return Response(
                {"error": "Bearer token missing or invalid"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        payload = {
            "accountNo": account_number,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {bearer_token}",
        }

        try:
            response = requests.post(
                url=base_url + resource,
                headers=headers,
                json=payload,
            )
            return response
        except requests.exceptions.RequestException as e:
            logging.error(f"Get wallet details API request error: {str(e)}")
            return None

    @staticmethod
    def Debit(debitAccount, amount, reason, merchantFeeAmount):
        bearer_token = authenticate()
        tx_id = Wallet._generate_transaction_id(prefix="PICA")
        if not bearer_token:
            logging.error("Bearer token is invalid or missing")
            return None
        resource = "debit/transfer"
        headers = {
            "Authorization": f"Bearer {bearer_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "accountNo": debitAccount,
            "totalAmount": amount,
            "transactionId": tx_id,
            "narration": reason,
            "merchant": {
                "isFee": False,
                "merchantFeeAccount": picadailys_collection_account,
                "merchantFeeAmount": merchantFeeAmount,
            },
            "transactionType": "DEBIT_WALLET",
        }

        try:
            response = requests.post(
                url=base_url + resource, headers=headers, json=payload
            )
            return response

        except requests.exceptions.RequestException as e:
            logging.error(f"Debiting an account API request error: {str(e)}")
            return None

    @staticmethod
    def Credit(acct_no, amount, reason):
        bearer_token = authenticate()
        tx_id = Wallet._generate_transaction_id(prefix="PICA")
        if not bearer_token:
            logging.error("Bearer token is invalid or missing")
            return None
        resource = "credit/transfer"
        headers = {
            "Authorization": f"Bearer {bearer_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "accountNo": acct_no,
            "totalAmount": amount,
            "transactionId": tx_id,
            "narration": reason,
            "merchant": {
                "isFee": False,
                "merchantFeeAccount": "",
                "merchantFeeAmount": "",
            },
            "transactionType": "CREDIT_WALLET",
        }
        try:
            response = requests.post(
                url=base_url + resource, headers=headers, json=payload
            )
            return response

        except requests.exceptions.RequestException as e:
            logging.error(
                f"Crediting a failed transaction account API request error: {str(e)}"
            )
            return None


# class Forex:
#     @staticmethod
#     def generate_quote():
#         resource = "fx/quote"

#         payload = {"source_currency": "NGN", "target_currency": "USD", "amount": 10000}
#         bearer_token = login()
#         headers = {
#             "accept": "application/json",
#             "content-Type": "application/json",
#             "Authorization": bearer_token,
#         }

#         try:
#             response = requests.post(
#                 url=base_url + resource,
#                 json=payload,
#                 headers=headers,
#             )
#             return response
#         except requests.exceptions.RequestException as e:
#             logging.error(f"Generate quote request error: {str(e)}")
#             return Response(
#                 {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
#             )

#     @staticmethod
#     def exchange(reference):
#         resource = "fx"

#         payload = {"quote_reference": reference}
#         bearer_token = login()
#         headers = {
#             "accept": "application/json",
#             "content-Type": "application/json",
#             "Authorization": bearer_token,
#         }

#         try:
#             response = requests.post(
#                 url=base_url + resource,
#                 json=payload,
#                 headers=headers,
#             )
#             return response
#         except requests.exceptions.RequestException as e:
#             logging.error(f"Forex exchange request error: {str(e)}")
#             return Response(
#                 {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
#             )


class Transfers:
    @staticmethod
    def getAllBanks():
        bearer_token = authenticate()
        resource = "get_banks"
        headers = {
            "Authorization": f"Bearer {bearer_token}",
            "Content-Type": "application/json",
        }
        try:
            response = requests.get(
                url=base_url + resource,
                headers=headers,
            )
            return response
        except requests.exceptions.RequestException as e:
            logging.error(f"Get all banks API request error: {str(e)}")
            return None

    @staticmethod
    def getAccount(acct_num, bank_code):
        resource = "other_banks_enquiry"
        payload = {
            "customer": {"account": {"bank": bank_code, "number": acct_num}},
        }

        bearer_token = authenticate()

        if not bearer_token:
            logging.error("Bearer token is invalid or missing")
            return Response(
                {"error": "Bearer token missing or invalid"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {bearer_token}",
        }

        try:
            response = requests.post(
                url=base_url + resource, headers=headers, json=payload
            )
            return response
        except requests.exceptions.RequestException as e:
            logging.error(f"Get account API request error: {str(e)}")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @staticmethod
    def tx_requery(sessionID, accountNumber):
        resource = "notification_requery"
        payload = {
            "accountNumber": accountNumber,
            "sessionID": sessionID,
        }

        bearer_token = authenticate()

        if not bearer_token:
            logging.error("Bearer token is invalid or missing")
            return Response(
                {"error": "Bearer token missing or invalid"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {bearer_token}",
        }

        try:
            response = requests.post(
                url=base_url + resource, headers=headers, json=payload
            )
            return response
        except requests.exceptions.RequestException as e:
            logging.error(f"Transaction requery API request error: {str(e)}")
            return None

    @staticmethod
    def initiate_transfer(
        bank_code,
        account_number,
        sender_account_number,
        name,
        sender_name,
        amount,
        description,
        transactionType,
        tx_ref,
    ):
        resource = "wallet_other_banks"
        bearer_token = authenticate()
        headers = {
            "Authorization": f"Bearer {bearer_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "customer": {
                "account": {
                    "bank": bank_code,
                    "number": account_number,
                    "senderaccountnumber": sender_account_number,
                    "name": name,
                    "sendername": sender_name,
                }
            },
            "order": {
                "amount": amount,
                "currency": "NGN",
                "description": description,
                "country": "NG",
            },
            "narration": description,
            "transaction": {"reference": tx_ref},
            "transactionType": transactionType,
        }

        url = base_url + resource
        logging.warning(
            "TRANSFER initiate_transfer REQUEST: url=%s | payload=%s | headers=%s",
            url, payload, headers,
        )
        try:
            response = requests.post(url=url, headers=headers, json=payload)
            try:
                resp_body = response.json()
            except Exception:
                resp_body = response.text
            logging.warning(
                "TRANSFER initiate_transfer RESPONSE: status=%s | body=%s",
                response.status_code, resp_body,
            )
            return response
        except requests.exceptions.RequestException as e:
            logging.warning("TRANSFER initiate_transfer ERROR: %s", e)
            return None

    @staticmethod
    def complete_transfer(
        transactionId,
    ):
        resource = "wallet_other_banks"
        bearer_token = authenticate()
        headers = {
            "Authorization": f"Bearer {bearer_token}",
            "Content-Type": "application/json",
        }
        payload = {"transactionId": transactionId}

        try:
            response = requests.post(
                url=base_url + resource, headers=headers, json=payload
            )
            return response
        except requests.exceptions.RequestException as e:
            logging.error(f"Complete transfer API request error: {str(e)}")
            return None


class Paystack:
    base_url = "https://api.paystack.co"

    @staticmethod
    def _headers():
        return {
            "Authorization": f"Bearer {secret_key}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def generate_url(email, amount):
        generate_url_resource = f"{Paystack.base_url}/transaction/initialize"
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

    @staticmethod
    def verify_transaction(reference):
        """
        Verify a Paystack transaction using its reference
        """
        url = f"{Paystack.base_url}/transaction/verify/{reference}"

        response = requests.get(
            url=url,
            headers=Paystack._headers(),
            timeout=30,
        )

        if response.status_code != 200:
            raise Exception("Failed to verify Paystack transaction")

        return response.json()

    @staticmethod
    def create_refund(txn_reference):
        refund_url_resource = f"{Paystack.base_url}/refund"
        payload = {"transaction": txn_reference}

        try:
            response = requests.post(
                url=refund_url_resource, json=payload, headers=headers
            )
            return response
        except requests.exceptions.RequestException as e:
            logging.error(f"Generate paystack payment url API request error: {str(e)}")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
