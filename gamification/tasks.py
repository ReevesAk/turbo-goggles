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


def _targeting_kwargs_for(model_label, obj):
    """Reads the fixed set of targeting fields relevant to this model - see
    gamification/eligibility.py for what each kwarg does."""
    if model_label == "gamification.StepCampaignModel":
        return {"gender": obj.target_gender, "age_bracket": obj.target_age_bracket}

    if model_label == "gamification.StreakChallenge":
        return {"min_tier": obj.target_min_tier, "state": obj.target_state}

    if model_label == "gamification.ReferralTask":
        return {"min_tier": obj.target_min_tier, "state": obj.target_state}

    if model_label == "gamification.RewardRule":
        return {
            "min_tier": obj.target_min_tier,
            "state": obj.target_state,
            "exclude_verified": obj.source == "kyc_upgrade",
        }

    if model_label == "gamification.UserGeneratedContent":
        return {
            "gender": obj.gender,
            "age_bracket": obj.demography,
            "location_perimeter": obj.location_perimeter,
            "states": obj.states,
            "cities": obj.cities,
        }

    return {}


@shared_task(name="gamification.tasks.send_task_push")
def send_task_push(
    model_label: str, object_id, title: str, body: str, notif_type: str = "new_task"
):
    """
    Fan-out FCM push to has_done_survey members matching the given task's
    targeting fields. Called via .delay() right after a task/campaign is
    created, so the admin/brand request never blocks on the send.

    model_label: "<app_label>.<ModelName>", e.g. "gamification.StepCampaignModel".
    A walk_to_earn_gate ReferralTask is a silent prerequisite, not an
    announcement - callers should not invoke this for that mode.
    """
    from django.apps import apps

    from user_profile.fcm import send_push_to_user

    from .eligibility import eligible_members

    model = apps.get_model(model_label)
    try:
        obj = model.objects.get(pk=object_id)
    except model.DoesNotExist:
        logger.warning("send_task_push: %s %s no longer exists", model_label, object_id)
        return 0

    recipients = eligible_members(**_targeting_kwargs_for(model_label, obj))

    eligible_count = 0
    sent_count = 0
    for user in recipients:
        eligible_count += 1
        try:
            sent_count += send_push_to_user(
                user=user,
                title=title,
                body=body,
                data={"type": notif_type, "id": str(object_id)},
            )
        except Exception:
            logger.exception("send_task_push: push failed for user=%s", user.email)

    logger.info(
        "send_task_push: %s %s - %d device pushes sent across %d eligible members",
        model_label,
        object_id,
        sent_count,
        eligible_count,
    )
    return sent_count


def queue_task_push(
    model_label: str, object_id, title: str, body: str, notif_type: str = "new_task"
):
    """
    Synchronously counts how many members currently match the task's
    targeting fields (one fast COUNT query - cheap enough to do inline,
    unlike the actual send), then fires the real push asynchronously via
    send_task_push.delay(). A broker hiccup on that async call (e.g. Redis
    unreachable) is caught and logged rather than raised, so it can't fail
    the create request that already has its count to return.

    Returns the eligible member count - how many members match right now,
    not how many pushes were actually delivered (some may have no device
    token, or FCM may fail per-device; see send_task_push's own logs for
    delivery counts).
    """
    from django.apps import apps

    from .eligibility import eligible_members

    model = apps.get_model(model_label)
    try:
        obj = model.objects.get(pk=object_id)
        eligible_count = eligible_members(
            **_targeting_kwargs_for(model_label, obj)
        ).count()
    except model.DoesNotExist:
        logger.warning(
            "queue_task_push: %s %s no longer exists", model_label, object_id
        )
        eligible_count = 0

    try:
        send_task_push.delay(model_label, object_id, title, body, notif_type)
    except Exception:
        logger.exception(
            "Failed to queue push notification for %s %s", model_label, object_id
        )

    return eligible_count
