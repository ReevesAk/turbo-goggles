from django.db import models
import uuid


class JobModel(models.Model):
    title = models.CharField(max_length=255)
    location = models.CharField(max_length=255)
    company = models.CharField(max_length=255, null=True, blank=True)
    job_type = models.CharField(max_length=100, null=True, blank=True)
    job_summary = models.TextField(null=True, blank=True)

    key_responsibilities = models.JSONField(default=list, blank=True)
    requirements = models.JSONField(default=list, blank=True)

    salary = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class Applications(models.Model):
    job = models.ForeignKey(
        JobModel,
        on_delete=models.CASCADE,
        related_name="applications",
        null=True,
    )
    job_title = models.CharField(max_length=255, null=True)
    first_name = models.CharField(max_length=255, null=True)
    last_name = models.CharField(max_length=255, null=True)
    email = models.EmailField(max_length=255, null=True)
    gender = models.CharField(max_length=10, null=True)
    phone_number = models.CharField(max_length=15, null=True)
    state = models.CharField(max_length=100, null=True)
    lga = models.CharField(max_length=100, null=True)
    address = models.CharField(max_length=255, null=True)
    cv = models.FileField(max_length=255, null=True)


class NewsletterSubscribers(models.Model):
    email = models.EmailField(max_length=255, unique=True)
    token = models.UUIDField(
        default=uuid.uuid4, editable=False, unique=True, null=True
    )
    subscribed_at = models.DateTimeField(auto_now_add=True)
