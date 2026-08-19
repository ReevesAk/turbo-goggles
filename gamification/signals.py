from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache
from .models import (
    StepCampaignModel,
    StepSessionModel,
    PointTransaction,
    UserGeneratedContent,
    StreakChallenge,
)


@receiver(post_save, sender=StepCampaignModel)
@receiver(post_delete, sender=StepCampaignModel)
def clear_step_campaign_cache(sender, **kwargs):
    cache.delete_many(["all_step_campaigns", "campaigns_with_participants"])


@receiver(post_save, sender=UserGeneratedContent)
@receiver(post_delete, sender=UserGeneratedContent)
def clear_brand_ads_list_cache(sender, instance, **kwargs):
    # ListAllBrandAds (adverts app) merges CreateAd + UserGeneratedContent +
    # StreakChallenge into one "my ads" list under this same cache key - see
    # adverts/signals.py for the CreateAd side of this invalidation.
    cache.delete(f"user_ads:{instance.user_id}")


@receiver(post_save, sender=StreakChallenge)
@receiver(post_delete, sender=StreakChallenge)
def clear_brand_ads_list_cache_for_inapp_task(sender, instance, **kwargs):
    # StreakChallenge is owned via created_by, not user - see
    # clear_brand_ads_list_cache above.
    if instance.created_by_id:
        cache.delete(f"user_ads:{instance.created_by_id}")


@receiver(post_save, sender=StepSessionModel)
@receiver(post_delete, sender=StepSessionModel)
def clear_campaign_participants_cache(sender, **kwargs):
    cache.delete("campaigns_with_participants")


@receiver(post_save, sender=PointTransaction)
def clear_leaderboard_cache(sender, **kwargs):
    cache.delete("points_leaderboard_top100")
