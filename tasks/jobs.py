import logging

from celery import shared_task
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from accounts.models import User
from gamification.points import Points, BASE_POINTS
from user_profile.fcm import send_push_to_user, send_push_to_admins
from .models import BrandTaskSubmission, TaskSubmission, VerificationResult, UserTrustScore
from .verification import verify_submission, verify_brand_submission, VerificationError

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def run_verification(self, submission_id: str):
    """
    Async task: verify a TaskSubmission using Claude Vision, then
    auto-approve/reject based on the verdict and the user's trust score.
    """
    try:
        submission = TaskSubmission.objects.select_related(
            "task", "user", "user__social_profile"
        ).get(pk=submission_id)
    except TaskSubmission.DoesNotExist:
        logger.error("run_verification: submission %s not found", submission_id)
        return

    if submission.status != "Pending":
        logger.info("Skipping already-processed submission %s", submission_id)
        return

    try:
        result = verify_submission(submission)
    except VerificationError as exc:
        logger.warning("Verification failed for %s: %s", submission_id, exc)
        self.retry(exc=exc)
        return

    with transaction.atomic():
        VerificationResult.objects.update_or_create(
            submission=submission,
            defaults={
                "verdict": result["verdict"],
                "confidence_score": result["confidence_score"],
                "ai_reasoning": result["reasoning"],
                "flags": result["flags"],
                "username_matched": result["username_matched"],
                "target_matched": result["target_matched"],
                "hashtag_found": result["hashtag_found"],
                "mention_found": result["mention_found"],
                "action_confirmed": result["action_confirmed"],
                "verification_code_found": result["verification_code_found"],
            },
        )

        trust, _ = UserTrustScore.objects.get_or_create(user=submission.user)
        verdict = result["verdict"]
        confidence = result["confidence_score"]

        if verdict == "Pass" and trust.can_auto_approve and confidence >= 70:
            _approve_submission(submission, trust)
        elif verdict == "Fail" and confidence >= 80:
            _reject_submission(submission, trust, reason="AI verification failed")
        else:
            submission.status = "Pending"
            submission.save(update_fields=["status"])
            logger.info("Submission %s queued for manual review (verdict=%s)", submission_id, verdict)
            send_push_to_admins(
                title="Submission Needs Review",
                body=f"{submission.user.full_name or submission.user.email} submitted proof for '{submission.task.title}' — requires manual review.",
                data={"type": "manual_review", "submission_id": submission_id},
            )


def _approve_submission(submission, trust):
    submission.status = "Approved"
    submission.reward_issued = True
    submission.save(update_fields=["status", "reward_issued"])

    trust.record_approval()

    task = submission.task
    task.total_submissions += 1
    task.save(update_fields=["total_submissions"])

    if task.reward_points:
        Points.award(
            user=submission.user,
            amount=task.reward_points,
            reason=f"Completed task: {task.title}",
            source="task_completion",
            reference_id=str(submission.pk),
        )

    send_push_to_user(
        user=submission.user,
        title="Submission Approved! 🎉",
        body=f"Your submission for '{task.title}' was approved. {task.reward_points} pts credited.",
        data={"type": "task_approved", "submission_id": str(submission.pk)},
    )
    logger.info("Auto-approved submission %s, issued %d pts", submission.pk, task.reward_points)


def _reject_submission(submission, trust, reason: str = ""):
    submission.status = "Rejected"
    submission.rejection_reason = reason
    submission.save(update_fields=["status", "rejection_reason"])
    trust.record_rejection()
    send_push_to_user(
        user=submission.user,
        title="Submission Not Approved",
        body=f"Your submission for '{submission.task.title}' was not approved. {reason or 'Please review our guidelines and try again.'}",
        data={"type": "task_rejected", "submission_id": str(submission.pk)},
    )
    logger.info("Auto-rejected submission %s", submission.pk)


