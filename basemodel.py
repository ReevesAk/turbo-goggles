from django.db import models
import uuid

PAYMENT_OPTIONS = (
    ("WALLET", "WALLET"),
    ("CARD", "CARD"),
)

class BaseModel(models.Model):
    """Define abstract base model."""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted = models.BooleanField(default=False)

    class Meta:
        abstract = True


class VasBaseModel(models.Model):
    """Define abstract base model for payments."""

    payment_option = models.CharField(choices=PAYMENT_OPTIONS, max_length=100, null=True)
    created_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
