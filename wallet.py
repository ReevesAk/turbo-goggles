"""
Standalone Safe Haven MFB token fetcher.

Mints a short-lived client assertion with the private key and exchanges it
for an access/refresh token - all locally, no online JWT tool involved.

Reads config from .env (via decouple), so it can just be run as:
    python walley.py

Required .env vars:
    SAFEHAVEN_CLIENT_ID
    SAFEHAVEN_COMPANY_URL
    SAFEHAVEN_PRIVATE_KEY_PATH
Optional:
    SAFEHAVEN_BASE_URL (default: https://api.sandbox.safehavenmfb.com)
"""

import json
import time

import jwt
import requests
from decouple import config

SAFEHAVEN_BASE_URL = config(
    "SAFEHAVEN_BASE_URL", default="https://api.sandbox.safehavenmfb.com"
)
SAFEHAVEN_CLIENT_ID = config("SAFEHAVEN_CLIENT_ID")
SAFEHAVEN_COMPANY_URL = config("SAFEHAVEN_COMPANY_URL")
SAFEHAVEN_PRIVATE_KEY_PATH = config("SAFEHAVEN_PRIVATE_KEY_PATH")


def get_access_token():
    with open(SAFEHAVEN_PRIVATE_KEY_PATH, "r") as f:
        private_key = f.read()

    now = int(time.time())
    assertion = jwt.encode(
        {
            "iss": SAFEHAVEN_COMPANY_URL,
            "sub": SAFEHAVEN_CLIENT_ID,
            "aud": SAFEHAVEN_BASE_URL,
            "iat": now,
            "exp": now + 300,
        },
        private_key,
        algorithm="RS256",
    )

    response = requests.post(
        f"{SAFEHAVEN_BASE_URL}/oauth2/token",
        json={
            "grant_type": "client_credentials",
            "client_id": SAFEHAVEN_CLIENT_ID,
            "client_assertion": assertion,
            "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
        },
    )
    return response.status_code, response.json()


class SafeHaven:
    def __init__(self):
        self.base_url = SAFEHAVEN_BASE_URL

    def _authenticated_headers(self):
        status_code, data = get_access_token()
        if status_code >= 400:
            raise RuntimeError(f"Failed to get Safe Haven access token: {data}")
        return {
            "Authorization": f"Bearer {data['access_token']}",
            "ClientID": data["ibs_client_id"],
            "Content-Type": "application/json",
        }

    def create_sub_account(
        self,
        phone_number,
        email_address,
        external_reference,
        identity_type,
        identity_number=None,
        identity_id=None,
        otp=None,
        callback_url=None,
    ):
        """
        identity_type: one of "NIN", "vNIN", "BVN", "BVNUSSD", "vID".
        identity_number is required for BVN/NIN/BVNUSSD.
        identity_id is the _id returned by Safe Haven's verification endpoint,
        required for vID/BVN/NIN.
        """
        payload = {
            "phoneNumber": phone_number,
            "emailAddress": email_address,
            "externalReference": external_reference,
            "identityType": identity_type,
        }
        if identity_number:
            payload["identityNumber"] = identity_number
        if identity_id:
            payload["identityId"] = identity_id
        if otp:
            payload["otp"] = otp
        if callback_url:
            payload["callbackUrl"] = callback_url

        response = requests.post(
            f"{self.base_url}/accounts/v2/subaccount",
            headers=self._authenticated_headers(),
            json=payload,
        )
        return response.status_code, response.json()


if __name__ == "__main__":
    status_code, data = get_access_token()
    print(f"Status: {status_code}")
    print(json.dumps(data, indent=2))
