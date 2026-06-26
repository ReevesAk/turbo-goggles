import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from accounts.models import OTP, UserNotification, DeviceId
from roles.models import ActivityModel

logger = logging.getLogger(__name__)


@shared_task(name="accounts.tasks.purge_expired_otps")
def purge_expired_otps():
    deleted, _ = OTP.objects.filter(expires_at__lt=timezone.now()).delete()
    logger.info("purge_expired_otps: removed %d record(s)", deleted)


@shared_task(name="accounts.tasks.purge_old_notifications")
def purge_old_notifications():
    cutoff = timezone.now() - timedelta(days=90)
    deleted, _ = UserNotification.objects.filter(created_at__lt=cutoff).delete()
    logger.info(
        "purge_old_notifications: removed %d record(s) older than 90 days", deleted
    )


@shared_task(name="accounts.tasks.purge_old_activity_logs")
def purge_old_activity_logs():
    cutoff = timezone.now() - timedelta(days=365)
    deleted, _ = ActivityModel.objects.filter(created_at__lt=cutoff).delete()
    logger.info(
        "purge_old_activity_logs: removed %d record(s) older than 12 months", deleted
    )


@shared_task(name="accounts.tasks.purge_stale_devices")
def purge_stale_devices():
    cutoff = timezone.now() - timedelta(days=365)
    deleted, _ = DeviceId.objects.filter(created_at__lt=cutoff).delete()
    logger.info(
        "purge_stale_devices: removed %d device record(s) older than 12 months", deleted
    )
