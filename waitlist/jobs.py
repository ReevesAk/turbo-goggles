import logging
from datetime import timedelta
from django.utils import timezone
from .models import WaitlistModel

logger = logging.getLogger(__name__)


def remove_unverified_waitlist_users():
    cutoff = timezone.now() - timedelta(days=7)
    qs = WaitlistModel.objects.filter(is_verified=False, joined_at__lt=cutoff)
    count, _ = qs.delete()
    logger.info(f"Removed {count} unverified waitlist users older than 7 days.")
