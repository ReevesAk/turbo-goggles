from datetime import timedelta
from django.utils import timezone
import random
import string

from django.core.exceptions import ObjectDoesNotExist

from .models import OTP


class OTPManager:
    def generate_token(self, num: int = 4) -> str:
        """Generate random token."""
        characters = string.digits
        return "".join(random.choice(characters) for _ in range(num))

    def create_otp(self, user_id: str, expires=5):
        try:
            existing_otp = OTP.objects.get(user_id=user_id)
            existing_otp.delete()
        except ObjectDoesNotExist:
            pass

        otp = self.generate_token()

        expires_at = timezone.now() + timedelta(minutes=expires)

        # Create and save the OTP instance with the expiration time
        otp_instance = OTP(otp=otp, user_id=user_id, expires_at=expires_at)
        otp_instance.save()

        return otp

    def validate_user_otp(self, otp: str):
        """Check that otp is valid."""

        try:
            otp_obj = OTP.objects.get(otp=otp)
            if timezone.now() >= otp_obj.expires_at:
                user_id = otp_obj.user_id
                otp_obj.delete()
                print(f"Valid OTP: {otp}, User ID: {user_id}")
                return user_id
            else:
                print(f"Expired OTP: {otp}")
        except OTP.DoesNotExist:
            print(f"Invalid OTP: {otp}")
            return None

    def delete_user_otp(self, otp: str):
        """Delete user OTP."""
        if OTP.objects.filter(otp=otp).exists():
            OTP.objects.get(otp=otp).delete()


otp_manager = OTPManager()
