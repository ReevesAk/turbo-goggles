from decouple import config

from django.db import models
from django.utils import timezone

from cloudinary.models import CloudinaryField

from accounts.models import User
from .choices import *


# Create your models here.
class BrandAdvert(models.Model):
    facebook = models.CharField(max_length=150, null=True)
    twitter = models.CharField(max_length=150, null=True)
    youtube = models.CharField(max_length=150, null=True)
    instagram = models.CharField(max_length=150, null=True)
    website = models.CharField(max_length=150, null=True)
    brand_user_type = models.CharField(
        choices=BRAND_TYPE, max_length=100, null=True
    )
    ads_type = models.CharField(choices=ADS_TYPES, max_length=100)
    trade = models.CharField(max_length=155, null=True)
    brand_name = models.CharField(max_length=150, null=True)
    brand_description = models.CharField(max_length=150, null=True)
    country = models.CharField(max_length=150, null=True)
    state = models.CharField(max_length=150, null=True)
    city = models.CharField(max_length=150, null=True)
    email = models.CharField(max_length=80, unique=True, null=True)
    address = models.CharField(max_length=150, null=True)
    phone_number = models.CharField(max_length=155, null=True)

    class Meta:
        verbose_name = 'Brand Advert Resgistration'
        verbose_name_plural = 'Brand Advert Resgistration'

    def __str__(self):
        return self.brand_name

class BrandAdlogo(models.Model):
    """Model for brand avderts logo uploads."""

    user = models.ForeignKey(
        BrandAdvert, on_delete=models.CASCADE
    )
    logo = CloudinaryField(null=True)
    timestamp = models.DateTimeField(default=timezone.now)

    @property
    def logo_url(self):
        cloud_name = config('CLOUDINARY_CLOUD_NAME')
        return (
            f"https://res.cloudinary.com/{cloud_name}/{self.logo}"
        )
    

class BrandAdSurvey(models.Model):
    user = models.ForeignKey(BrandAdvert, on_delete=models.CASCADE)
    preference = models.CharField(choices=PREFERENCES, null=True)
    age_bracket = models.CharField(
        choices=AGE_BRACKET, null=True
    )
    hobbies = models.CharField(choices=HOBBIES, null=True)
    phone_use = models.CharField(choices=MOBILE_PHONE_USE, null=True)
    music_type = models.CharField(choices=MUSIC_CHOICE, null=True)
    social_event = models.CharField(choices=SOCIAL_EVENT, null=True)

    
class BrandAdService(models.Model):
    user = models.ForeignKey(BrandAdvert, on_delete=models.CASCADE)
    service_name = models.CharField(max_length=155, null=True)
    price_of_service = models.FloatField()
    duration_of_service = models.DurationField(null=True)
    service_desc = models.TextField()

    def __str__(self):
        return self.service_name
        

class BookAnAd(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    booking = models.CharField(choices=BOOKING, default="confirm", max_length=155, null=True)

