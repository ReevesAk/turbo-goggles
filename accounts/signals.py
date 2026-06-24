from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache
from .models import AccountType


@receiver(post_save, sender=AccountType)
@receiver(post_delete, sender=AccountType)
def clear_user_role_caches(sender, **kwargs):
    cache.delete_many(
        [
            "all_partner_users",
            "all_members",
            "all_admin_users",
            "admin_users_by_role",
            "brandad_users_list",
        ]
    )
