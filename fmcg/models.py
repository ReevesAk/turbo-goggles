from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator

from basemodel import BaseModel
from accounts.models import User


PRODUCT_CATEGORY = (
    ("Sugar", "Sugar"),
    ("Vegetable Oil", "Vegetable Oil"),
    ("Rice", "Rice"),
    ("Pasta", "Pasta"),
    ("Yeast", "Yeast"),
    ("Flours", "Flours"),
    ("Magaraine", "Magarine"),
    ("Semolina", "Semolina")
)

COMPANY = (
    ("BUA", "BUA"),
    ("Dangote", "Dangote"),
    ("Golden Penny", "Golden Penny"),
    ("PZ", "PZ"),
    ("Duffel", "Duffel"),
    ("Olam", "Olam"),
    ("Flour Mills of Nigeria", "Flour Mills of Nigeria")
)

BILLING_ADDRESS = (
    ("Store Pick-Up", "Store Pick-Up"),
    ("Delivery", "Delivery")
)


class PickupAdress(models.Model):
    name = models.CharField(max_length=200, null=True)
    state = models.CharField(max_length=50, null=True)


class Product(BaseModel):
    category = models.CharField(choices=PRODUCT_CATEGORY, max_length=100, null=True)
    image_url = models.CharField(max_length=150, null=True)
    name_and_size = models.CharField(max_length=150, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    expiry_date = models.DateField(null=True, blank=True)
    description = models.TextField(null=True)
    macro_nutrients = models.TextField(null=True)
    micro_nutrients = models.TextField(null=True)
    density = models.CharField(max_length=50, null=True)
    calories = models.CharField(max_length=200, null=True)
    moisture = models.CharField(max_length=200, null=True)
    texture = models.CharField(max_length=150, null=True)
    storage = models.CharField(max_length=200, null=True)
    additional_images_urls = models.CharField(max_length=255, null=True)
    subtitle = models.CharField(max_length=200, null=True, blank=True)
    input_style = models.CharField(max_length=200, null=True, blank=True)
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)], null=True)
    is_available = models.BooleanField(null=True)

    # def clean(self):
    #     super().clean()
    #     if self.expiry_date < timezone.now().date():
    #         raise ValidationError("Expiry date cannot be in the past.")


class Cart(models.Model):
    cart_id = models.CharField(max_length=150, blank=True)
    date_added = models.DateField(auto_now_add=True, null=True)

    def __str__(self):
        return self.cart_id


class CartItem(BaseModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="product_carts")
    product = models.ForeignKey('Product', on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)], null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)

    def get_total_price(self):
        return self.quantity * self.price


class FmcgOrder(BaseModel):
    class Status(models.TextChoices):
        PENDING = 'Pending', _('Pending')
        COMPLETED = 'Completed', _('Completed')
        CANCELED = 'Canceled', _('Canceled')
        FAILED = 'Failed', _('Failed')

    user = models.ForeignKey(to=User, on_delete=models.CASCADE, null=True)
    product = models.CharField(max_length=150, null=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    billing_address = models.CharField(max_length=150, choices=BILLING_ADDRESS, null=True)
    available_addresses = models.ForeignKey(
        to=PickupAdress, on_delete=models.CASCADE,
        max_length=250, null=True, blank=True
    )
    delivery_address = models.CharField(max_length=200, null=True, blank=True)
    delivery_fee = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    tracking_id = models.CharField(max_length=50, null=True)
    total_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)


class FmcgRating(BaseModel):
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="fmcg_rating"
    )
    rating = models.CharField(null=True, blank=True)
    review = models.TextField(null=True, blank=True)
    slug = models.SlugField(default="", max_length=155, null=False)
