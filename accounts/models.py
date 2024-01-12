from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.utils import timezone


from .user_manager import CustomUserManager

USER_CATEGORY_CHOICES = (
    ("SuperAdmin", "SuperAdmin"),
    ("User", "User"),
    ("Partner", "Partner"),
    ("Member", "Member"),
    ("BrandAd", "BrandAd"),
    ("TaskAdmin", "TaskAdmin"),
    ("AdAdmin", "AdAdmin"),
    ("MembersAdmin", "MembersAdmin"),
    ("UserAdmin", "UserAdmin"),
    ("PartnersAdmin", "PartnersAdmin"),
    ("ContentAdmin", "ContentAdmin"),
    ("IntegrationAdmin", "IntegrationAdmin"),
    ("WalletAdmin", "WalletAdmin"),
)

BRAND_TYPE = (
    ("Individual", "Individual"),
    ("Company", "Company"),
    ("Business", "Business"),
)


# User describes the database model for each user.
class User(AbstractBaseUser, PermissionsMixin):
    first_name = models.CharField(max_length=255, null=True)
    last_name = models.CharField(max_length=255, null=True)
    password = models.CharField(max_length=255, null=True)
    phone_number = models.CharField(max_length=20, unique=True)
    email = models.CharField(max_length=80, unique=True)
    country = models.CharField(max_length=155, blank=False)
    state = models.CharField(max_length=155, blank=False)
    city = models.CharField(max_length=155, blank=False)
    points = models.FloatField(null=True)
    profile_img_url = models.CharField(max_length=255, null=True)
    is_bvn_verified = models.BooleanField(default=False)
    is_upgraded = models.BooleanField(default=False)

    # Brand details.
    address = models.CharField(max_length=155, blank=False, null=True)
    whoareyou = models.CharField(choices=BRAND_TYPE, max_length=150, null=True)
    name = models.CharField(max_length=155, blank=False, null=True)
    brand_type = models.CharField(max_length=155, blank=False, null=True)

    # Brand onboarding.
    brand_name = models.CharField(max_length=255, null=True)
    description = models.CharField(max_length=150, null=True)
    services = models.CharField(max_length=255, null=True)
    website = models.CharField(max_length=150, null=True)
    facebook = models.CharField(max_length=150, null=True)
    twitter = models.CharField(max_length=150, null=True)
    instagram = models.CharField(max_length=150, null=True)
    telegram = models.CharField(max_length=150, null=True)

    # Partner details.
    account_type = models.CharField(
        choices=USER_CATEGORY_CHOICES, max_length=40, null=True
    )
    business_name = models.CharField(max_length=500, null=True)
    website = models.CharField(max_length=255, null=True)
    business_category = models.CharField(max_length=255, null=True)
    is_verified = models.BooleanField(default=False)
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_member = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = "phone_number"
    REQUIRED_FIELDS = []

    objects = CustomUserManager()

    def __str__(self):
        return self.phone_number


class DeviceId(models.Model):
    user = models.ForeignKey(to=User, on_delete=models.CASCADE)
    device_id = models.CharField(max_length=250, null=True)
    created_at = models.DateTimeField(auto_now_add=True)


class OTP(models.Model):
    otp = models.CharField(max_length=6, null=True)
    user_id = models.IntegerField()
    expires_at = models.DateTimeField(auto_now_add=True)
