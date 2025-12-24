import logging

from django.template.loader import render_to_string

from accounts.models import UserNotification
from roles.models import ActivityModel

from commons import Messaging

logger = logging.getLogger(__name__)


def create_notification(user, title, message):
    UserNotification.objects.create(user=user, title=title, message=message)


def create_activity(user, title, description):
    ActivityModel.objects.create(
        user=user,
        title=title,
        description=description,
    )


def send_token(user, msg):
    recipient = user.phone_number[1:]

    Messaging.send_sms(phone_number=recipient, msg=str(msg))
    logger.info(
        "Electricity token sent to user %s at %s and %s", user.id, recipient, user.email
    )

    # Render the template with values
    text_content = render_to_string(
        template_name="empty_email.html",
        context={
            "custom_text": f"Dear {user.first_name},<br><br>{msg}.",
            "support_email": "support@picadailys.com",
            "picadailys_phone": "+123 456 7890",
        },
    )

    Messaging.send_email(
        sender_email="notifications@picadailys.com",
        body=msg,
        email=user.email,
        html_content=text_content,
        subject="Electricity Token",
    )


def send_token_to_guest_users(guest_phone, msg):
    recipient = guest_phone[1:]

    Messaging.send_sms(phone_number=recipient, msg=str(msg))
    logger.info(
        "Electricity token sent to guest user with phone number %s",
        guest_phone,
        recipient,
    )