@shared_task
def manual_approve(submission_id: str, reviewer_id: str):
    """Admin/moderator manually approves a submission."""
    try:
        submission = TaskSubmission.objects.select_related("task", "user").get(pk=submission_id)
        reviewer = User.objects.get(pk=reviewer_id)
    except (TaskSubmission.DoesNotExist, User.DoesNotExist):
        return

    with transaction.atomic():
        submission.status = "Approved"
        submission.reward_issued = True
        submission.reviewed_by = reviewer
        submission.reviewed_at = timezone.now()
        submission.save(update_fields=["status", "reward_issued", "reviewed_by", "reviewed_at"])

        trust, _ = UserTrustScore.objects.get_or_create(user=submission.user)
        trust.record_approval()

        submission.task.total_submissions += 1
        submission.task.save(update_fields=["total_submissions"])

        if submission.task.reward_points:
            Points.award(
                user=submission.user,
                amount=submission.task.reward_points,
                reason=f"Completed task: {submission.task.title}",
                source="task_completion",
                reference_id=str(submission.pk),
                triggered_by=reviewer,
            )

    send_push_to_user(
        user=submission.user,
        title="Submission Approved! 🎉",
        body=f"Your submission for '{submission.task.title}' was approved. {submission.task.reward_points} pts credited.",
        data={"type": "task_approved", "submission_id": str(submission.pk)},
    )


@shared_task
def manual_reject(submission_id: str, reviewer_id: str, reason: str = ""):
    """Admin/moderator manually rejects a submission."""
    try:
        submission = TaskSubmission.objects.select_related("user").get(pk=submission_id)
        reviewer = User.objects.get(pk=reviewer_id)
    except (TaskSubmission.DoesNotExist, User.DoesNotExist):
        return

    with transaction.atomic():
        submission.status = "Rejected"
        submission.rejection_reason = reason
        submission.reviewed_by = reviewer
        submission.reviewed_at = timezone.now()
        submission.save(update_fields=["status", "rejection_reason", "reviewed_by", "reviewed_at"])

        trust, _ = UserTrustScore.objects.get_or_create(user=submission.user)
        trust.record_rejection()

    send_push_to_user(
        user=submission.user,
        title="Submission Not Approved",
        body=f"Your submission for '{submission.task.title}' was not approved. {reason or 'Please review our guidelines and try again.'}",
        data={"type": "task_rejected", "submission_id": str(submission.pk)},
    )


# ── Brand campaign task jobs ──────────────────────────────────────────────────

# Maps task_type to the points source label used in the ledger
_BRAND_TASK_SOURCE = {
    "watch_video": "watch_video",
    "social_engage": "social_engagement",
    "website_visit": "website_visit",
    "store_visit": "store_visit",
    "survey": "survey_completion",
    "app_download": "app_download",
}


def approve_brand_submission_now(submission_id: str, reviewer_id: str = None):
    """
    Approve a BrandTaskSubmission and credit points to the user.
    reviewer_id is None for auto-approvals (timer/QR/survey completions).
    """
    try:
        submission = BrandTaskSubmission.objects.select_related("ad", "user").get(
            pk=submission_id
        )
    except BrandTaskSubmission.DoesNotExist:
        logger.error("approve_brand_submission: submission %s not found", submission_id)
        return

    if submission.status == "Approved":
        logger.info("Brand submission %s already approved — skipping", submission_id)
        return

    reviewer = None
    if reviewer_id:
        try:
            reviewer = User.objects.get(pk=reviewer_id)
        except User.DoesNotExist:
            pass

    with transaction.atomic():
        submission.status = "Approved"
        submission.reward_issued = True
        submission.reviewed_by = reviewer
        submission.reviewed_at = timezone.now()
        submission.save(update_fields=["status", "reward_issued", "reviewed_by", "reviewed_at"])

        trust, _ = UserTrustScore.objects.get_or_create(user=submission.user)
        trust.record_approval()

        ad = submission.ad
        from adverts.models import CreateAd as _CreateAd
        _CreateAd.objects.filter(pk=ad.pk).update(slots_filled=F("slots_filled") + 1)

        # Credit points using the brand-set reward_points, falling back to BASE_POINTS
        task_type = ad.task_type or ""
        points_amount = ad.reward_points or BASE_POINTS.get(task_type, 0)
        source = _BRAND_TASK_SOURCE.get(task_type, "brand_task")

        if points_amount:
            Points.award(
                user=submission.user,
                amount=points_amount,
                reason=f"Completed brand task: {ad.campaign_name}",
                source=source,
                reference_id=str(submission.pk),
                triggered_by=reviewer,
            )

    send_push_to_user(
        user=submission.user,
        title="Brand Task Complete! 🎉",
        body=f"You completed '{ad.campaign_name}' and earned {points_amount} pts.",
        data={"type": "brand_task_approved", "submission_id": submission_id},
    )
    logger.info(
        "Brand submission %s approved — %d pts awarded to %s",
        submission_id, points_amount, submission.user.email,
    )
    return points_amount


