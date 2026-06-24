from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache
from .models import StepCampaignModel, StepSessionModel, PointTransaction


@receiver(post_save, sender=StepCampaignModel)
@receiver(post_delete, sender=StepCampaignModel)
def clear_step_campaign_cache(sender, **kwargs):
    cache.delete_many(["all_step_campaigns", "campaigns_with_participants"])


@receiver(post_save, sender=StepSessionModel)
@receiver(post_delete, sender=StepSessionModel)
def clear_campaign_participants_cache(sender, **kwargs):
    cache.delete("campaigns_with_participants")


@receiver(post_save, sender=PointTransaction)
def clear_leaderboard_cache(sender, **kwargs):
    cache.delete("points_leaderboard_top100")
