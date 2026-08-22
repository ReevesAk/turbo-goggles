import math
import random
import logging
import token
import requests
from decimal import Decimal


def is_slot_target_reached(slot_cap, slots_filled) -> bool:
    """
    Campaigns are allowed to close early: once slots_filled falls in the top
    15% of slot_cap (85%-100%), a fresh random point within that band is
    rolled and compared against slots_filled. slots_filled never exceeds
    slot_cap regardless. The random point is not persisted, so this can
    return a different answer on repeated calls while slots_filled sits in
    the band.
    """
    if not slot_cap:
        return False
    slots_filled = slots_filled or 0
    if slots_filled >= slot_cap:
        return True
    floor = math.ceil(slot_cap * 0.85)
    if slots_filled < floor:
        return False
    target = random.randint(floor, slot_cap)
    return slots_filled >= target


def first_validation_error(detail) -> str:
    """Recursively extract the first human-readable string from a DRF error detail structure."""
    if isinstance(detail, list):
        return first_validation_error(detail[0]) if detail else ""
    if isinstance(detail, dict):
        for v in detail.values():
            msg = first_validation_error(v)
            if msg:
                return msg
    return str(detail)


from decouple import config

from accounts.models import User
from gamification.models import Points as PointsModel
from gamification.points import Points as PointsEngine, TIER_VALUES

yournotify_api_key = config("YOURNOTIFY_API_KEY")
yournotify_base_url = config("YOURNOTIFY_BASE_URL")


def generateOTP(OTP):
    digits = "0123456789"
    OTP = ""
    for i in range(6):
        OTP += digits[math.floor(random.random() * 10)]
        return OTP


def upload_to(instance, filename):
    return "profile/{filename}".format(filename=filename)


def generate_txId():
    tx_id = random.randint(100000000000000, 999999999999999)
    return tx_id


class Biometrics:
    @staticmethod
    def authenticate(phone_number):
        try:
            # Retrieve user with biometrics enabled
            user = User.objects.get(phone_number=phone_number)
            return user
        except User.DoesNotExist:
            logging.error("User with biometrics not found or not enabled")
            return None


class Messaging:
    def send_email(email, html_content, sender_email, subject, body):
        url = yournotify_base_url + "campaigns/email/"

        headers = {
            "Authorization": yournotify_api_key,
            "Content-Type": "application/json"
        }

        payload = {
            "name": "Picadailys Email",
            "from": sender_email,
            "subject": subject,
            "html": html_content,
            "text": body,
            "status": "running",
            "lists": [
                email
            ],
            "channel": "email",
        }
        response = requests.post(url, headers=headers, json=payload)
        return response.json()

    def send_email_with_attachment(
            email, html_content,
            sender_email, subject,
            body, media_id
        ):
        url = yournotify_base_url + "campaigns/email/"

        headers = {
            "Authorization": yournotify_api_key,
            "Content-Type": "application/json"
        }

        payload = {
            "name": "Picadailys Email",
            "from": sender_email,
            "subject": subject,
            "html": html_content,
            "text": body,
            "status": "running",
            "lists": [
                email
            ],
            "channel": "email",
            "media": [
                media_id
            ]
        }
        response = requests.post(url, headers=headers, json=payload)
        return response.json()

    @staticmethod
    def _normalize_phone(phone_number: str) -> str:
        """Always returns 10-digit local number (e.g. 8134649680) ready for 234 prefix."""
        p = phone_number.strip().lstrip("+")
        if p.startswith("234"):
            p = p[3:]
        elif p.startswith("0"):
            p = p[1:]
        return p

    @staticmethod
    def send_sms(phone_number, msg):
        url = yournotify_base_url + "campaigns/sms/"

        headers = {
            "Authorization": yournotify_api_key,
            "Content-Type": "application/json"
        }
        phone = "234" + Messaging._normalize_phone(phone_number)
        payload = {
            "name": "Picadailys SMS",
            "from": "PICADAILYS",
            "text": msg,
            "status": "running",
            "lists": [
                phone
            ],
            "channel": "sms",
        }
        response = requests.post(url, headers=headers, json=payload)
        return response.json()
    
    @staticmethod
    def whatsApp(phone_number, otp):
        url = yournotify_base_url + "campaigns/whatsapp/"

        headers = {
            "Authorization": yournotify_api_key,
            "Content-Type": "application/json"
        }

        phone = "234" + Messaging._normalize_phone(phone_number)
        payload = {
            "name": "Picadailys OTP",
            "status": "running",
            "send_at": None,
            "lists": [
            phone
            ],
            "channel": "whatsapp",
            "from": "1038875632647675",
            "template_id": "auth_verify_code:en_US",
            "template_params": [
                "#123456",
                "Delivered"
            ],
            "attribs": {
        "whatsapp_template": {
            "name": "auth_verify_code",
            "language": "en_US"
        },
        "template_id": "auth_verify_code:en_US",
        "template_name": "auth_verify_code",
        "components": [
            {
            "type": "body",
            "parameters": [
                {
                "type": "text",
                "text": otp
                }
            ]
            },
            {
            "type": "button",
            "sub_type": "url",
            "index": "0",
            "parameters": [
                {
                "type": "text",
                "text": otp
                }
            ]
            }
        ]
        }
    }
        response = requests.post(url, headers=headers, json=payload)
        return response.json()

    @staticmethod
    def _otp_sent(response):
        try:
            return response.get("status") == "success"
        except Exception:
            return False

    @staticmethod
    def send_otp_whatsapp_first(phone_number, otp, msg):
        """WhatsApp first, SMS fallback — used for registration."""
        try:
            result = Messaging.whatsApp(phone_number=phone_number, otp=otp)
            if Messaging._otp_sent(result):
                return
        except Exception:
            pass
        try:
            Messaging.send_sms(phone_number=phone_number, msg=msg)
        except Exception:
            pass

    @staticmethod
    def send_otp_whatsapp_fallback(phone_number, otp, msg):
        """SMS first, WhatsApp fallback — used on resend for non-registration OTPs."""
        try:
            result = Messaging.send_sms(phone_number=phone_number, msg=msg)
            if Messaging._otp_sent(result):
                return
        except Exception:
            pass
        try:
            Messaging.whatsApp(phone_number=phone_number, otp=otp)
        except Exception:
            pass


