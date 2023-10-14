import math
import random
import requests

from rest_framework.response import Response
from rest_framework import status

from decouple import config

termii_base_url = config("TERMII_BASE_URL")
termii_api_key = config("TERMII_API_KEY")

def generateOTP(OTP) :
    digits = "0123456789"
    OTP = ""
    for i in range(6) :
        OTP += digits[math.floor(random.random() * 10)]
        return OTP

def upload_to(instance, filename):
    return 'profile/{filename}'.format(filename=filename)


class Messsage:
    @staticmethod
    def send_otp(msg, to):
        
        resource = "/api/sms/send"
        headers = {
            'Content-Type': 'application/json',
        }

        payload = {
            "to": to,
            "from": "Picadailys",
            "sms": msg,
            "type": "plain",
            "channel": "generic",
            "api_key": termii_api_key,
        }
        try:
            response = requests.request(
                "POST",
                url=termii_base_url + resource,
                headers=headers,
                json=payload,
            )
            if response.status_code == 200:
                return Response(response.json())
            else:
                return Response("Error from server: " + str(response.json()))
        except requests.exceptions.RequestException as e:
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
