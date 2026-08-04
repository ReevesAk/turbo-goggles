# gamification/tasks.py

import logging
from datetime import timedelta

from celery import shared_task
from django.db.models import Sum, Count
from django.utils import timezone

logger = logging.getLogger(__name__)


def _check_user_activity(user, streak_type, date):
    """
    Returns True if the user completed the streak_type activity on the given date.
    """
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

    # Check UGC submissions
    if streak_type == "ugc_task_completion":
        from .models import UGCTaskSubmission

        return UGCTaskSubmission.objects.filter(
            user=user,
            status="approved",
            reviewed_at__date=date,
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
    """
    Daily task (runs ~midnight) that increments or resets each user's active streaks.
    """
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

                    # Use level multiplier for streak rewards
                    reward_points = challenge.reward_points
                    level_multiplier = Points.get_level_multiplier(
                        Points.get_user_tier(user_streak.user.total_points or 0)
                    )
                    final_points = int(reward_points * level_multiplier)

                    ok, _ = Points.award(
                        user=user_streak.user,
                        amount=final_points,
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
                                body=f"You completed the '{challenge.name}' streak! {final_points} pts have been credited.",
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
    End-of-day reminder: sends push notifications to users who haven't completed
    today's streak activity yet.
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


# ==================
# UGC-specific tasks
# ==================


@shared_task(name="gamification.tasks.calculate_ugc_leaderboard")
def calculate_ugc_leaderboard():
    """
    Scheduled task to recalculate UGC leaderboards.
    Runs daily at midnight.
    """
    from .models import UGCTaskSubmission, UGCLeaderboard

    timeframes = ["daily", "weekly", "monthly", "all_time"]
    now = timezone.now()
    today = now.date()

    for timeframe in timeframes:
        # Determine period
        if timeframe == "daily":
            period_start = today
            period_end = today
        elif timeframe == "weekly":
            period_start = today - timedelta(days=7)
            period_end = today
        elif timeframe == "monthly":
            period_start = today - timedelta(days=30)
            period_end = today
        else:  # all_time
            period_start = None
            period_end = None

        # Get approved submissions
        qs = UGCTaskSubmission.objects.filter(status="approved")

        if period_start and period_end:
            qs = qs.filter(
                reviewed_at__date__gte=period_start, reviewed_at__date__lte=period_end
            )

        # Aggregate by user
        user_stats = (
            qs.values("user")
            .annotate(points_earned=Sum("points_awarded"), tasks_completed=Count("id"))
            .order_by("-points_earned")
        )

        # Clear existing entries
        UGCLeaderboard.objects.filter(timeframe=timeframe).delete()

        # Create new entries
        entries = []
        for rank, stat in enumerate(user_stats, 1):
            entries.append(
                UGCLeaderboard(
                    user_id=stat["user"],
                    timeframe=timeframe,
                    rank=rank,
                    points_earned=stat["points_earned"] or 0,
                    tasks_completed=stat["tasks_completed"],
                    period_start=period_start or today,
                    period_end=period_end or today,
                )
            )

        if entries:
            UGCLeaderboard.objects.bulk_create(entries)

    return f"Leaderboard calculated for {len(timeframes)} timeframes"


@shared_task(name="gamification.tasks.check_ugc_achievements")
def check_ugc_achievements():
    """
    Check and award UGC achievement bonuses.
    Runs hourly.
    """
    from .models import UGCTaskProgress
    from .points import UGC_ACHIEVEMENTS, Points

    awarded = 0

    for milestone, achievement in UGC_ACHIEVEMENTS.items():
        achievement_key = f"ugc_achievement_{milestone}"

        # Find users who have reached this milestone but haven't received the achievement
        progresses = (
            UGCTaskProgress.objects.filter(
                approved_submissions=milestone,
            )
            .exclude(achievements__contains=[achievement_key])
            .select_related("user")
        )

        for progress in progresses:
            success, _ = Points.award(
                user=progress.user,
                amount=achievement["points"],
                reason=f"🏆 {achievement['title']}",
                source="special_campaign",
            )
            if success:
                progress.achievements.append(achievement_key)
                progress.save(update_fields=["achievements"])
                awarded += 1

                logger.info(
                    "UGC achievement awarded: %s - %s (%d pts)",
                    progress.user.email,
                    achievement["title"],
                    achievement["points"],
                )

    return f"UGC achievements checked: {awarded} awarded"


@shared_task(name="gamification.tasks.update_ugc_levels")
def update_ugc_levels():
    """
    Update UGC levels for all users based on their approved submissions.
    Runs daily.
    """
    from .models import UGCTaskProgress
    from .points import Points

    updated = 0
    progresses = UGCTaskProgress.objects.select_related("user").all()

    for progress in progresses:
        new_level = Points.get_ugc_level(progress.approved_submissions)

        # Log the level update
        logger.info(
            "UGC level for %s: %s (%d submissions)",
            progress.user.email,
            new_level,
            progress.approved_submissions,
        )
        updated += 1

    return f"UGC levels updated for {updated} users"


@shared_task(name="gamification.tasks.cleanup_old_leaderboard_entries")
def cleanup_old_leaderboard_entries():
    """
    Clean up old leaderboard entries to prevent unlimited growth.
    Runs weekly.
    """
    from .models import UGCLeaderboard

    # Keep only last 30 days of daily/weekly entries
    cutoff_date = timezone.now().date() - timedelta(days=30)

    deleted, _ = UGCLeaderboard.objects.filter(
        period_start__lt=cutoff_date, timeframe__in=["daily", "weekly"]
    ).delete()

    logger.info("Cleaned up %d old leaderboard entries", deleted)
    return f"Cleaned up {deleted} old leaderboard entries"


@shared_task(name="gamification.tasks.cleanup_rejected_submissions")
def cleanup_rejected_submissions():
    """
    Clean up rejected submissions older than 90 days.
    Runs monthly.
    """
    from .models import UGCTaskSubmission

    cutoff_date = timezone.now() - timedelta(days=90)

    deleted, _ = UGCTaskSubmission.objects.filter(
        status="rejected", submitted_at__lt=cutoff_date
    ).delete()

    logger.info("Cleaned up %d old rejected submissions", deleted)
    return f"Cleaned up {deleted} old rejected submissions"


@shared_task(name="gamification.tasks.sync_ugc_progress")
def sync_ugc_progress():
    """
    Sync UGC progress for all users by replaying approved submissions.
    Runs weekly to correct any inconsistencies.
    """
    from django.contrib.auth import get_user_model
    from .models import UGCTaskSubmission, UGCTaskProgress

    User = get_user_model()

    updated = 0
    users = User.objects.filter(ugc_submissions__status="approved").distinct()

    for user in users:
        # Get all approved submissions for this user
        submissions = UGCTaskSubmission.objects.filter(
            user=user, status="approved"
        ).select_related("task")

        progress, created = UGCTaskProgress.objects.get_or_create(user=user)

        # If no submissions, set zeros
        if not submissions.exists():
            progress.total_submissions = 0
            progress.approved_submissions = 0
            progress.rejected_submissions = UGCTaskSubmission.objects.filter(
                user=user, status="rejected"
            ).count()
            progress.completed_task_types = {}
            progress.current_streak = 0
            progress.longest_streak = 0
            progress.last_submission_date = None
            progress.save()
            updated += 1
            continue

        # Recalculate from scratch
        total = submissions.count()
        approved = total
        rejected = UGCTaskSubmission.objects.filter(
            user=user, status="rejected"
        ).count()

        # Rebuild completed_task_types
        task_types = {}
        for sub in submissions:
            task_type = sub.task.task_type
            task_types[task_type] = task_types.get(task_type, 0) + 1

        # Update progress
        progress.total_submissions = total + rejected
        progress.approved_submissions = approved
        progress.rejected_submissions = rejected
        progress.completed_task_types = task_types

        # Recalculate streak from submission dates
        submission_dates = list(
            submissions.values_list("reviewed_at__date", flat=True)
            .distinct()
            .order_by("-reviewed_at__date")
        )

        current_streak = 0
        longest_streak = 0
        last_date = None

        for date in submission_dates:
            if last_date is None:
                current_streak = 1
            elif (last_date - date).days == 1:
                current_streak += 1
            else:
                current_streak = 1

            longest_streak = max(longest_streak, current_streak)
            last_date = date

        progress.current_streak = current_streak
        progress.longest_streak = longest_streak
        progress.last_submission_date = last_date

        progress.save()
        updated += 1

    logger.info("Synced UGC progress for %d users", updated)
    return f"Synced UGC progress for {updated} users"
