import smtplib
from email.mime.text import MIMEText
import smtplib
from decouple import config

import cloudinary
import cloudinary.uploader
import cloudinary.api

from django.core.validators import URLValidator
from rest_framework.validators import ValidationError


# send_email handles the sending of emails to user.
def send_email(subject, body, sender, recipients, password):
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp_server:
        smtp_server.login(sender, password)
        smtp_server.sendmail(sender, recipients, msg.as_string())


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
        print(exception)
        return False
