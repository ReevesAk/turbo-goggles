from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache
from .models import CreateAd


@receiver(post_save, sender=CreateAd)
@receiver(post_delete, sender=CreateAd)
def clear_ad_caches(sender, instance, **kwargs):
    user_id = instance.user_id
    cache.delete_many(
        [
            "brandad_users_list",
            f"user_ads:{user_id}",
            f"Ad_Details:{user_id}",
            f"singleAd_Details:{instance.id}",
            f"ad_stats_{user_id}",
        ]
    )
