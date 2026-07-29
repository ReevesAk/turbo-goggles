import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


def _check_user_activity(user, streak_type, date):
    """Returns True if the user completed the streak_type activity on the given date."""
    if streak_type == "daily_login":
        return bool(user.last_login and user.last_login.date() == date)

    brand_task_types = {
        "watch_video",
        "website_visit",
        "store_visit",
        "survey_completion",
        "app_download",
        "brand_task",
    }
    if streak_type in brand_task_types:
        from tasks.models import BrandTaskSubmission

        qs = BrandTaskSubmission.objects.filter(
            user=user, status="Approved", created_at__date=date
        )
        if streak_type != "brand_task":
            qs = qs.filter(ad__task_type=streak_type)
        return qs.exists()

    if streak_type == "social_engagement":
        from tasks.models import TaskSubmission

        return TaskSubmission.objects.filter(
            user=user, status="Approved", created_at__date=date
        ).exists()

    # Fallback: check PointTransaction with matching source
    from .models import PointTransaction

    return PointTransaction.objects.filter(
        user=user,
        source=streak_type,
        transaction_type="award",
        created_at__date=date,
    ).exists()


@shared_task(name="gamification.tasks.check_and_update_streaks")
def check_and_update_streaks():
    """Daily task (runs ~midnight) that increments or resets each user's active streaks."""
    from .models import StreakChallenge, UserStreak, StreakHistory
    from .points import Points

    yesterday = timezone.now().date() - timedelta(days=1)

    active_challenges = StreakChallenge.objects.filter(
        is_active=True,
        is_paused=False,
        end_date__gte=yesterday,
    )

    processed = 0
    for challenge in active_challenges:
        user_streaks = UserStreak.objects.filter(
            challenge=challenge,
            completed=False,
        ).select_related("user")

        for user_streak in user_streaks:
            did_activity = _check_user_activity(
                user_streak.user, challenge.streak_type, yesterday
            )

            if did_activity:
                user_streak.current_count += 1
                user_streak.last_activity_date = yesterday
                if user_streak.current_count > user_streak.longest_count:
                    user_streak.longest_count = user_streak.current_count

                if (
                    user_streak.current_count >= challenge.duration_days
                    and not user_streak.reward_issued
                ):
                    user_streak.completed = True
                    user_streak.completed_at = timezone.now()
                    ok, _ = Points.award(
                        user=user_streak.user,
                        amount=challenge.reward_points,
                        reason=f"Streak challenge completed: {challenge.name}",
                        source="streak_bonus",
                        reference_id=str(challenge.id),
                    )
                    if ok:
                        user_streak.reward_issued = True
                        StreakHistory.objects.create(
                            user=user_streak.user,
                            challenge=challenge,
                            streak_count_reached=user_streak.current_count,
                            completed=True,
                            reward_issued=True,
                        )
                        try:
                            from user_profile.fcm import send_push_to_user

                            send_push_to_user(
                                user=user_streak.user,
                                title="Streak Complete! 🔥",
                                body=f"You completed the '{challenge.name}' streak! {challenge.reward_points} pts have been credited.",
                                data={
                                    "type": "streak_completed",
                                    "challenge_id": str(challenge.id),
                                },
                            )
                        except Exception:
                            logger.exception(
                                "FCM push failed for streak completion: user=%s",
                                user_streak.user.email,
                            )
                        logger.info(
                            "Streak completed + reward issued: user=%s challenge=%s",
                            user_streak.user.email,
                            challenge.name,
                        )

                user_streak.save()
            else:
                if user_streak.current_count > 0:
                    StreakHistory.objects.create(
                        user=user_streak.user,
                        challenge=challenge,
                        streak_count_reached=user_streak.current_count,
                        broken_at=yesterday,
                        completed=False,
                        reward_issued=False,
                    )
                    logger.info(
                        "Streak broken: user=%s challenge=%s count_reached=%d",
                        user_streak.user.email,
                        challenge.name,
                        user_streak.current_count,
                    )
                    user_streak.current_count = 0
                    user_streak.save(update_fields=["current_count"])

            processed += 1

    logger.info(
        "check_and_update_streaks completed: %d user-streaks processed", processed
    )
    return processed


@shared_task(name="gamification.tasks.send_streak_reminders")
def send_streak_reminders():
    """
    End-of-day reminder: logs (and optionally notifies) users who haven't completed
    today's streak activity yet. Wire up push/email here once a notification system is in place.
    """
    from .models import StreakChallenge, UserStreak

    today = timezone.now().date()

    active_challenges = StreakChallenge.objects.filter(
        is_active=True,
        is_paused=False,
        start_date__lte=today,
        end_date__gte=today,
    )

    reminded = 0
    for challenge in active_challenges:
        user_streaks = UserStreak.objects.filter(
            challenge=challenge,
            completed=False,
        ).select_related("user")

        for user_streak in user_streaks:
            if user_streak.last_activity_date != today:
                logger.info(
                    "Streak reminder: user=%s challenge=%s current=%d",
                    user_streak.user.email,
                    challenge.name,
                    user_streak.current_count,
                )
                try:
                    from user_profile.fcm import send_push_to_user

                    send_push_to_user(
                        user=user_streak.user,
                        title="Keep your streak alive! 🔥",
                        body=(
                            f"You're on a {user_streak.current_count}-day streak for "
                            f"'{challenge.name}'. Complete today's activity before midnight!"
                        ),
                        data={
                            "type": "streak_reminder",
                            "challenge_id": str(challenge.id),
                        },
                    )
                except Exception:
                    logger.exception(
                        "FCM reminder failed for user=%s", user_streak.user.email
                    )
                reminded += 1

    logger.info("send_streak_reminders: %d reminders sent", reminded)
    return reminded
