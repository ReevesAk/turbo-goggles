import time
import base64
import json
import jwt
import logging
import requests
from decouple import config as conf

from rest_framework.response import Response
from rest_framework import status


logger = logging.getLogger(__name__)

nextbee_base_url = conf("NEXTBEE_BASE_URL")
secret_key = conf("NEXTBEE_JWT_SECRET_KEY")
sso_register_widget_config = conf("NEXTBEE_SSO_REGISTER_WIDGET_CONFIG")
sso_login_widget_config = conf("NEXTBEE_SSO_LOGIN_WIDGET_CONFIG")
widget_config = conf("NEXTBEE_WIDGET_CONFIG_ID")
program_id = conf("NEXTBEE_PROGRAM_ID")
admin_email = conf("NEXTBEE_ADMIN_EMAIL")
nextbee_environment = conf("NEXTBEE_ENVIRONMENT")
nextbee_advertiser_id = conf("NEXTBEE_ADVERTISER_ID")
nextbee_program_id = conf("NEXTBEE_PROGRAM_ID")


class JWTUtils:
    @staticmethod
    def encrypt_nb(self, data: str, key: str) -> str:
        encrypted = ''.join(chr(ord(data[i]) ^ ord(key[i % len(key)])) for i in range(len(data)))
        return base64.b64encode(encrypted.encode()).decode()

    @staticmethod
    def generate_jwt_token(self, advertiser_id: str, email: str, algorithm: str = 'HS256') -> str:
        """
        Generate a JWT token with the given data and secret key.
        """

        # Data to be encrypted
        data = {
            "aid": advertiser_id,
            "email": email
        }

        # === Encrypt and encode ===
        json_data = json.dumps(data)
        encrypted_data = self.encrypt_nb(json_data, secret_key)

        # === JWT payload ===
        timestamp = int(time.time())  # UTC time
        exp_duration = 15 * 60  # 15 minutes in seconds

        payload = {
            "iss": "nextbee",
            "sub": encrypted_data,
            "iat": timestamp,
            "exp": timestamp + exp_duration
        }

        # Generate JWT token
        token = jwt.encode(payload=payload, key=secret_key, algorithm=algorithm)
        return token

    @staticmethod
    def sso_login(
        self,
        env: str,
        email: str,
        program_id: int,
        advertiser_id: str,
        ssoRegisterWidgetConfigId: int,
        ssoLoginWidgetConfigId: int,

    ) -> str:
        """
        Login to NextBee SSO.
        """
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.generate_jwt_token(advertiser_id, email)}"
        }

        url = f"{nextbee_base_url}/client/sso/login"
        payload = {
            "env": env,
            "email": email,
            "programId": program_id,
            "ssoRegisterWidgetConfigId": ssoRegisterWidgetConfigId,
            "ssoLoginWidgetConfigId": ssoLoginWidgetConfigId
        }
        try:
            response = requests.post(
                url=url,
                data=payload,
                headers=headers
            )
            return response
        except requests.exceptions.RequestException as e:
            logging.error(f"SSO login API request error: {str(e)}")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @staticmethod
    def get_token(
        self,
        email: str,
        program_id,
    ) -> str:
        """
        Generate a JWT token that will be used to access NextBee member resources.
        """
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.generate_jwt_token(nextbee_advertiser_id, email)}"
        }

        url = f"{nextbee_base_url}/client/api-token"
        payload = {
            "env": nextbee_environment,
            "email": email,
            "programId": program_id,
        }
        try:
            response = requests.post(
                url=url,
                data=payload,
                headers=headers
            )
            return response.json().get("token", "No token found in response")
        except requests.exceptions.RequestException as e:
            logging.error(f"Generate token API request error: {str(e)}")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @staticmethod
    def member_activity(
        self,
        member_email,
        activityId,
        numericValue
    ) -> str:
        """
        Register member activity on NextBee.
        """
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.get_token(nextbee_advertiser_id, admin_email)}"
        }

        url = f"{nextbee_base_url}/client/member/activity"
        payload = {
            "widgetConfigId": widget_config,
            "email": member_email,
            "activityId": activityId,
            "numericValue": numericValue,
        }
        try:
            response = requests.post(
                url=url,
                data=payload,
                headers=headers
            )
            return Response(data=response.json(), status=response.status_code)
        except requests.exceptions.RequestException as e:
            logging.error(f"Member activity API request error: {str(e)}")
            return Response(
                data={"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
