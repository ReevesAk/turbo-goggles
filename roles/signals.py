from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache
from gamification.models import StepCampaignModel
from banking.models import WalletModel
from treasury.models import TreasuryAccount


@receiver(post_save, sender=StepCampaignModel)
@receiver(post_delete, sender=StepCampaignModel)
def clear_step_campaign_cache(sender, **kwargs):
    """
    Automatically clears the cached list of step campaigns
    whenever a campaign is created, updated, or deleted.
    """
    cache_key = "all_step_campaigns"
    cache.delete(cache_key)


@receiver(post_save, sender=WalletModel)
@receiver(post_delete, sender=WalletModel)
def clear_wallet_list_cache(sender, **kwargs):
    """
    Automatically clears the cached list of wallet users list
    whenever a new entry is created, updated, or deleted.
    """
    cache_key = "wallet_users_list"
    cache.delete(cache_key)


@receiver(post_save, sender=TreasuryAccount)
@receiver(post_delete, sender=TreasuryAccount)
def clear_treasury_account_list_cache(sender, **kwargs):
    """
    Automatically clears the cached list of treasury accounts
    whenever a new entry is created, updated, or deleted.
    """
    cache_key = "treasury_accounts_list"
    cache.delete(cache_key)
