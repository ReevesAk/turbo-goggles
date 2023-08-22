from django.db import models
from django.utils.translation import gettext_lazy as _

from commons import upload_to

ADS_TYPES = (
    ("PPC", "PPC"),
    ("Signups", "Signups"),
    ("Website Traffic", "Website Traffic"),
    ("Views(Video Marketing)", "Views(Video Marketing)"),
    ("Followers", "Followers"),
    ("SEO", "SEO"),
    ("Social Media", "Social Media"),
    ("App Downloads", "App Downloads")
)

BRAND_TYPE = (
    ("Individual", "Individual"),
    ("Company", "Company"),
    ("Organisation", "Organisation")
)


# Create your models here.
class BrandAdvertRegistration(models.Model):
    facebook = models.CharField(max_length=150, null=True)
    twitter = models.CharField(max_length=150, null=True)
    youtube = models.CharField(max_length=150, null=True)
    instagram = models.CharField(max_length=150, null=True)
    website = models.CharField(max_length=150, null=True)
    brand_user_type = models.CharField(choices=BRAND_TYPE, max_length=100, null=True)
    ads_type = models.CharField(choices=ADS_TYPES, max_length=100)
    trade = models.CharField(max_length=155, null=True)
    brand_logo = models.FileField(upload_to=upload_to)
    brand_name = models.CharField(max_length=150, null=True)
    brand_description = models.CharField(max_length=150, null=True)
    country = models.CharField(max_length=150, null=True)
    state = models.CharField(max_length=150, null=True)
    city = models.CharField(max_length=150, null=True)
    email = models.EmailField(_("email address"), unique=True, null=True)
    address = models.CharField(max_length=150, null=True)
    phone_number = models.CharField(max_length=155, null=True)

    class Meta:
        verbose_name = 'Brand Advert Resgistration'
        verbose_name_plural = 'Brand Advert Resgistration'

    def __str__(self):
        return self.service_name
        