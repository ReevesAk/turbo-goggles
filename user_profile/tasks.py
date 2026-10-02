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