class Allocate:
    @staticmethod
    def reward(amount):
        rewards = (amount / 100) * 0.5
        return rewards


class Pay:
    @staticmethod
    def with_pts(user, amount):
        """
        Pay for a purchase using points converted to naira at the user's own
        tier rate (same rate RedeemPointsToWallet uses), with no minimum
        balance requirement.

        Deduction: proportional — only the points worth the exact naira `amount`
        are deducted, not a flat 400.

        Returns:
          ("Enough",     amount)        — full amount covered, points deducted
          ("Not Enough", naira_available) — balance too low, nothing deducted
          ("Not Found",  0)             — user has no Points record
        """
        try:
            pts = PointsModel.objects.get(user=user)
        except PointsModel.DoesNotExist:
            return "Not Found", 0

        tier_rate = TIER_VALUES.get(pts.tier, Decimal("0"))
        naira_available = pts.balance * tier_rate
        if naira_available <= Decimal("0"):
            return "Not Enough", 0

        amount_dec = Decimal(str(amount))
        if naira_available < amount_dec:
            return "Not Enough", naira_available

        # Calculate proportional points to deduct
        points_to_deduct = math.ceil(amount_dec / tier_rate)

        PointsEngine.deduct(
            user=user,
            amount=points_to_deduct,
            reason=f"Purchase payment of ₦{amount}",
            source="service_purchase",
        )
        return "Enough", amount

    @staticmethod
    def refund_pts(user, naira_amount):
        """
        Refund points after a failed or reversed purchase.
        Bypasses credibility check — this is a restoration, not a reward.
        Uses the user's current tier rate, same as with_pts.
        """
        try:
            pts = PointsModel.objects.get(user=user)
        except PointsModel.DoesNotExist:
            return

        tier_rate = TIER_VALUES.get(pts.tier, Decimal("0"))
        if tier_rate <= Decimal("0"):
            return

        points_to_refund = math.ceil(Decimal(str(naira_amount)) / tier_rate)

        PointsEngine.award(
            user=user,
            amount=points_to_refund,
            reason=f"Refund for reversed purchase of ₦{naira_amount}",
            source="admin_adjustment",
            bypass_credibility=True,
        )


# class CamelCaseJSONRenderer(JSONRenderer):
#     def render(self, data, accepted_media_type=None, renderer_context=None):
#         if isinstance(data, dict):
#             data = {inflection.camelize(key, False): value for key, value in data.items()}
#         elif isinstance(data, list):
#             data = [{inflection.camelize(key, False): value for key, value in item.items()} for item in data]
#         return super().render(data, accepted_media_type, renderer_context)
