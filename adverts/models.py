from django.db import models

from accounts.models import User
from basemodel import PAYMENT_OPTIONS

ONLINE_PRESENCE = (("Yes", "Yes"), ("No", "No"))

TARGET_MARKET = (
    ("16-36 years", "16-36 years"),
    ("36 years and above", "36 years and above"),
)

METRIC_TO_INCREASE = (
    ("Brand Awareness", "Brand Awareness"),
    ("Promore Awareness", "Promore Awareness"),
    ("Drive Sales", "Drive Sales"),
    ("Generate leads", "Generate leads"),
)

AD_CATEGORY = (
    ("On-iste(Images and Video)", "On-iste(Images and Video)"),
    ("On-iste(Images)", "On-iste(Images)"),
    ("On-iste(Video)", "On-iste(Video)"),
    (
        "Self Service/Off-site(Images and Video)",
        "Self Service/Off-site(Images and Video)",
    ),
    ("Self Service/Off-site(Images)", "Self Service/Off-site(Images)"),
    ("Self Service/Off-site(Video)", "Self Service/Off-site(Video)"),
)

AD_TYPE = (
    ("Pay Per Action(PPA)", "Pay Per Action(PPA)"),
    ("Pay Per Click (PPC)", "Pay Per Click (PPC)"),
    ("Pay Per Engagement (PPE)", "Pay Per Engagement (PPE)"),
    ("Pay Per View (PPV)", "Pay Per View (PPV)"),
)


class CreateAd(models.Model):
    user = models.ForeignKey(
        to=User, on_delete=models.CASCADE, related_name="create_ad"
    )
    brand_type = models.CharField(max_length=155, null=True)
    product_type = models.CharField(max_length=200, null=True)
    online_presence = models.CharField(
        choices=ONLINE_PRESENCE, max_length=20, blank=True, null=True
    )
    online_preferences = models.CharField(max_length=150, blank=True, null=True)
    metric_to_increase = models.CharField(max_length=250, blank=True, null=True)
    demography = models.CharField(
        choices=TARGET_MARKET, max_length=150, blank=True, null=True
    )
    website = models.CharField(max_length=150, blank=True, null=True)
    type = models.CharField(max_length=100, null=True, blank=True)
    category = models.CharField(
        choices=AD_CATEGORY, max_length=155, null=True, blank=True
    )
    address = models.CharField(max_length=155, null=True, blank=True)
    description = models.CharField(max_length=155, null=True, blank=True)
    duration = models.CharField(max_length=155, null=True, blank=True)
    is_approved = models.BooleanField(default=False, null=True, blank=True)
    is_rejected = models.BooleanField(default=False, null=True, blank=True)


class AdMedia(models.Model):
    brand = models.ForeignKey(
        to=CreateAd, on_delete=models.CASCADE, related_name="ad_media"
    )
    images = models.CharField(max_length=150, blank=True, null=True)
    videos = models.CharField(max_length=150, blank=True, null=True)

    def __str__(self) -> str:
        return (
            f"{self.images}, {self.videos}"
            if self.images and self.videos
            else "Unknown Media"
        )


class AdLocation(models.Model):
    brand = models.ForeignKey(
        to=CreateAd, on_delete=models.CASCADE, related_name="brand_location"
    )
    state = models.CharField(max_length=150, blank=True, null=True)
    city = models.CharField(max_length=150, blank=True, null=True)

    def __str__(self) -> str:
        return (
            f"{self.state}, {self.city}"
            if self.state and self.city
            else "Unknown Location"
        )


class AdBudget(models.Model):
    user = models.OneToOneField(
        to=User, on_delete=models.CASCADE, related_name="promote_ad"
    )
    payment_option = models.CharField(
        choices=PAYMENT_OPTIONS, max_length=100, null=True
    )
    is_active_ad = models.BooleanField(default=False)
    is_completed = models.BooleanField(default=False)
    is_ongoing = models.BooleanField(default=False)
    has_made_request = models.BooleanField(default=False)
    ad_type = models.CharField(choices=AD_TYPE, max_length=150)
    category = models.CharField(max_length=150, null=True)
    ad = models.CharField(max_length=100, null=True)
    star = models.CharField(max_length=50, null=True, blank=True)
    price_range = models.CharField(max_length=150, null=True)
