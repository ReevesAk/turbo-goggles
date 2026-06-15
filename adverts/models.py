from datetime import timedelta

from django.db import models
from django.utils import timezone

from accounts.models import User

DEMOGRAPHY = (
    ("18 - 25", "18 - 25"),
    ("26 - 35", "26 - 35"),
    ("36 - 45", "36 - 45"),
    ("46+", "46+"),
)

TYPE_OF_BUSUINESS = (
    ("Online", "Online"),
    ("Physical", "Physical"),
    ("Hybrid", "Hybrid"),
)

GENDER = (
    ("Male", "Male"),
    ("Female", "Female"),
    ("All", "All"),
)

INDUSTRY_CHOICES = (
    ("Technology", "Technology"),
    ("Fashion & Beauty", "Fashion & Beauty"),
    ("Food & Drinks", "Food & Drinks"),
    ("Health & Fitness", "Health & Fitness"),
    ("Travels", "Travels"),
    ("Education", "Education"),
    ("Entertainment", "Entertainment"),
    ("Home Decor", "Home Decor"),
    ("Sports", "Sports"),
    ("Business & Finance", "Business & Finance"),
    ("Retail & General Trade", "Retail & General Trade"),
    ("Charities & Membership", "Charities & Membership"),
)

BRAND_OBJECTIVE = (
    ("Brand Awareness", "Brand Awareness"),
    ("Generate Leads", "Generate Leads"),
    ("Drive Sales", "Drive Sales"),
    ("Promote Awareness(Engagement)", "Promote Awareness(Engagement)"),
)

LOCATION_TYPE_CHOICES = (
    ("nationwide", "Nationwide"),
    ("states", "States"),
    ("cities", "Cities"),
)

TASK_TYPE_CHOICES = (
    ("watch_video", "Watch Video"),
    ("social_engage", "Social Engage"),
    ("website_visit", "Website Visit"),
    ("store_visit", "Store Visit"),
    ("survey", "Survey"),
    ("app_download", "App Download"),
)


class CreateAd(models.Model):
    user = models.ForeignKey(
        to=User, on_delete=models.CASCADE, related_name="create_ad"
    )
    business_or_brand_name = models.CharField(max_length=255, null=True)
    type_of_business = models.CharField(
        choices=TYPE_OF_BUSUINESS, max_length=155, null=True
    )
    industry = models.CharField(choices=INDUSTRY_CHOICES, max_length=255, null=True)
    brand_objective = models.CharField(
        choices=BRAND_OBJECTIVE, max_length=255, null=True
    )
    campaign_name = models.CharField(max_length=150, null=True)
    expiry_date = models.DateTimeField(null=True, blank=True)
    gender = models.CharField(choices=GENDER, max_length=20, null=True)
    demography = models.CharField(
        choices=DEMOGRAPHY, max_length=150, blank=True, null=True
    )
    engagement_type = models.CharField(max_length=150, blank=True, null=True)
    daily_allocation = models.CharField(max_length=150, blank=True, null=True)

    website = models.CharField(max_length=150, blank=True, null=True)
    brand_socials = models.JSONField(default=list, blank=True)
    type_of_brand = models.CharField(max_length=100, null=True, blank=True)
    campaign_duration = models.CharField(max_length=155, null=True, blank=True)
    amount = models.CharField(max_length=155, null=True, blank=True)
    is_active = models.BooleanField(default=False, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Task type fields
    task_type = models.CharField(
        choices=TASK_TYPE_CHOICES, max_length=30, null=True, blank=True
    )
    task_name = models.CharField(max_length=255, null=True, blank=True)
    task_description = models.TextField(null=True, blank=True)
    task_details = models.JSONField(default=dict, blank=True)
    reward_points = models.PositiveIntegerField(default=0, null=True, blank=True)
    slot_cap = models.PositiveIntegerField(null=True, blank=True)
    slots_filled = models.PositiveIntegerField(default=0)

    # Targeting
    location_type = models.CharField(
        choices=LOCATION_TYPE_CHOICES, max_length=20, null=True, blank=True
    )
    countries = models.JSONField(default=list, blank=True)
    auto_boost = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if self.campaign_duration and not self.expiry_date:
            self.expiry_date = timezone.now() + timedelta(
                days=int(self.campaign_duration)
            )
        super().save(*args, **kwargs)


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
