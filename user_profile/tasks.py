import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def broadcast_push(title, body, data=None, sent_by=None):
    """
    Admin "all users" push (roles.members.SendPushNotificationView). Runs off
    the request path since it fans out to every registered device. Disabled
    accounts are skipped.
    """
    from user_profile.fcm import send_push_multicast, FCM_MULTICAST_LIMIT
    from user_profile.models import DeviceToken

    # exclude(), not filter(is_disabled=False) - the column is nullable and
    # NULL means "not disabled".
    tokens = DeviceToken.objects.exclude(user__is_disabled=True).values_list(
        "token", flat=True
    )
    batch, sent, total = [], 0, 0
    for token in tokens.iterator(chunk_size=FCM_MULTICAST_LIMIT):
        batch.append(token)
        if len(batch) == FCM_MULTICAST_LIMIT:
            sent += send_push_multicast(batch, title, body, data)
            total += len(batch)
            batch = []
    if batch:
        sent += send_push_multicast(batch, title, body, data)
        total += len(batch)

    logger.info(
        "Admin broadcast push by %s: %d/%d devices delivered (title=%r)",
        sent_by,
        sent,
        total,
        title,
    )
    return {"devices_targeted": total, "devices_sent": sent}


# Recipients per YourNotify campaign call.
ADMIN_MESSAGE_BATCH_SIZE = 100


def admin_message_recipients(message):
    """Distinct phone numbers (sms) or emails (email) for an AdminMessage's
    audience. Disabled accounts are skipped."""
    from accounts.models import User

    users = User.objects.exclude(is_disabled=True)
    if message.audience == "selected":
        users = users.filter(id__in=message.user_ids)
    elif message.audience == "members":
        users = users.filter(account_types__user_type="Member")

    field = "phone_number" if message.channel == "sms" else "email"
    return list(
        users.exclude(**{f"{field}__isnull": True})
        .exclude(**{field: ""})
        .values_list(field, flat=True)
        .distinct()
    )


@shared_task
def send_admin_message(message_id):
    """
    Delivers an AdminMessage (roles.members.SendMessageView) in batched
    YourNotify campaigns. The queued -> sending claim makes a redelivered
    task a no-op, so a message is never sent twice.
    """
    from commons import Messaging
    from roles.models import AdminMessage

    claimed = AdminMessage.objects.filter(id=message_id, status="queued").update(
        status="sending"
    )
    if not claimed:
        logger.warning("AdminMessage %s already claimed, skipping", message_id)
        return None

    message = AdminMessage.objects.get(id=message_id)
    recipients = admin_message_recipients(message)
    sent, errors = 0, []
    for i in range(0, len(recipients), ADMIN_MESSAGE_BATCH_SIZE):
        batch = recipients[i : i + ADMIN_MESSAGE_BATCH_SIZE]
        try:
            if message.channel == "sms":
                response = Messaging.send_bulk_sms(batch, message.body)
            else:
                response = Messaging.send_bulk_email(
                    batch, message.subject, message.body
                )
        except Exception as exc:
            logger.exception("AdminMessage %s batch %d failed", message_id, i)
            errors.append(str(exc))
            continue
        if isinstance(response, dict) and response.get("status") == "success":
            sent += len(batch)
        else:
            errors.append(str(response)[:500])

    if not recipients or sent == len(recipients):
        message.status = "sent"
    else:
        message.status = "partial" if sent else "failed"
    message.recipients_targeted = len(recipients)
    message.recipients_sent = sent
    message.error = "\n".join(errors)[:5000]
    message.save(
        update_fields=[
            "status",
            "recipients_targeted",
            "recipients_sent",
            "error",
            "updated_at",
        ]
    )
    logger.info(
        "AdminMessage %s (%s to %s) by %s: %d/%d sent",
        message_id,
        message.channel,
        message.audience,
        message.sent_by_id,
        sent,
        len(recipients),
    )
    return {"recipients_targeted": len(recipients), "recipients_sent": sent}
