from django.db import models


class JobModel(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField()
    location = models.CharField(max_length=255)
    salary = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


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
