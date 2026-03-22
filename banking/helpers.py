import requests
from io import BytesIO
from PIL import Image
import base64

from django.contrib.auth.hashers import check_password
from django.utils import timezone

from .models import WalletModel

# Third party imports.
from rest_framework.response import Response
from rest_framework import status

from commons import Biometrics
from security import encrypt


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
    app_name="Picadailys",
):
    masked_account = f"******{str(account_number)[-4:]}"

    extra_line = ""
    if transaction_type.upper() == "DEBIT":
        extra_line = "If not you, contact support immediately."

    message = f"""
    {transaction_type.upper()} ALERT

    Acct: {masked_account}
    Amt: NGN{amount:.2f}
    Desc: {description}
    Date: {timezone.now().strftime('%d-%b-%Y %H:%M')}
    Bal: NGN{balance:.2f}
    Ref: {reference}

    {extra_line}
    {app_name}
    """
    return message.strip()
