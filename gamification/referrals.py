import logging
import random
import string

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from accounts.models import User
from .models import Referral, ReferralTask, UserReferralTaskProgress, UserStreak
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
            Referrals._check_inapp_referral_tasks(referrer)

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

    @staticmethod
    def _check_inapp_referral_tasks(referrer):
        """
        Updates progress for StreakChallenge in-app tasks with
        mission_category="referral_task" (streak_type="financial_task") -
        a cumulative "refer required_count people" target, distinct from
        ReferralTask above (a different model/admin flow - see
        gamification/models.py's ReferralTask docstring and the
        InAppTaskFeedSerializer/StreakChallenge task.type="referral_task"
        mapping in tasks/serializers.py).

        Only touches challenges the user has already joined (has a
        UserStreak row for via JoinStreakChallengeView) - joining is what
        opts a user into a specific challenge's reward, same as
        UserReferralTaskProgress above is scoped to a specific ReferralTask.
        current_count is set to the true referral_count rather than
        incremented, so this is idempotent and can't drift.
        """
        candidates = UserStreak.objects.select_for_update().filter(
            user=referrer,
            completed=False,
            challenge__streak_type="financial_task",
            challenge__mission_category="referral_task",
            challenge__action_type__in=("count_based", "streak"),
            challenge__is_active=True,
            challenge__is_paused=False,
            challenge__is_cancelled=False,
        ).select_related("challenge")

        for user_streak in candidates:
            challenge = user_streak.challenge
            if not challenge.is_ongoing:
                continue

            user_streak.current_count = referrer.referral_count
            user_streak.longest_count = max(
                user_streak.longest_count, user_streak.current_count
            )
            user_streak.last_activity_date = timezone.now().date()

            required_count = challenge.required_count or 0
            if user_streak.current_count < required_count:
                user_streak.save(
                    update_fields=[
                        "current_count",
                        "longest_count",
                        "last_activity_date",
                    ]
                )
                continue

            level_multiplier = Points.get_level_multiplier(
                Points.get_user_tier(referrer.total_points or 0)
            )
            final_points = int(challenge.reward_points * level_multiplier)

            ok, msg = Points.award(
                user=referrer,
                amount=final_points,
                reason=f"Referral task completed: {challenge.name}",
                source="referral",
                reference_id=str(challenge.id),
            )
            if ok:
                user_streak.completed = True
                user_streak.completed_at = timezone.now()
                user_streak.reward_issued = True
                user_streak.save(
                    update_fields=[
                        "current_count",
                        "longest_count",
                        "last_activity_date",
                        "completed",
                        "completed_at",
                        "reward_issued",
                    ]
                )
                try:
                    from user_profile.fcm import send_push_to_user

                    send_push_to_user(
                        user=referrer,
                        title="Referral Task Complete! 🎉",
                        body=f"You completed '{challenge.name}'! {final_points} pts have been credited.",
                        data={
                            "type": "inapp_referral_task_completed",
                            "challenge_id": str(challenge.id),
                        },
                    )
                except Exception:
                    logger.exception(
                        "FCM push failed for in-app referral task completion: user=%s",
                        referrer.email,
                    )
            else:
                logger.warning(
                    "In-app referral task reward blocked for %s: %s",
                    referrer.email,
                    msg,
                )
                user_streak.save(
                    update_fields=[
                        "current_count",
                        "longest_count",
                        "last_activity_date",
                    ]
                )
