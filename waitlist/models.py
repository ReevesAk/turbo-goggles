import string
import random

from django.db import models


# Create your models here.
class WaitlistModel(models.Model):
    """WaitlistModel is the model to persist the record of
    waitlist users and their count
    """

    f_name = models.CharField(max_length=50, null=True)
    l_name = models.CharField(max_length=50, null=True)
    email = models.CharField(max_length=100, unique=True, null=True)
    phone = models.CharField(max_length=50, null=True, blank=True)
    referral_code = models.CharField(max_length=50, null=True)
    referral_count = models.SmallIntegerField(null=True, blank=True)
    is_student = models.BooleanField(default=False, null=True)
    institution = models.CharField(max_length=150, null=True, blank=True)

    @classmethod
    def generate_referral_code(cls, first_name, length=4):
        """
        Generate a unique referral code with first name prefix
        """
        # Clean first name
        prefix = (first_name or "USER").upper().replace(" ", "")[:5]

        while True:
            random_digits = "".join(
                random.choices(string.ascii_uppercase + string.digits, k=4)
            )
            code = f"{prefix}{random_digits}"

            if not cls.objects.filter(referral_code=code).exists():
                return code
