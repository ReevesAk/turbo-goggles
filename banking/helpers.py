import requests
from io import BytesIO
from PIL import Image
import base64


from django.contrib.auth.hashers import check_password

from .models import WalletModel

# Third party imports.
from rest_framework.response import Response
from rest_framework import status


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

    # fetch image from URL
    response = requests.get(url)
    response.raise_for_status()

    # open the image
    img = Image.open(BytesIO(response.content))

    # convert all images to RGB (PNG, WebP, HEIC, etc)
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    # resize/compress
    img.thumbnail(max_size)

    # save to memory buffer
    buffer = BytesIO()
    img.save(buffer, format="JPEG", quality=quality)
    buffer.seek(0)

    # encode to base64
    return base64.b64encode(buffer.read()).decode("utf-8")
