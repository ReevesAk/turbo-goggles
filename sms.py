from decouple import config

from rest_framework.response import Response
from rest_framework import status
from twilio.rest import Client


auth_token = config('TWILIO_AUTH_TOKEN')
account_sid = config('TWILIO_ACCOUNT_SID')
picadailys = config('PACADAILYS_NO')


class Message:
    @staticmethod
    def send_otp(msg, to):

        phone_number = "+234" + to

        try:
            client = Client(
                account_sid,
                auth_token
            )
            message = client.messages.create(
                from_=picadailys,
                to=phone_number,
                body=msg
            )
            return message
        except Exception as error_msg:
            print(error_msg)
            return Response(
                data=error_msg, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
