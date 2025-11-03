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
