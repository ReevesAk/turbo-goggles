import logging
import string
import random
import time
from datetime import datetime
import uuid
import requests
from decouple import config
from django.core.cache import cache

from .helpers import cloudinary_to_base64, cloudinary_to_bytes

from rest_framework import status
from rest_framework.response import Response

username = config("NINE_PSB_USERNAME")
password = config("NINE_PSB_PASSWORD")
clientId = config("CLIENT_ID")
clientSecret = config("CLIENT_SECRET")
base_url = config("NINE_PSB_BASEURL")
dojah_base_url = config("DOJAH_BASE_URL")

picadailys_operational_account = config("CENTRAL_OPERATIONAL_ACCOUNT")

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


def _post_with_retry(
    url, headers, json_payload, timeout, retries=1, backoff_seconds=1.5
):
    """
    POST with retries on network-level failures only (timeout / connection
    refused) - never on a definitive HTTP response, since that means 9PSB
    already answered and retrying could double-process the request.

    Retries resend the exact same json_payload (including transactionId for
    debit/credit calls), so a retry after a read timeout is only as risky as
    9PSB's own dedup-by-transactionId guarantee - the same assumption this
    codebase already relies on when a user manually resubmits a FAILED
    transaction (see BrandChargeMixin._check_idempotency).
    """
    attempt = 0
    while True:
        try:
            return requests.post(
                url=url, headers=headers, json=json_payload, timeout=timeout
            )
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            attempt += 1
            if attempt > retries:
                raise
            logging.warning(
                "Transient error calling %s (attempt %d/%d): %s - retrying",
                url,
                attempt,
                retries + 1,
                e,
            )
            time.sleep(backoff_seconds)


_NINE_PSB_TOKEN_KEY = "nine_psb_bearer_token"
_NINE_PSB_TOKEN_TTL = 25 * 60  # 25 minutes — refresh before 9PSB token expires


def _fetch_fresh_token():
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
            cache.set(_NINE_PSB_TOKEN_KEY, token, _NINE_PSB_TOKEN_TTL)
            return token
    except requests.exceptions.RequestException as e:
        logging.error("Authentication request failed: %s", str(e))
    except Exception as e:
        logging.error("Authentication failed: %s", str(e))
    return None


def authenticate(force_refresh=False):
    """Return cached 9PSB token; fetch a fresh one only when missing or force_refresh=True."""
    if not force_refresh:
        token = cache.get(_NINE_PSB_TOKEN_KEY)
        if token:
            return token
    return _fetch_fresh_token()


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
        url = base_url + resource
        logging.warning(
            "WALLET UpgradeToTier2 REQUEST: url=%s | payload=%s | headers=%s",
            url,
            payload,
            headers,
        )
        try:
            response = requests.post(
                url=url, json=payload, headers=headers, timeout=180
            )
            try:
                resp_body = response.json()
            except Exception:
                resp_body = response.text
            logging.warning(
                "WALLET UpgradeToTier2 RESPONSE: status=%s | body=%s",
                response.status_code,
                resp_body,
            )
            return response
        except requests.exceptions.RequestException as e:
            logging.warning("WALLET UpgradeToTier2 ERROR: %s", e)
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
            response = _post_with_retry(
                url=base_url + resource,
                headers=headers,
                json_payload=payload,
                timeout=15,
            )
            if response.status_code == 401:
                bearer_token = authenticate(force_refresh=True)
                if bearer_token:
                    headers["Authorization"] = f"Bearer {bearer_token}"
                    response = _post_with_retry(
                        url=base_url + resource,
                        headers=headers,
                        json_payload=payload,
                        timeout=15,
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
                "merchantFeeAccount": picadailys_operational_account,
                "merchantFeeAmount": merchantFeeAmount,
            },
            "transactionType": "DEBIT_WALLET",
        }

        try:
            response = _post_with_retry(
                url=base_url + resource,
                headers=headers,
                json_payload=payload,
                timeout=30,
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
                url=base_url + resource, headers=headers, json=payload, timeout=30
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
                timeout=15,
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
                url=base_url + resource, headers=headers, json=payload, timeout=30
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
                url=base_url + resource, headers=headers, json=payload, timeout=30
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
        merchant_fee=None,
    ):
        resource = "wallet_other_banks"
        bearer_token = authenticate()
        headers = {
            "Authorization": f"Bearer {bearer_token}",
            "Content-Type": "application/json",
        }
        is_fee = merchant_fee is not None
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
            "merchant": {
                "isFee": is_fee,
                "merchantFeeAccount": picadailys_operational_account if is_fee else "",
                "merchantFeeAmount": str(merchant_fee) if is_fee else "",
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
            url,
            payload,
            headers,
        )
        try:
            response = requests.post(url=url, headers=headers, json=payload, timeout=30)
            if response.status_code == 401:
                bearer_token = authenticate(force_refresh=True)
                if bearer_token:
                    headers["Authorization"] = f"Bearer {bearer_token}"
                    response = requests.post(
                        url=url, headers=headers, json=payload, timeout=30
                    )
            try:
                resp_body = response.json()
            except Exception:
                resp_body = response.text
            logging.warning(
                "TRANSFER initiate_transfer RESPONSE: status=%s | body=%s",
                response.status_code,
                resp_body,
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
                url=base_url + resource, headers=headers, json=payload, timeout=30
            )
            return response
        except requests.exceptions.RequestException as e:
            logging.error(f"Complete transfer API request error: {str(e)}")
            return None


