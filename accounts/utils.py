import logging
from decouple import config

import cloudinary
import cloudinary.uploader
import cloudinary.api

from django.core.validators import URLValidator
from rest_framework.validators import ValidationError


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
