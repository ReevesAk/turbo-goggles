from django.db import models

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
    ("Generation Lead", "Generation Lead"),
    ("Drive Sales", "Drive Sales"),
    ("Promotion Awareness(Engagement)", "Promotion Awareness(Engagement)"),
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
    gender = models.CharField(choices=GENDER, max_length=20, null=True)
    demography = models.CharField(
        choices=DEMOGRAPHY, max_length=150, blank=True, null=True
    )
    engagement_type = models.CharField(max_length=150, blank=True, null=True)
    daily_allocation = models.CharField(max_length=150, blank=True, null=True)

    website = models.CharField(max_length=150, blank=True, null=True)
    type = models.CharField(max_length=100, null=True, blank=True)
    campaign_duration = models.CharField(max_length=155, null=True, blank=True)
    amount = models.CharField(max_length=155, null=True, blank=True)
    is_active = models.BooleanField(default=False, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)


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
