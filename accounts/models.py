from django.db import models
from django.contrib.auth.models import (
    AbstractBaseUser, BaseUserManager, PermissionsMixin)

# Third party imports.
from rest_framework_simplejwt.tokens import RefreshToken


# UserManager handles the creation of superuser as well as manage creation of user accounts.
class UserManager(BaseUserManager):

    def create_user(self, first_name, last_name, phone_number, email, password=None, password2=None):
        if phone_number is None:
            raise TypeError('Users should have a phone_number')
        if email is None:
            raise TypeError('Users should have a Email')

        user = self.model(
            phone_number=phone_number, 
            email=self.normalize_email(email),
            first_name =first_name,
            last_name = last_name
            )
        user.set_password(password)
        user.save()
        return user

    def create_superuser(self, first_name, last_name, phone_number, email, password=None):
        if password is None:
            raise TypeError('Password should not be none')

        user = self.create_user(first_name, last_name, phone_number, email, password)
        user.is_superuser = True
        user.is_staff = True
        user.save()
        return user


# User describes the database model for each user.
class User(AbstractBaseUser, PermissionsMixin):
    first_name = models.CharField(max_length=150, blank=False)
    last_name = models.CharField(max_length=150, blank=False)
    phone_number = models.TextField(max_length=20, blank=False)
    email = models.EmailField(max_length=255, unique=True, db_index=True)
    is_verified = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['phone_number', 'first_name', 'last_name']

    objects = UserManager()

    def __str__(self):
        return self.email

    def tokens(self):
        refresh_token = RefreshToken.for_user(self)
        return {
            'refresh': str(refresh_token),
            'access': str(refresh_token.access_token)
        }
