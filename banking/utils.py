import logging

logger = logging.getLogger(__name__)


def normalize_ng_phone(phone: str | None) -> str | None:
    """
    Normalize a Nigerian phone number to country-code format ("234XXXXXXXXXX").
    """
    if not phone:
        return None

    digits = "".join(c for c in str(phone) if c.isdigit())

    if not digits:
        return None

    # 11 digits starting with 0 (local trunk format)
    if len(digits) == 11 and digits.startswith("0"):
        return "234" + digits[1:]

    # 13 digits already in country-code format
    if len(digits) == 13 and digits.startswith("234"):
        return digits

    # 10 digits missing the trunk 0
    if len(digits) == 10:
        return "234" + digits

    # Unknown length — log and return None rather than persisting garbage.
    logger.warning("Unrecognized NG phone format, cannot normalize: %r", phone)
    return None
