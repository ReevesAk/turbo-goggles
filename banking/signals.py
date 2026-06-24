from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache
from .models import WalletModel


@receiver(post_save, sender=WalletModel)
@receiver(post_delete, sender=WalletModel)
def clear_wallet_list_cache(sender, **kwargs):
    cache.delete_many(["wallet_users_list", "all_members"])
