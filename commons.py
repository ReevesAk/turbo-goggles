import math
import random
import logging
import token
import requests
from decimal import Decimal


from decouple import config

from accounts.models import User
from gamification.models import Points as PointsModel
from gamification.points import Points as PointsEngine, MIN_POINTS_REQUIRED, TIER_VALUES

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
    def send_sms(phone_number, msg):
        url = yournotify_base_url + "campaigns/sms/"

        headers = {
            "Authorization": yournotify_api_key,
            "Content-Type": "application/json"
        }
        phone = "234" + phone_number
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

        phone = "234" + phone_number
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
            "name": "auth_login_code",
            "language": "en_US"
        },
        "template_id": "auth_login_code:en_US",
        "template_name": "auth_login_code",
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
        Pay for a purchase using points converted to naira.

        Eligibility: user must hold at least MIN_POINTS_REQUIRED (400) points.
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

        # Must hold the minimum threshold to unlock point payments
        if pts.balance < MIN_POINTS_REQUIRED:
            return "Not Enough", 0

        naira_available = pts.naira_value
        if naira_available <= Decimal("0"):
            return "Not Enough", 0

        amount_dec = Decimal(str(amount))
        if naira_available < amount_dec:
            return "Not Enough", naira_available

        # Calculate proportional points to deduct
        tier_rate = TIER_VALUES.get(pts.tier, Decimal("0.50"))
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
        """
        try:
            pts = PointsModel.objects.get(user=user)
        except PointsModel.DoesNotExist:
            return

        tier_rate = TIER_VALUES.get(pts.tier, Decimal("0.50"))
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
