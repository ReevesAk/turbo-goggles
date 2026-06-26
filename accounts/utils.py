import logging
from decouple import config

import cloudinary
import requests

from django.core.validators import URLValidator
from rest_framework.validators import ValidationError
from rest_framework.response import Response
from rest_framework import status


def mask_email(email: str) -> str:
    if not email or "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    return local[:2] + "***@" + domain


def mask_phone(phone: str) -> str:
    if not phone or len(phone) < 5:
        return "***"
    return phone[:3] + "***" + phone[-4:]


class Liveness:
    @staticmethod
    def check(image):
        app_id = config("APP_ID")
        authorization = config("AUTHORIZATION")
        resource = "https://api.dojah.io/api/v1/ml/liveness/"
        payload = {"image": image}
        headers = {
            "AppId": app_id,
            "Authorization": authorization,
        }

        try:
            response = requests.post(
                url=resource,
                json=payload,
                headers=headers,
            )
            return response
        except requests.exceptions.RequestException as e:
            logging.error(f"liveness check API request error: {str(e)}")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# file_uploader handles the uploads of media files
# cloud storage using cloudinary.
def file_uploader():
    cloudinary.config(
        cloud_name=config("CLOUDINARY_CLOUD_NAME"),
        api_key=config("CLOUDINARY_API_KEY"),
        api_secret=config("CLOUDINARY_API_SECRET"),
    )


def validate_url(to_validate: str) -> bool:
    validator = URLValidator()
    try:
        validator(to_validate)
        return True
    except ValidationError as exception:
        logging.error(exception)
        return False
