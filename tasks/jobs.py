import logging

from celery import shared_task
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def run_verification(self, submission_id: str):
    """
    Async task: verify a TaskSubmission using Claude Vision, then
    auto-approve/reject based on the verdict and the user's trust score.
    """
    from .models import TaskSubmission, VerificationResult, UserTrustScore
    from .verification import verify_submission, VerificationError

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
                "hashtag_found": result["hashtag_found"],
                "mention_found": result["mention_found"],
                "action_confirmed": result["action_confirmed"],
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
            # Queue for manual review — low confidence, Uncertain, or low trust
            submission.status = "Pending"
            submission.save(update_fields=["status"])
            logger.info("Submission %s queued for manual review (verdict=%s)", submission_id, verdict)


def _approve_submission(submission, trust):
    from gamification.models import Points

    submission.status = "Approved"
    submission.reward_issued = True
    submission.save(update_fields=["status", "reward_issued"])

    trust.record_approval()

    # Increment task counter
    task = submission.task
    task.total_submissions += 1
    task.save(update_fields=["total_submissions"])

    # Issue points reward
    if submission.task.reward_points:
        points, _ = Points.objects.get_or_create(user=submission.user)
        points.balance += submission.task.reward_points
        points.save(update_fields=["balance"])

    logger.info("Auto-approved submission %s, issued %d pts", submission.pk, submission.task.reward_points)


def _reject_submission(submission, trust, reason: str = ""):
    submission.status = "Rejected"
    submission.rejection_reason = reason
    submission.save(update_fields=["status", "rejection_reason"])
    trust.record_rejection()
    logger.info("Auto-rejected submission %s", submission.pk)


@shared_task
def manual_approve(submission_id: str, reviewer_id: str):
    """Admin/moderator manually approves a submission."""
    from .models import TaskSubmission, UserTrustScore
    from accounts.models import User
    from gamification.models import Points

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
            points, _ = Points.objects.get_or_create(user=submission.user)
            points.balance += submission.task.reward_points
            points.save(update_fields=["balance"])


@shared_task
def manual_reject(submission_id: str, reviewer_id: str, reason: str = ""):
    """Admin/moderator manually rejects a submission."""
    from .models import TaskSubmission, UserTrustScore
    from accounts.models import User

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
