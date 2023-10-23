from django.db import models
from django.utils import timezone
from cloudinary.models import CloudinaryField

from accounts.models import User


class ProfileImage(models.Model):
    user = models.ForeignKey(to=User, on_delete=models.CASCADE)
    image = CloudinaryField(null=True)
    timestamp = models.DateTimeField(default=timezone.now)
