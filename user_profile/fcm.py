import logging

import firebase_admin
from firebase_admin import credentials, messaging
from decouple import config as conf

from user_profile.models import DeviceToken

logger = logging.getLogger(__name__)

_firebase_app = None


def _get_app():
    """Lazy-initialise the Firebase Admin SDK app once."""
    global _firebase_app
    if _firebase_app is not None:
        return _firebase_app

    cred_path = conf("FIREBASE_CREDENTIALS_PATH", default=None)
    if not cred_path:
        logger.warning(
            "FIREBASE_CREDENTIALS_PATH not set — push notifications are disabled"
        )
        return None

    try:
        cred = credentials.Certificate(cred_path)
        _firebase_app = firebase_admin.initialize_app(cred)
    except Exception:
        logger.exception("Failed to initialise Firebase Admin SDK")

    return _firebase_app


def send_push(token: str, title: str, body: str, data: dict = None) -> bool:
    """
    Send a single FCM push notification to one device token.
    Returns True on success, False on failure.
    Automatically removes stale (unregistered) tokens from the DB.
    """
    if not _get_app():
        return False

    try:
        message = messaging.Message(
            notification=messaging.Notification(title=title, body=body),
            data={k: str(v) for k, v in (data or {}).items()},
            token=token,
        )
        messaging.send(message)
        logger.debug("FCM push sent to token …%s", token[-8:])
        return True

    except messaging.UnregisteredError:
        DeviceToken.objects.filter(token=token).delete()
        logger.info("Removed stale FCM token …%s", token[-8:])
        return False

    except Exception:
        logger.exception("FCM send failed for token …%s", token[-8:])
        return False


def send_push_to_user(user, title: str, body: str, data: dict = None) -> int:
    """
    Send a push notification to every registered device for `user`.
    Returns the number of successful sends.
    """
    tokens = list(DeviceToken.objects.filter(user=user).values_list("token", flat=True))
    if not tokens:
        return 0

    return sum(1 for t in tokens if send_push(t, title, body, data))
