import math
import random
import requests
import logging

import ElasticEmail
from ElasticEmail import EmailsApi, ApiClient
from ElasticEmail.models import (
    EmailContent,
    BodyPart,
    BodyContentType,
    EmailRecipient,
    EmailMessageData,
)

from rest_framework.response import Response
from rest_framework import status

from decouple import config

from accounts.models import User
from roles.models import Points

termii_base_url = config("TERMII_BASE_URL")
termii_api_key = config("TERMII_API_KEY")
elastic_api_key = config("ELASTIC_API_KEY")


def generateOTP(OTP):
    digits = "0123456789"
    OTP = ""
    for i in range(6):
        OTP += digits[math.floor(random.random() * 10)]
        return OTP


def upload_to(instance, filename):
    return "profile/{filename}".format(filename=filename)


def generate_txId():
    tx_id = random.randint(100000000000000, 999999999999999)
    return tx_id


class Biometrics:
    @staticmethod
    def authenticate(phone_number):
        try:
            # Retrieve user with biometrics enabled
            user = User.objects.get(phone_number=phone_number)
            return user
        except User.DoesNotExist:
            logging.error("User with biometrics not found or not enabled")
            return None


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
            if response.status_code == 200:
                return Response(response.json())
            else:
                error_resp = "Error from server: " + str(response.json())

                return Response(error_resp)
        except requests.exceptions.RequestException as e:
            error_msg = {"error": str(e)}

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

            if response.status_code == 200:

                return Response(response.json())
            else:
                error_resp = "Error from server: " + str(response.json())

                return Response(error_resp)
        except requests.exceptions.RequestException as e:
            error_msg = {"error": str(e)}

            return Response(
                data=error_msg, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def send_email(email, html_content, subject):
        configuration = ElasticEmail.Configuration()
        configuration.api_key['apikey'] = elastic_api_key

        with ApiClient(configuration) as api_client:
            api_instance = EmailsApi(api_client)

            email_data = EmailMessageData(
                recipients=[
                    EmailRecipient(email=email)
                ],
                content=EmailContent(
                    body=[
                        BodyPart(
                            content_type=BodyContentType("HTML"),
                            content=html_content,
                            charset="utf-8",
                        ),
                    ],
                    From="Alert@picadailys.com",
                    reply_to="",
                    subject=subject,
                ),
            )

            try:
                # Send email using Elastic Email API
                response = api_instance.emails_post(email_data)
                logging("Email sent successfully!")
                logging(response)
            except Exception as e:
                logging("Error occurred while sending email:", e)


class Allocate:
    @staticmethod
    def reward(amount):
        rewards = (amount / 100) * 0.5
        return rewards


class Pay:
    @staticmethod
    def with_rwd(user, amount):
        try:
            rwd = Points.objects.get(user=user)
        except Points.DoesNotExist:
            return "Not Found", 0

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
        try:
            pts = Points.objects.get(user=user)
        except Points.DoesNotExist:
            return "Not Found", 0
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


# class CamelCaseJSONRenderer(JSONRenderer):
#     def render(self, data, accepted_media_type=None, renderer_context=None):
#         if isinstance(data, dict):
#             data = {inflection.camelize(key, False): value for key, value in data.items()}
#         elif isinstance(data, list):
#             data = [{inflection.camelize(key, False): value for key, value in item.items()} for item in data]
#         return super().render(data, accepted_media_type, renderer_context)
