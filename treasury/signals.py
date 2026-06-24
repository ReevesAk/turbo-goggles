from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache
from .models import TreasuryAccount


@receiver(post_save, sender=TreasuryAccount)
@receiver(post_delete, sender=TreasuryAccount)
def clear_treasury_account_list_cache(sender, **kwargs):
    cache.delete("treasury_accounts_list")
