from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache
from accounts.models import TxModel
from .financial_tasks import record_financial_task_progress
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


@receiver(post_save, sender=TxModel)
def track_financial_task_progress(sender, instance, created, **kwargs):
    """Drives financial_task/count_based challenge progress (e.g. "transfer
    ≥₦100, 5 times" or "buy airtime 3 times") off real successful
    transactions, tagged via is_task/task_id on the TxModel row — see
    gamification/financial_tasks.py. Source-agnostic: fires for a TxModel
    row from any app (banking transfers, vas airtime/data/bills, ...) as
    long as is_task/task_id/status="SUCCESS" are set on it.

    Deliberately does NOT gate on `created` - banking/transfers.py creates a
    row PENDING then updates it to SUCCESS (created=False at that point),
    but vas/views.py's update_or_create() reaches SUCCESS in the same
    create step (created=True). `status == "SUCCESS"` alone already
    correctly skips a fresh PENDING row either way, so the created check
    only ever made unrelated rows harder to reach.

    task_progress_recorded is the idempotency guard: many code paths across
    banking/ and vas/ set a TxModel to SUCCESS, and this must fire exactly
    once per row no matter which one did it or whether the row gets saved
    again afterwards."""
    if (
        not instance.is_task
        or not instance.task_id
        or instance.status != "SUCCESS"
        or instance.task_progress_recorded
    ):
        return

    record_financial_task_progress(
        user=instance.user, task_id=instance.task_id, amount=instance.amount
    )
    # .update() rather than instance.save() - avoids re-triggering this same
    # post_save signal. Also set on the in-memory instance itself - .update()
    # alone wouldn't be visible if this same Python object gets saved again
    # later without being re-fetched from the DB first.
    instance.task_progress_recorded = True
    TxModel.objects.filter(pk=instance.pk).update(task_progress_recorded=True)
