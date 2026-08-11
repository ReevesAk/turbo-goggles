import logging
import random
import string

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from accounts.models import User
from .models import Referral, ReferralTask, UserReferralTaskProgress
from .points import Points

logger = logging.getLogger(__name__)

CODE_RANDOM_LENGTH = 6


class Referrals:
    @staticmethod
    def generate_code(user) -> str:
        """
        Loop-until-unique referral code generator for accounts.User. Independent
        equivalent of waitlist's WaitlistModel.generate_referral_code — not
        imported/coupled to that app.
        """
        prefix = (user.first_name or "USER").upper().replace(" ", "")[:5]
        while True:
            suffix = "".join(
                random.choices(
                    string.ascii_uppercase + string.digits, k=CODE_RANDOM_LENGTH
                )
            )
            code = f"{prefix}{suffix}"
            if not User.objects.filter(referral_code=code).exists():
                return code

    @staticmethod
    def get_active_gate():
        """Returns the currently active walk_to_earn_gate ReferralTask, or None."""
        return (
            ReferralTask.objects.filter(
                mode="walk_to_earn_gate",
                is_active=True,
                is_paused=False,
                is_cancelled=False,
            )
            .order_by("-created_at")
            .first()
        )

    @staticmethod
    def record_referral(referrer, referred, code_used: str):
        """
        Called once per successful registration-with-code. Always creates the
        Referral ledger row. Only advances referrer.referral_count and checks
        gamification-task completion if the referrer passes
        Points.check_credibility — an untrustworthy referrer can't farm
        Walk-to-Earn access via referrals.
        """
        with transaction.atomic():
            credible, reason = Points.check_credibility(referrer)

            referral = Referral.objects.create(
                referrer=referrer,
                referred=referred,
                referral_code_used=code_used,
                counted=credible,
            )

            if not credible:
                logger.info(
                    "Referral recorded but not counted (referrer failed credibility): "
                    "referrer=%s reason=%s",
                    referrer.email,
                    reason,
                )
                return referral

            User.objects.filter(pk=referrer.pk).update(
                referral_count=F("referral_count") + 1
            )
            referrer.refresh_from_db(fields=["referral_count"])
            Referrals._check_gamification_tasks(referrer)

        return referral

    @staticmethod
    def _check_gamification_tasks(referrer):
        active_tasks = ReferralTask.objects.filter(
            mode="gamification",
            is_active=True,
            is_paused=False,
            is_cancelled=False,
            target_referral_count__lte=referrer.referral_count,
        )
        for task in active_tasks:
            (
                progress,
                _,
            ) = UserReferralTaskProgress.objects.select_for_update().get_or_create(
                user=referrer, task=task
            )
            if progress.reward_issued:
                continue

            ok, msg = Points.award(
                user=referrer,
                amount=task.reward_points,
                reason=f"Referral task completed: {task.name}",
                source="referral",
                reference_id=str(task.id),
            )
            if ok:
                progress.completed = True
                progress.completed_at = timezone.now()
                progress.reward_issued = True
                progress.referral_count_at_completion = referrer.referral_count
                progress.save(
                    update_fields=[
                        "completed",
                        "completed_at",
                        "reward_issued",
                        "referral_count_at_completion",
                    ]
                )
            else:
                logger.warning(
                    "Referral task reward blocked for %s: %s", referrer.email, msg
                )
