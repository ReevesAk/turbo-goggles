import math
import random
import requests

from rest_framework.response import Response
from rest_framework import status

from decouple import config

from accounts.models import Rewards
from roles.models import Points

termii_base_url = config("TERMII_BASE_URL")
termii_api_key = config("TERMII_API_KEY")


def generateOTP(OTP):
    digits = "0123456789"
    OTP = ""
    for i in range(6):
        OTP += digits[math.floor(random.random() * 10)]
        return OTP


def upload_to(instance, filename):
    return "profile/{filename}".format(filename=filename)


class Message:
    @staticmethod
    def send_otp(msg, to):
        resource = "/api/sms/send"
        headers = {
            "Content-Type": "application/json",
        }

        phone_number = "234" + to

        payload = {
            "to": phone_number,
            "from": "N-Alert",
            "sms": msg,
            "type": "plain",
            "channel": "dnd",
            "api_key": termii_api_key,
        }
        try:
            response = requests.request(
                "POST",
                url=termii_base_url + resource,
                headers=headers,
                json=payload,
            )
            print(termii_base_url + resource)
            print(payload)
            if response.status_code == 200:
                return Response(response.json())
            else:
                error_resp = "Error from server: " + str(response.json())
                print(error_resp)
                return Response(error_resp)
        except requests.exceptions.RequestException as e:
            error_msg = {"error": str(e)}
            print(error_msg)
            return Response(
                data=error_msg, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @staticmethod
    def send_msg(msg, to):
        resource = "/api/sms/send"
        headers = {
            "Content-Type": "application/json",
        }

        phone_number = "234" + to

        payload = {
            "to": phone_number,
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
            print(termii_base_url + resource)
            print(payload)
            if response.status_code == 200:
                print()
                return Response(response.json())
            else:
                error_resp = "Error from server: " + str(response.json())
                print(error_resp)
                return Response(error_resp)
        except requests.exceptions.RequestException as e:
            error_msg = {"error": str(e)}
            print(error_msg)
            return Response(
                data=error_msg, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class Allocate:
    @staticmethod
    def reward(amount):
        rewards = (amount / 100) * 0.5
        return rewards


class Pay:
    @staticmethod
    def with_rwd(user, amount):
        rwd = Rewards.objects.get(user=user)
        deducted_amount = (0.30 * amount) * 0.5

        if rwd.balance >= deducted_amount:
            rwd.balance -= deducted_amount
            rwd.save()
            return "Enough", deducted_amount
        else:
            deducted_amount = rwd.balance
            rwd.balance = 0
            rwd.save()
            return "Not Enough", deducted_amount

    @staticmethod
    def with_pts(user, amount):
        pts = Points.objects.get(user=user)
        deducted_amount = 0.20 * amount

        if pts.balance >= deducted_amount:
            pts.balance -= deducted_amount
            pts.save()
            return "Enough", deducted_amount
        else:
            deducted_amount = pts.balance
            pts.balance = 0
            pts.save()
            return "Not Enough", deducted_amount
