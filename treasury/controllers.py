import uuid
import logging
import requests
from decouple import config

anchor_api_key = config("ANCHOR_API_KEY", default="")
anchor_base_url = config("ANCHOR_BASE_URL", default="https://api.sandbox.getanchor.co").rstrip("/")
anchor_ops_account_id = config("ANCHOR_OPS_ACCOUNT_ID", default="")

logger = logging.getLogger(__name__)


def _log_request(label, url, payload=None):
    logger.warning("Anchor %s REQUEST: url=%s | payload=%s", label, url, payload)


def _log_response(label, response):
    try:
        body = response.json()
    except Exception:
        body = response.text
    logger.warning("Anchor %s RESPONSE: status=%s | body=%s", label, response.status_code, body)


class Anchor:
    @staticmethod
    def _get_headers():
        return {
            "x-anchor-key": anchor_api_key,
            "Content-Type": "application/json",
            "accept": "application/json",
        }

    @staticmethod
    def generate_reference(prefix="PICA"):
        return f"{prefix}-{uuid.uuid4().hex[:20]}"

    @staticmethod
    def is_success(response):
        """Anchor returns HTTP 200/201 for success."""
        try:
            return response.status_code in (200, 201)
        except Exception:
            return False

    # ------------------------------------------------------------------ #
    # Customers
    # ------------------------------------------------------------------ #

    @staticmethod
    def create_customer(first_name, last_name, email, phone, bvn=None):
        """
        Create an individual customer on Anchor.
        phone must be in E.164 format: +2348012345678
        """
        url = f"{anchor_base_url}/api/v1/customers"
        attributes = {
            "firstName": first_name,
            "lastName": last_name,
            "email": email,
            "phoneNumber": phone,
        }
        if bvn:
            attributes["bvn"] = bvn
        payload = {
            "data": {
                "type": "IndividualCustomer",
                "attributes": attributes,
            }
        }
        _log_request("create_customer", url, payload)
        try:
            resp = requests.post(url, json=payload, headers=Anchor._get_headers(), timeout=30)
            _log_response("create_customer", resp)
            return resp
        except requests.RequestException as e:
            logger.warning("Anchor create_customer ERROR: %s", e)
            return None

    @staticmethod
    def get_customer(customer_id):
        """Retrieve a customer by Anchor customer ID."""
        url = f"{anchor_base_url}/api/v1/customers/{customer_id}"
        _log_request("get_customer", url)
        try:
            resp = requests.get(url, headers=Anchor._get_headers(), timeout=15)
            _log_response("get_customer", resp)
            return resp
        except requests.RequestException as e:
            logger.warning("Anchor get_customer ERROR: %s", e)
            return None

    # ------------------------------------------------------------------ #
    # Deposit Accounts (sub-accounts / virtual NUBANs)
    # ------------------------------------------------------------------ #

    @staticmethod
    def create_deposit_account(customer_id, account_name=None):
        """
        Create a virtual deposit account (NUBAN) for a customer.
        Each user gets their own real account number on signup.
        """
        url = f"{anchor_base_url}/api/v1/accounts"
        attributes = {"productName": "SAVINGS"}
        if account_name:
            attributes["accountName"] = account_name
        payload = {
            "data": {
                "type": "DepositAccount",
                "attributes": attributes,
                "relationships": {
                    "customer": {
                        "data": {"type": "IndividualCustomer", "id": customer_id}
                    }
                },
            }
        }
        _log_request("create_deposit_account", url, payload)
        try:
            resp = requests.post(url, json=payload, headers=Anchor._get_headers(), timeout=30)
            _log_response("create_deposit_account", resp)
            return resp
        except requests.RequestException as e:
            logger.warning("Anchor create_deposit_account ERROR: %s", e)
            return None

    @staticmethod
    def get_account(account_id):
        """Get deposit account details (including NUBAN and bank name)."""
        url = f"{anchor_base_url}/api/v1/accounts/{account_id}"
        _log_request("get_account", url)
        try:
            resp = requests.get(url, headers=Anchor._get_headers(), timeout=15)
            _log_response("get_account", resp)
            return resp
        except requests.RequestException as e:
            logger.warning("Anchor get_account ERROR: %s", e)
            return None

    @staticmethod
    def get_balance(account_id):
        """
        Get the balance of a deposit account.
        Returns amount in kobo — divide by 100 for naira.
        """
        url = f"{anchor_base_url}/api/v1/accounts/balance/{account_id}"
        _log_request("get_balance", url)
        try:
            resp = requests.get(url, headers=Anchor._get_headers(), timeout=15)
            _log_response("get_balance", resp)
            return resp
        except requests.RequestException as e:
            logger.warning("Anchor get_balance ERROR: %s", e)
            return None

    # ------------------------------------------------------------------ #
    # Transfers
    # ------------------------------------------------------------------ #

    @staticmethod
    def internal_transfer(source_account_id, destination_account_id, amount_naira, narration, reference=None):
        """
        Transfer between two Anchor sub-accounts (instant, stays within Anchor ledger).
        amount_naira is in naira — converted to kobo internally.
        """
        url = f"{anchor_base_url}/api/v1/transfers"
        ref = reference or Anchor.generate_reference()
        payload = {
            "data": {
                "type": "BookTransfer",
                "attributes": {
                    "amount": int(amount_naira * 100),  # kobo
                    "currency": "NGN",
                    "reason": narration,
                    "reference": ref,
                },
                "relationships": {
                    "account": {
                        "data": {"type": "DepositAccount", "id": source_account_id}
                    },
                    "destinationAccount": {
                        "data": {"type": "DepositAccount", "id": destination_account_id}
                    },
                },
            }
        }
        _log_request("internal_transfer", url, payload)
        try:
            resp = requests.post(url, json=payload, headers=Anchor._get_headers(), timeout=30)
            _log_response("internal_transfer", resp)
            return resp
        except requests.RequestException as e:
            logger.warning("Anchor internal_transfer ERROR: %s", e)
            return None

    @staticmethod
    def create_counterparty(account_name, account_number, bank_code):
        """
        Register a recipient bank account as a CounterParty before sending a NIP transfer.
        POST /api/v1/counterparties
        Returns the counterparty ID needed for nip_transfer.
        """
        url = f"{anchor_base_url}/api/v1/counterparties"
        payload = {
            "data": {
                "type": "CounterParty",
                "attributes": {
                    "accountName": account_name,
                    "accountNumber": account_number,
                    "bankCode": bank_code,
                },
            }
        }
        _log_request("create_counterparty", url, payload)
        try:
            resp = requests.post(url, json=payload, headers=Anchor._get_headers(), timeout=30)
            _log_response("create_counterparty", resp)
            return resp
        except requests.RequestException as e:
            logger.warning("Anchor create_counterparty ERROR: %s", e)
            return None

    @staticmethod
    def nip_transfer(source_account_id, counterparty_id, amount_naira, narration, reference=None):
        """
        Send money to any Nigerian bank via NIP/NIBSS.
        Requires a counterparty_id from create_counterparty().
        amount_naira is in naira — converted to kobo internally.
        POST /api/v1/transfers  (type: NIPTransfer)
        """
        url = f"{anchor_base_url}/api/v1/transfers"
        ref = reference or Anchor.generate_reference()
        payload = {
            "data": {
                "type": "NIPTransfer",
                "attributes": {
                    "amount": int(amount_naira * 100),  # kobo
                    "currency": "NGN",
                    "reason": narration,
                    "reference": ref,
                },
                "relationships": {
                    "account": {
                        "data": {"type": "DepositAccount", "id": source_account_id}
                    },
                    "counterParty": {
                        "data": {"type": "CounterParty", "id": counterparty_id}
                    },
                },
            }
        }
        _log_request("nip_transfer", url, payload)
        try:
            resp = requests.post(url, json=payload, headers=Anchor._get_headers(), timeout=30)
            _log_response("nip_transfer", resp)
            return resp
        except requests.RequestException as e:
            logger.warning("Anchor nip_transfer ERROR: %s", e)
            return None

    @staticmethod
    def get_transfer(transfer_id):
        """Get the status of a transfer by ID."""
        url = f"{anchor_base_url}/api/v1/transfers/{transfer_id}"
        _log_request("get_transfer", url)
        try:
            resp = requests.get(url, headers=Anchor._get_headers(), timeout=15)
            _log_response("get_transfer", resp)
            return resp
        except requests.RequestException as e:
            logger.warning("Anchor get_transfer ERROR: %s", e)
            return None

    # ------------------------------------------------------------------ #
    # Name Enquiry
    # ------------------------------------------------------------------ #

    @staticmethod
    def verify_bank_account(bank_code, account_number):
        """
        NIP name enquiry — verify a bank account before sending money.
        Returns the account name if valid.
        GET /api/v1/payments/verify-account/{bankCode}/{accountNumber}
        """
        url = f"{anchor_base_url}/api/v1/payments/verify-account/{bank_code}/{account_number}"
        _log_request("verify_bank_account", url)
        try:
            resp = requests.get(url, headers=Anchor._get_headers(), timeout=15)
            _log_response("verify_bank_account", resp)
            return resp
        except requests.RequestException as e:
            logger.warning("Anchor verify_bank_account ERROR: %s", e)
            return None

    # ------------------------------------------------------------------ #
    # Fees
    # ------------------------------------------------------------------ #

    @staticmethod
    def charge_custom_fee(account_id, amount_naira, description="Platform fee"):
        """
        Charge a fee to a user's deposit account.
        Amount settles into the organisation's Anchor revenue account.
        POST /api/v1/fee/custom-fee
        amount_naira is in naira — converted to kobo internally.
        """
        url = f"{anchor_base_url}/api/v1/fee/custom-fee"
        payload = {
            "data": {
                "type": "CustomerFee",
                "attributes": {
                    "currency": "NGN",
                    "amount": int(amount_naira * 100),  # kobo
                    "description": description,
                },
                "relationships": {
                    "account": {
                        "data": {"type": "DepositAccount", "id": account_id}
                    }
                },
            }
        }
        _log_request("charge_custom_fee", url, payload)
        try:
            resp = requests.post(url, json=payload, headers=Anchor._get_headers(), timeout=30)
            _log_response("charge_custom_fee", resp)
            return resp
        except requests.RequestException as e:
            logger.warning("Anchor charge_custom_fee ERROR: %s", e)
            return None

    # ------------------------------------------------------------------ #
    # KYC / Tier Upgrades
    # ------------------------------------------------------------------ #

    @staticmethod
    def upgrade_tier2(customer_id, bvn, date_of_birth, gender):
        """
        Submit BVN for Tier 2 upgrade (Anchor's automatic Tier 1 validation).
        POST /api/v1/customers/{id}/verification/individual
        date_of_birth: "YYYY-MM-DD"
        gender: "Male" | "Female"
        Result arrives via customer.identification.approved/rejected webhook.
        """
        url = f"{anchor_base_url}/api/v1/customers/{customer_id}/verification/individual"
        payload = {
            "data": {
                "type": "Verification",
                "attributes": {
                    "level": "TIER_2",
                    "level2": {
                        "bvn": bvn,
                        "dateOfBirth": date_of_birth,
                        "gender": gender,
                    },
                },
            }
        }
        _log_request("upgrade_tier2", url, payload)
        try:
            resp = requests.post(url, json=payload, headers=Anchor._get_headers(), timeout=30)
            _log_response("upgrade_tier2", resp)
            return resp
        except requests.RequestException as e:
            logger.warning("Anchor upgrade_tier2 ERROR: %s", e)
            return None

    @staticmethod
    def upgrade_tier3(customer_id, id_type, id_number):
        """
        Submit government ID for Tier 3 upgrade (Anchor's manual Tier 2 review).
        POST /api/v1/customers/{id}/verification/individual
        id_type: "NIN" | "Passport" | "DriversLicense" | "VotersCard"
        Result arrives via customer.identification.approved/rejected webhook.
        """
        url = f"{anchor_base_url}/api/v1/customers/{customer_id}/verification/individual"
        payload = {
            "data": {
                "type": "Verification",
                "attributes": {
                    "level": "TIER_3",
                    "level3": {
                        "idType": id_type,
                        "idNumber": id_number,
                    },
                },
            }
        }
        _log_request("upgrade_tier3", url, payload)
        try:
            resp = requests.post(url, json=payload, headers=Anchor._get_headers(), timeout=30)
            _log_response("upgrade_tier3", resp)
            return resp
        except requests.RequestException as e:
            logger.warning("Anchor upgrade_tier3 ERROR: %s", e)
            return None

    # ------------------------------------------------------------------ #
    # Transactions
    # ------------------------------------------------------------------ #

    @staticmethod
    def get_transactions(account_id, page=1, per_page=20):
        """List transactions for a deposit account."""
        url = f"{anchor_base_url}/api/v1/transactions"
        params = {
            "filter[accountId]": account_id,
            "page[number]": page,
            "page[size]": per_page,
        }
        _log_request("get_transactions", url, params)
        try:
            resp = requests.get(url, headers=Anchor._get_headers(), params=params, timeout=15)
            _log_response("get_transactions", resp)
            return resp
        except requests.RequestException as e:
            logger.warning("Anchor get_transactions ERROR: %s", e)
            return None
