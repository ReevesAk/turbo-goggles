import logging
import json
import requests
from decouple import config

from rest_framework import status
from rest_framework.response import Response

app_id = config("APP_ID")
authorization = config("AUTHORIZATION")
base_url = config("DOJAH_BBASE_URL")


class CAC:
    @staticmethod
    def verify(rc_number, business_name):
        resource = "/api/v1/kyc/cac/basic"
        payload = {"rc_number": rc_number, "company_type": business_name}
        headers = {
            "AppId": app_id,
            "Authorization": authorization,
        }

        try:
            response = requests.get(
                url=base_url + resource,
                json=payload,
                headers=headers,
            )
            return response
        except requests.exceptions.RequestException as e:
            logging.error(f"CAC lookup API request error: {str(e)}")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
