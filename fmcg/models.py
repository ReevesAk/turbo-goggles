from django.db import models
from django.core.validators import MinValueValidator

from basemodel import BaseModel
from accounts.models import User


PRODUCT_CATEGORY = (
    ("Sugar", "Sugar"),
    ("Oil", "Oil"),
    ("Rice", "Rice"),
    ("Pasta", "Pasta"),
    ("Yeast", "Yeast"),
    ("Flour", "Flour"),
    ("Magaraine", "Magarine")
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


# Create your models here.
class Product(BaseModel):
    image_url = models.CharField(max_length=150, null=True)
    name = models.CharField(max_length=150, null=True)
    description = models.TextField(null=True)
    category = models.CharField(choices=PRODUCT_CATEGORY, max_length=100, null=True)
    company = models.CharField(choices=COMPANY, max_length=100, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)], null=True)
    is_available = models.BooleanField(null=True)


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