_BUSINESS_TYPE_TO_DOJAH = {
    "SOLE_PROPRIETORSHIP": "BUSINESS_NAME",
    "LIMITED_LIABILITY_COMPANY": "COMPANY",
    "CORPORATIONS": "COMPANY",
    "FRANCHISE": "COMPANY",
    "SOCIAL_ENTERPRISE": "COMPANY",
    "COOPERATIVE": "COMPANY",
    "OTHERS": "COMPANY",
    "PARTNERSHIP": "LIMITED_PARTNERSHIP",
    "NGO": "INCORPORATED_TRUSTEES",
}

_BUSINESS_SUFFIXES = [
    " limited",
    " ltd",
    " plc",
    " incorporated",
    " inc",
    " co.",
    " company",
    " enterprises",
    " global",
    " ng",
]


def _normalize_business_name(name):
    name = (name or "").lower().strip()
    for suffix in _BUSINESS_SUFFIXES:
        if name.endswith(suffix):
            name = name[: -len(suffix)].strip()
    return name


def _names_match(submitted, verified):
    s = _normalize_business_name(submitted)
    v = _normalize_business_name(verified)
    return s and v and (s in v or v in s)


class CorporateKYC:
    _headers = {
        "AppId": app_id,
        "Authorization": authorization,
    }

    @staticmethod
    def verify_registration(
        rc_number, business_type, business_name, company_reg_date=None
    ):
        """
        Verifies RC number via Dojah CAC advance.
        Cross-validates: rc_number, business_name, and optionally company_reg_date.
        Returns (True, entity_dict) or (False, error_message).
        """
        company_type = _BUSINESS_TYPE_TO_DOJAH.get(business_type, "COMPANY")
        url = f"{dojah_base_url}/api/v1/kyc/cac/advance"
        try:
            response = requests.get(
                url=url,
                params={"rc_number": rc_number, "company_type": company_type},
                headers=CorporateKYC._headers,
                timeout=20,
            )
            if response.status_code != 200:
                logging.warning(
                    "CAC verify non-200: %s %s",
                    response.status_code,
                    response.text[:200],
                )
                return (
                    False,
                    "Registration number could not be verified. Please check the RC number and try again.",
                )

            entity = response.json().get("entity") or {}

            verified_rc = (entity.get("rc_number") or "").strip().upper()
            submitted_rc = (rc_number or "").strip().upper()
            if not verified_rc:
                return False, "Registration number not found in CAC records."
            if verified_rc != submitted_rc:
                return (
                    False,
                    f"Registration number mismatch: CAC records show RC '{verified_rc}'.",
                )

            verified_name = entity.get("company_name", "")
            if not _names_match(business_name, verified_name):
                return False, (
                    f"Business name does not match CAC records. "
                    f"CAC shows '{verified_name}' for RC {rc_number}."
                )

            if company_reg_date:
                reg_date_str = (entity.get("date_of_registration") or "")[:10]
                if reg_date_str and reg_date_str != company_reg_date:
                    return False, (
                        f"Registration date mismatch: CAC records show {reg_date_str}."
                    )

            return True, entity

        except requests.exceptions.RequestException as e:
            logging.error("CorporateKYC.verify_registration error: %s", e)
            return False, "Registration verification service is currently unavailable."

    @staticmethod
    def verify_tin(tin, business_name, registration_number=None):
        """
        Validates TIN via Dojah FIRS.
        Cross-validates: taxpayer_name against business_name,
        and cac_reg_number against registration_number.
        Returns (True, entity_dict) or (False, error_message).
        """
        url = f"{dojah_base_url}/api/v1/kyc/tin"
        try:
            response = requests.get(
                url=url,
                params={"tin": tin},
                headers=CorporateKYC._headers,
                timeout=20,
            )
            if response.status_code != 200:
                logging.warning(
                    "TIN verify non-200: %s %s",
                    response.status_code,
                    response.text[:200],
                )
                return (
                    False,
                    "TIN could not be verified. Please check the TIN and try again.",
                )

            entity = response.json().get("entity") or {}

            taxpayer_name = entity.get("taxpayer_name", "")
            if not taxpayer_name:
                return False, "TIN not found in FIRS records."

            if not _names_match(business_name, taxpayer_name):
                return False, (
                    f"TIN is registered to '{taxpayer_name}', "
                    f"which does not match the submitted business name '{business_name}'."
                )

            if registration_number:
                firs_rc = (entity.get("cac_reg_number") or "").strip().upper()
                submitted_rc = registration_number.strip().upper()
                if firs_rc and firs_rc != submitted_rc:
                    return False, (
                        f"TIN is linked to RC number '{firs_rc}', "
                        f"which does not match the provided registration number '{submitted_rc}'."
                    )

            return True, entity

        except requests.exceptions.RequestException as e:
            logging.error("CorporateKYC.verify_tin error: %s", e)
            return False, "TIN verification service is currently unavailable."


