from django.db import models

from accounts.models import User

ONLINE_PRESENCE = (
    ("Yes", "Yes"),
    ("No", "No")
)

TARGET_MARKET = (
    ("16-36 years", "16-36 years"),
    ("36 years and above", "36 years and above")
)

METRIC_TO_INCREASE = (
    ("Brand Awareness", "Brand Awareness"),
    ("Promore Awareness", "Promore Awareness"),
    ("Drive Sales", "Drive Sales"),
    ("Generate leads", "Generate leads")
)

class BrandSurvey(models.Model):
    user = models.OneToOneField(to=User, on_delete=models.CASCADE, related_name="brand_survey")
    online_presence = models.CharField(choices=ONLINE_PRESENCE, max_length=20, null=True)
    online_preferences = models.CharField(max_length=150, null=True)
    metric_to_increase = models.CharField()
    demography = models.CharField(choices=TARGET_MARKET, max_length=150, null=True)
    website = models.CharField(max_length=150, blank=True, null=True)


class BrandSurveyLocation(models.Model):
    brand = models.ManyToOneRel(to=BrandSurvey, on_delete=models.CASCADE, related_name="brand_location")
    state = models.CharField(max_length=150, blank=True, null=True)
    city = models.CharField(max_length=150, blank=True, null=True)

    def __str__(self) -> str:
        return f"{self.state}, {self.city}" if self.state and self.city else "Unknown Location"