import io
import logging
import secrets
import string

import cloudinary.uploader
import qrcode
from celery import shared_task

from commons import Messaging

logger = logging.getLogger(__name__)


def _make_visit_code(brand_name: str) -> str:
    """Generate a unique short code with the brand acronym as prefix, e.g. 'PIC-A3X9K2'."""
    words = (brand_name or "").split()
    acronym = "".join(w[0].upper() for w in words if w)[:4] or "ST"
    alphabet = string.ascii_uppercase + string.digits
    suffix = "".join(secrets.choice(alphabet) for _ in range(6))
    return f"{acronym}-{suffix}"


def generate_qr_image_and_upload(token: str) -> str:
    """Generate a QR code PNG for the given token, upload to Cloudinary, and return the secure URL."""
    qr_content = f"picadailys://store-visit?token={token}"
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(qr_content)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    try:
        upload_result = cloudinary.uploader.upload(
            buffer,
            folder="store_visit_qr",
            public_id=token,
            resource_type="image",
            overwrite=False,
        )
        return upload_result.get("secure_url", "")
    except Exception:
        logger.exception("Failed to upload QR code to Cloudinary for token %s", token)
        return ""


@shared_task
def email_qr_to_brand_task(ad_id: int):
    """Send the QR code image and visit code to the brand by email."""
    from .models import CreateAd, StoreVisitQRCode

    try:
        ad = CreateAd.objects.select_related("user").get(pk=ad_id)
        qr_obj = StoreVisitQRCode.objects.get(ad=ad)
    except (CreateAd.DoesNotExist, StoreVisitQRCode.DoesNotExist):
        logger.error(
            "email_qr_to_brand_task: ad or QR record not found for ad %s", ad_id
        )
        return

    _email_qr_to_brand(ad, qr_obj.qr_image_url, qr_obj.visit_code)


def _email_qr_to_brand(ad, qr_image_url: str, visit_code: str):
    brand_user = ad.user
    html = (
        f"<p>Hi <strong>{brand_user.full_name or brand_user.email}</strong>,</p>"
        f"<p>Your Store Visit QR code and access code for the campaign "
        f"<strong>{ad.campaign_name}</strong> are ready.</p>"
        f"<p>Display these at your store. Visitors scan the QR code with the Picadailys app, "
        f"or enter the access code manually if they cannot scan — "
        f"either way their visit is recorded and they earn <strong>{ad.reward_points} points</strong>.</p>"
        f"<div style='text-align:center;margin:24px 0'>"
        f"<img src='{qr_image_url}' alt='Store Visit QR Code' style='width:220px;height:220px;' />"
        f"<p style='font-size:28px;font-weight:bold;letter-spacing:4px;margin:12px 0'>{visit_code}</p>"
        f"<p style='color:#888;font-size:12px'>Manual entry code — share this if visitors cannot scan the QR</p>"
        f"</div>"
        f"<p style='color:#666;font-size:13px;'>Campaign: {ad.campaign_name}<br>"
        f"Reward per visit: {ad.reward_points} pts<br>"
        f"Slots available: {ad.slot_cap}</p>"
        f"<p>You can also <a href='{qr_image_url}'>download the QR code image here</a> and print it.</p>"
    )
    try:
        Messaging.send_email(
            email=brand_user.email,
            sender_email="notifications@picadailys.com",
            subject=f"Your Store Visit QR Code & Access Code — {ad.campaign_name}",
            html_content=html,
            body=(
                f"Your Store Visit QR code and access code for '{ad.campaign_name}' are ready. "
                f"Access code: {visit_code}. "
                f"QR code image: {qr_image_url}"
            ),
        )
        logger.info(
            "QR + visit code email sent to brand %s for ad %s (code: %s)",
            brand_user.email,
            ad.pk,
            visit_code,
        )
    except Exception:
        logger.exception("Failed to email QR code to brand %s", brand_user.email)
