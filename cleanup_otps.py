from django.core.management.base import BaseCommand
from django.utils import timezone
from accounts.models import OTP


class Command(BaseCommand):
    help = "Clean up expired OTPs"

    def handle(self, *args, **kwargs):
        now = timezone.now()
        expired_otps = OTP.objects.filter(expires_at__lte=now)
        expired_otps.delete()
