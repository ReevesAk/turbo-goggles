from django.db import models

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

# Create your models here.
class BrandAdvertRegistration(models.Model):
    facebook                = models.CharField(max_length=150, blank=False)
    twitter                 = models.CharField(max_length=150, blank=False)
    youtube                 = models.CharField(max_length=150, blank=False)
    website                 = models.CharField(max_length=150, blank=False)
    ads_type                = models.CharField(choices=ADS_TYPES, max_length=50)
    brand_logo              = models.FileField(upload_to=upload_to)
    brand_name              = models.CharField(max_length=150, blank=False)
    brand_description       = models.CharField(max_length=150, blank=False)
    country                 = models.CharField(max_length=150, blank=False)
    state                   = models.CharField(max_length=150, blank=False)
    city                    = models.CharField(max_length=150, blank=False)
    service_name            = models.CharField(max_length=150, blank=False)
    service_price           = models.CharField(max_length=150, blank=False)
    service_duration        = models.CharField(max_length=150, blank=False)
    service_desctiption     = models.CharField(max_length=150, blank=False)

    class Meta:
        verbose_name = 'Brand Advert Resgistration'
        verbose_name_plural = 'Brand Advert Resgistration'

    def __str__(self):
        return self.service_name
        