@shared_task
def approve_brand_submission(submission_id: str, reviewer_id: str = None):
    approve_brand_submission_now(submission_id, reviewer_id)


@shared_task
def reject_brand_submission(submission_id: str, reviewer_id: str, reason: str = ""):
    """Admin rejects a BrandTaskSubmission."""
    try:
        submission = BrandTaskSubmission.objects.select_related("user").get(pk=submission_id)
        reviewer = User.objects.get(pk=reviewer_id)
    except (BrandTaskSubmission.DoesNotExist, User.DoesNotExist):
        return

    with transaction.atomic():
        submission.status = "Rejected"
        submission.rejection_reason = reason
        submission.reviewed_by = reviewer
        submission.reviewed_at = timezone.now()
        submission.save(update_fields=["status", "rejection_reason", "reviewed_by", "reviewed_at"])
        trust, _ = UserTrustScore.objects.get_or_create(user=submission.user)
        trust.record_rejection()

    send_push_to_user(
        user=submission.user,
        title="Brand Task Not Approved",
        body=f"Your brand task submission was not approved. {reason or 'Please review the requirements and try again.'}",
        data={"type": "brand_task_rejected", "submission_id": submission_id},
    )
    logger.info("Brand submission %s rejected by %s", submission_id, reviewer.email)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def run_brand_verification(self, submission_id: str):
    """
    Async task: verify a BrandTaskSubmission screenshot using Claude Vision,
    then approve or reject based on the verdict.
    """
    try:
        submission = BrandTaskSubmission.objects.select_related("ad", "user").get(pk=submission_id)
    except BrandTaskSubmission.DoesNotExist:
        logger.error("run_brand_verification: submission %s not found", submission_id)
        return

    if submission.status != "Pending":
        logger.info("Skipping already-processed brand submission %s", submission_id)
        return

    try:
        result = verify_brand_submission(submission)
    except VerificationError as exc:
        logger.warning("Brand verification failed for %s: %s", submission_id, exc)
        self.retry(exc=exc)
        return

    verdict = result["verdict"]
    confidence = result["confidence_score"]
    action_confirmed = result["action_confirmed"]
    target_matched = result["target_matched"]

    if verdict == "Pass" and confidence >= 85 and action_confirmed and target_matched:
        approve_brand_submission_now(submission_id, None)
    elif verdict == "Fail" or (verdict == "Pass" and not (action_confirmed and target_matched)) or confidence < 60:
        with transaction.atomic():
            submission.status = "Rejected"
            submission.rejection_reason = f"AI verification failed: {result['reasoning']}"
            submission.reviewed_at = timezone.now()
            submission.save(update_fields=["status", "rejection_reason", "reviewed_at"])
            trust, _ = UserTrustScore.objects.get_or_create(user=submission.user)
            trust.record_rejection()
        send_push_to_user(
            user=submission.user,
            title="Submission Not Accepted",
            body=result["reasoning"],
            data={"type": "brand_task_rejected", "submission_id": submission_id},
        )
        logger.info(
            "Brand submission %s auto-rejected by AI (confidence=%d): %s",
            submission_id, confidence, result["reasoning"],
        )
    else:
        with transaction.atomic():
            submission.status = "Flagged"
            submission.reviewed_at = timezone.now()
            submission.save(update_fields=["status", "reviewed_at"])
        logger.info(
            "Brand submission %s flagged for manual review (verdict=%s, confidence=%d)",
            submission_id, verdict, confidence,
        )
        send_push_to_admins(
            title="Brand Submission Needs Review",
            body=(
                f"{submission.user.full_name or submission.user.email} submitted proof "
                f"for '{submission.ad.campaign_name}' — requires manual review."
            ),
            data={"type": "manual_review_brand", "submission_id": submission_id},
        )
