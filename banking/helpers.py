import requests
import csv
from io import BytesIO, StringIO
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from PIL import Image
import base64
from decouple import config

from django.contrib.auth.hashers import check_password
from django.utils import timezone

from .models import WalletModel

# Third party imports.
from rest_framework.response import Response
from rest_framework import status

from commons import Biometrics
from security import encrypt

yournotify_api_key = config("YOURNOTIFY_API_KEY")


class Pin:
    @staticmethod
    def verify(user, pin, hashed_pin):
        try:
            wallet = WalletModel.objects.get(user=user)
        except WalletModel.DoesNotExist:
            return Response(
                data={"message": "Invalid wallet ID"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if wallet:
            is_pin_correct = check_password(pin, hashed_pin)

            if is_pin_correct:
                return True
            else:
                return False


def cloudinary_to_base64(url, quality=40, max_size=(700, 700)):
    """
    Downloads an image from Cloudinary, compresses it, and returns base64 string.
    """

    response = requests.get(url)
    response.raise_for_status()

    img = Image.open(BytesIO(response.content))

    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    img.thumbnail(max_size)

    # save to memory buffer
    buffer = BytesIO()
    img.save(buffer, format="JPEG", quality=quality)
    buffer.seek(0)

    # encode to base64
    return base64.b64encode(buffer.read()).decode("utf-8")


def verify_wallet_auth(user, payment_option, pin=None, use_biometrics=False):
    if payment_option != "WALLET":
        return True, None

    account = WalletModel.objects.filter(user=user).first()

    if use_biometrics:
        verified = Biometrics.authenticate(user.phone_number)
        if not verified:
            return False, Response(
                encrypt({"status": "fail", "error": "Biometric verification failed"}),
                status=status.HTTP_403_FORBIDDEN,
            )

    elif account and account.pin:
        verified = Pin.verify(user=user, pin=pin, hashed_pin=account.pin)
        if not verified:
            return False, Response(
                encrypt({"status": "fail", "error": "Invalid PIN"}),
                status=status.HTTP_403_FORBIDDEN,
            )

    else:
        return False, Response(
            encrypt({"status": "fail", "error": "Account or PIN not found"}),
            status=status.HTTP_404_NOT_FOUND,
        )

    return True, None


def generate_transaction_sms(
    transaction_type,
    account_number,
    amount,
    balance,
    description,
    reference,
):
    masked_account = f"******{str(account_number)[-4:]}"
    support_phone = "02012271894"

    lines = [
        f"{transaction_type.upper()} ALERT",
        f"Acct: {masked_account}",
        f"Amt: NGN{amount:.2f}",
        f"Desc: {description}",
        f"Date: {timezone.now().strftime('%d-%b-%Y %H:%M')}",
        f"Bal: NGN{balance:.2f}",
    ]
    if transaction_type.upper() == "DEBIT":
        msg = f"If not you, contact support immediately. Call {support_phone}."
        lines.append(msg)
    return "\n".join(lines)


class ExportStatement:

    @staticmethod
    def to_csv(transactions):
        buffer = StringIO()
        writer = csv.writer(buffer)

        writer.writerow(
            ["Date", "Reference", "Type", "Amount", "Description", "Status"]
        )

        for tx in transactions:
            writer.writerow(
                [
                    tx.date.strftime("%Y-%m-%d %H:%M"),
                    tx.tx_reference,
                    tx.tx_type,
                    tx.amount,
                    tx.description,
                    tx.status,
                ]
            )

        return buffer.getvalue()

    @staticmethod
    def to_pdf(transactions):
        buffer = BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=letter)

        y = 750
        pdf.drawString(50, y, "Picadailys Account Statement")
        y -= 40

        for tx in transactions:
            line = f"{tx.date.strftime('%Y-%m-%d')} | {tx.tx_reference} | {tx.tx_type} | {tx.amount}"
            pdf.drawString(50, y, line)
            y -= 20

            if y < 50:  # new page if space finishes
                pdf.showPage()
                y = 750

        pdf.save()

        return buffer.getvalue()


def get_asset_id(file):
    url = "https://api.yournotify.com/assets"

    headers = {"Authorization": yournotify_api_key}

    try:
        with open(file, "rb") as pdf_file:
            files = {"file": ("statement.pdf", pdf_file, "application/pdf")}

            response = requests.post(url, headers=headers, files=files)

        if response.status_code == 200:
            data = response.json()

            if data.get("status") == "success":
                return {"success": True, "media_id": data["data"][0]["id"]}

            return {"success": False, "message": data.get("message", "Upload failed")}

        return {
            "success": False,
            "message": f"HTTP Error: {response.status_code}",
            "response": response.text,
        }

    except Exception as e:
        return {"success": False, "message": str(e)}
