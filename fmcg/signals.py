from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache
from .models import Product, CartItem


@receiver(post_save, sender=Product)
@receiver(post_delete, sender=Product)
def clear_product_cache(sender, instance, **kwargs):
    cache.delete(f"product__id:{instance.id}")


@receiver(post_save, sender=CartItem)
@receiver(post_delete, sender=CartItem)
def clear_cart_cache(sender, instance, **kwargs):
    cart_id = instance.user_id or instance.guest_id
    if cart_id:
        cache.delete(f"user_products:{cart_id}")
