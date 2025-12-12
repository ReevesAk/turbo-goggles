from django.db import models


class Applications(models.Model):
    first_name = models.CharField(max_length=255, null=True)
    last_name = models.CharField(max_length=255, null=True)
    email = models.EmailField(max_length=255, null=True)
    gender = models.CharField(max_length=10, null=True)
    phone_number = models.CharField(max_length=15, null=True)
    state = models.CharField(max_length=100, null=True)
    lga = models.CharField(max_length=100, null=True)
    address = models.CharField(max_length=255, null=True)
    cv = models.FileField(max_length=255, null=True)