class Corporate:
    @staticmethod
    def _make_files_payload(files_dict):
        payload = []
        for key, file_obj in files_dict.items():
            if file_obj:
                content = file_obj.read()
                payload.append((key, (file_obj.name, content, file_obj.content_type)))
        return payload

    @staticmethod
    def submit(data, files):
        resource = "corporates/submit"
        bearer_token = authenticate()
        if not bearer_token:
            logging.error("Bearer token missing for corporate submit")
            return None
        headers = {"Authorization": f"Bearer {bearer_token}"}
        files_payload = Corporate._make_files_payload(files)
        try:
            response = requests.post(
                url=_build_ninepsb_url(resource),
                data=data,
                files=files_payload or None,
                headers=headers,
                timeout=120,
            )
            if response.status_code == 401:
                bearer_token = authenticate(force_refresh=True)
                if bearer_token:
                    headers["Authorization"] = f"Bearer {bearer_token}"
                    response = requests.post(
                        url=_build_ninepsb_url(resource),
                        data=data,
                        files=files_payload or None,
                        headers=headers,
                        timeout=120,
                    )
            return response
        except requests.exceptions.RequestException as e:
            logging.error("Corporate submit error: %s", e)
            return None

    @staticmethod
    def submit_with_stored_docs(data, stored_docs, proof_file):
        """Submit corporate to 9PSB using Cloudinary-stored docs + admin-provided proof_file."""
        resource = "corporates/submit"
        bearer_token = authenticate()
        if not bearer_token:
            logging.error("Bearer token missing for corporate submit")
            return None
        headers = {"Authorization": f"Bearer {bearer_token}"}

        files_payload = []
        for key, url in stored_docs.items():
            try:
                content, content_type = cloudinary_to_bytes(url)
                filename = url.split("/")[-1]
                files_payload.append((key, (filename, content, content_type)))
            except Exception as e:
                logging.error("Failed to download stored doc %s: %s", key, e)
                return None

        if proof_file:
            content = proof_file.read()
            files_payload.append(
                (
                    "proofOfAddressVerification",
                    (proof_file.name, content, proof_file.content_type),
                )
            )

        try:
            response = requests.post(
                url=_build_ninepsb_url(resource),
                data=data,
                files=files_payload or None,
                headers=headers,
                timeout=120,
            )
            if response.status_code == 401:
                bearer_token = authenticate(force_refresh=True)
                if bearer_token:
                    headers["Authorization"] = f"Bearer {bearer_token}"
                    response = requests.post(
                        url=_build_ninepsb_url(resource),
                        data=data,
                        files=files_payload or None,
                        headers=headers,
                        timeout=120,
                    )
            return response
        except requests.exceptions.RequestException as e:
            logging.error("Corporate submit_with_stored_docs error: %s", e)
            return None

    @staticmethod
    def update(data, files):
        resource = "corporates/update"
        bearer_token = authenticate()
        if not bearer_token:
            logging.error("Bearer token missing for corporate update")
            return None
        headers = {"Authorization": f"Bearer {bearer_token}"}
        files_payload = Corporate._make_files_payload(files)
        try:
            response = requests.post(
                url=_build_ninepsb_url(resource),
                data=data,
                files=files_payload or None,
                headers=headers,
                timeout=120,
            )
            if response.status_code == 401:
                bearer_token = authenticate(force_refresh=True)
                if bearer_token:
                    headers["Authorization"] = f"Bearer {bearer_token}"
                    response = requests.post(
                        url=_build_ninepsb_url(resource),
                        data=data,
                        files=files_payload or None,
                        headers=headers,
                        timeout=120,
                    )
            return response
        except requests.exceptions.RequestException as e:
            logging.error("Corporate update error: %s", e)
            return None

    @staticmethod
    def get_status(tin):
        resource = "corporates/status"
        bearer_token = authenticate()
        if not bearer_token:
            logging.error("Bearer token missing for corporate status")
            return None
        headers = {
            "Authorization": f"Bearer {bearer_token}",
            "Accept": "application/json",
        }
        try:
            response = requests.get(
                url=_build_ninepsb_url(resource),
                params={"tin": tin},
                headers=headers,
                timeout=30,
            )
            return response
        except requests.exceptions.RequestException as e:
            logging.error("Corporate status error: %s", e)
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
                url=generate_url_resource, json=payload, headers=headers, timeout=30
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
                url=refund_url_resource, json=payload, headers=headers, timeout=30
            )
            return response
        except requests.exceptions.RequestException as e:
            logging.error(f"Generate paystack payment url API request error: {str(e)}")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
