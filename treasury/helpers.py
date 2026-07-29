from django.contrib.auth.hashers import check_password
from django.utils import timezone
from datetime import timedelta

from rest_framework.response import Response
from rest_framework import status


class Pin:
    @staticmethod
    def verify(user, pin, hashed_pin):
        from .models import TreasuryAccount

        try:
            account = TreasuryAccount.objects.get(user=user)
        except TreasuryAccount.DoesNotExist:
            return Response(
                data={"message": "Treasury account not found"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if account.pin_locked_until and account.pin_locked_until > timezone.now():
            return Response(
                data={"message": "PIN entry locked. Try again later."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if not hashed_pin:
            return False

        is_correct = check_password(pin, hashed_pin)

        if is_correct:
            account.pin_attempts = 0
            account.pin_locked_until = None
            account.save(update_fields=["pin_attempts", "pin_locked_until"])
            return True
        else:
            account.pin_attempts = (account.pin_attempts or 0) + 1
            if account.pin_attempts >= 4:
                account.pin_locked_until = timezone.now() + timedelta(minutes=30)
                account.save(update_fields=["pin_attempts", "pin_locked_until"])
                return Response(
                    data={
                        "message": "Too many wrong PIN attempts. Locked for 30 minutes."
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
            else:
                account.save(update_fields=["pin_attempts"])
                return False
