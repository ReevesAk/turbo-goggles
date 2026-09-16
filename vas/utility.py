import logging

from django.db import transaction
from django.template.loader import render_to_string

from accounts.models import TxModel, UserNotification
from roles.models import ActivityModel

from commons import Messaging

logger = logging.getLogger(__name__)


def create_notification(user, title, message):
    UserNotification.objects.create(user=user, title=title, message=message)


def create_activity(user=None, title=None, description=None, guest_id=None):
    if guest_id and not user:
        description = f"{description} [guest_id={guest_id}]"
    ActivityModel.objects.create(
        user=user,
        title=title,
        description=description,
    )


def complete_data_purchase(
    user,
    tx_reference,
    amount,
    phone,
    network,
    account_number="",
    is_task=False,
    task_id=None,
):
    """Shared success side effects for a data purchase - TxModel write,
    cashback reward, wallet/notification sync via post_vas_update. Used by
    both the synchronous DataSubscriptionView flow and the async pending-
    transaction reconciler, so a purchase 9PSB confirms after the request
    window still completes the same way."""
    from banking.cashback_service import CashbackService
    from banking.tasks import post_vas_update

    title = "Data purchase"
    message = f"This is to inform you that you have made a data purchase of {amount} naira data on {phone}."
    description = (
        f"{user.first_name} {user.last_name} "
        f"has made a purchase of {amount} naira data on {phone}."
    )
    create_notification(user=user, title=title, message=message)
    create_activity(user=user, title=title, description=description)
    try:
        with transaction.atomic():
            TxModel.objects.update_or_create(
                tx_reference=tx_reference,
                defaults={
                    "user": user,
                    "tx_type": "Data",
                    "amount": amount,
                    "description": title,
                    "status": "SUCCESS",
                    "is_task": is_task,
                    "task_id": task_id,
                },
            )
            CashbackService.reward_cashback(
                user=user, amount=amount, service="data", tx_ref=tx_reference
            )
    except Exception as e:
        logger.error(f"Database query error: {str(e)}")

    post_vas_update.delay(
        user_id=user.id,
        account_number=account_number,
        amount_str=str(amount),
        tx_reference=tx_reference,
        service_type="DATA",
        phone=phone,
        network=network,
        alert_type=getattr(user, "alert_type_choice", "Both"),
        phone_number=getattr(user, "phone_number", None),
        email=getattr(user, "email", None),
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
            "picadailys_phone": [
                "02012271894",
                "02012271895",
            ],
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
