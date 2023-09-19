from django.db import models
from django.contrib.auth.models import (
    AbstractBaseUser, PermissionsMixin)
from django.utils.translation import gettext_lazy as _
from django.utils import timezone


from .user_manager import CustomUserManager

USER_CATEGORY_CHOICES = (
    ("User", "User"),
    ("Partner", "Partner"),
)

# User describes the database model for each user.
class User(AbstractBaseUser, PermissionsMixin):
    first_name = models.CharField(max_length=255, null=True)
    last_name = models.CharField(max_length=255, null=True)
    password = models.CharField(max_length=255, null=True)
    phone_number = models.TextField(max_length=20, blank=False)
    email = models.CharField(max_length=80, unique=True)
    country = models.CharField(max_length=155, blank=False)
    state = models.CharField(max_length=155, blank=False)
    city = models.CharField(max_length=155, blank=False)
    game_points = models.IntegerField(null=True)

    #Partner detials.
    account_type = models.CharField(choices=USER_CATEGORY_CHOICES, max_length=40, null=True)
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
    

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = CustomUserManager()

    def __str__(self):
        return self.email
    
    def is_member(self):
        if self.game_points == 10:
            return True
