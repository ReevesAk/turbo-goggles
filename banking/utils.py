import logging
from datetime import datetime, date

from commons import Messaging

logger = logging.getLogger(__name__)

_DOB_FORMATS = ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d")


def normalize_ng_phone(phone: str | None) -> str | None:
    """
    Normalize a Nigerian phone number to country-code format ("234XXXXXXXXXX").
    """
    if not phone:
        return None

    digits = "".join(c for c in str(phone) if c.isdigit())

    if not digits:
        return None

    # Messaging._normalize_phone strips one leading "234" or "0" per call.
    # Calling it twice collapses even a double-prefixed "234" + "0" + local
    # number down to the bare 10-digit local number in one pass.
    local = Messaging._normalize_phone(digits)
    local = Messaging._normalize_phone(local)

    if len(local) == 10:
        return "234" + local

    # Unknown/malformed shape — log and return None rather than persisting garbage.
    logger.warning("Unrecognized NG phone format, cannot normalize: %r", phone)
    return None


def parse_dojah_dob(raw) -> date | None:
    """
    Parse a Dojah date_of_birth value to a Python date.
    Returns None if the value can't be parsed, so callers can fail closed.
    """
    if not raw:
        return None
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw

    s = str(raw).strip()
    for fmt in _DOB_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue

    try:
        return datetime.fromisoformat(s.replace("Z", "")).date()
    except ValueError:
        logger.warning("Unrecognized DOB format from Dojah: %r", raw)
        return None


def format_dob_for_9psb(dob: str | None) -> str | None:
    """
    Render a stored DOB string in the DD/MM/YYYY format 9PSB expects.
    """
    parsed = parse_dojah_dob(dob)
    if not parsed:
        return None
    return parsed.strftime("%d/%m/%Y")
