"""Progress tracking for streak_type="financial_task" / action_type=
"count_based" challenges (e.g. "transfer at least ₦100, 5 times") driven by
real transactions, rather than the generic manual check-in endpoint
(tasks/views.py's CompleteWebviewTaskView) used by other streak types.

Mirrors gamification.referrals._check_inapp_referral_tasks() — the existing
convention for this same StreakChallenge/UserStreak mechanism, just a
different mission_category: only challenges the user has already joined
(has a UserStreak row for via JoinStreakChallengeView) are touched, joining
being what opts a user into a specific challenge's reward. Completion
behavior branches on challenge.is_recurring: recurring challenges reset
current_count/completed back to zero so they can be earned again;
non-recurring ones stay permanently completed, same as referral tasks.

Entry point is record_financial_task_progress(), called from
gamification.signals whenever a TxModel row tagged with is_task/task_id
transitions to SUCCESS.
"""

import logging
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .models import UserStreak
from .points import Points

logger = logging.getLogger(__name__)


def record_financial_task_progress(user, task_id, amount):
    with transaction.atomic():
        user_streak = (
            UserStreak.objects.select_for_update()
            .filter(
                user=user,
                challenge_id=task_id,
                completed=False,
                challenge__streak_type="financial_task",
                challenge__action_type="count_based",
                challenge__is_active=True,
                challenge__is_paused=False,
                challenge__is_cancelled=False,
            )
            .select_related("challenge")
            .first()
        )
        if user_streak is None:
            logger.info(
                "record_financial_task_progress: no joined, active, "
                "count_based financial_task UserStreak for task_id=%s user=%s "
                "— ignoring.",
                task_id,
                user.email,
            )
            return

        challenge = user_streak.challenge
        if not challenge.is_ongoing:
            return

        if (
            challenge.min_amount_per_action is not None
            and Decimal(str(amount)) < challenge.min_amount_per_action
        ):
            logger.info(
                "record_financial_task_progress: %s below min_amount_per_action "
                "(%s) for challenge=%s user=%s — not counted.",
                amount,
                challenge.min_amount_per_action,
                challenge.id,
                user.email,
            )
            return

        user_streak.current_count += 1
        user_streak.longest_count = max(
            user_streak.longest_count, user_streak.current_count
        )
        user_streak.last_activity_date = timezone.now().date()

        required_count = challenge.required_count or 1
        if user_streak.current_count < required_count:
            user_streak.save(
                update_fields=["current_count", "longest_count", "last_activity_date"]
            )
            return

        level_multiplier = Points.get_level_multiplier(
            Points.get_user_tier(user.total_points or 0)
        )
        final_points = int(challenge.reward_points * level_multiplier)

        awarded, message = Points.award(
            user=user,
            amount=final_points,
            reason=f"Completed challenge: {challenge.name}",
            source="inapp_task",
            reference_id=str(challenge.id),
        )
        if not awarded:
            logger.warning(
                "record_financial_task_progress: challenge=%s reached for "
                "user=%s but Points.award failed: %s",
                challenge.id,
                user.email,
                message,
            )
            user_streak.save(
                update_fields=["current_count", "longest_count", "last_activity_date"]
            )
            return

        user_streak.completed_at = timezone.now()
        if challenge.is_recurring:
            # Reset immediately so this repeatable financial task starts a
            # fresh cycle - unlike referral in-app tasks, which stay
            # permanently completed once reached.
            user_streak.current_count = 0
            user_streak.completed = False
            user_streak.reward_issued = False
        else:
            # One-and-done, same convention as referral in-app tasks -
            # current_count stays at its final value, completed=True keeps
            # it out of the `completed=False` filter above for good.
            user_streak.completed = True
            user_streak.reward_issued = True
        user_streak.save(
            update_fields=[
                "current_count",
                "longest_count",
                "last_activity_date",
                "completed_at",
                "completed",
                "reward_issued",
            ]
        )

    try:
        from user_profile.fcm import send_push_to_user

        send_push_to_user(
            user=user,
            title="Task Complete! 🎉",
            body=f"You completed '{challenge.name}'! {final_points} pts have been credited.",
            data={
                "type": "inapp_financial_task_completed",
                "challenge_id": str(challenge.id),
            },
        )
    except Exception:
        logger.exception(
            "FCM push failed for in-app financial task completion: user=%s",
            user.email,
        )
