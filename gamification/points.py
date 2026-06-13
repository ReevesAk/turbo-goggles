import logging
from decimal import Decimal

from django.db import models, transaction

from .models import PointTransaction, Points as PointsModel
from .utils import NextBee

logger = logging.getLogger(__name__)


LEVEL_MULTIPLIERS = {
    "Starter": 1.0,
    "Explorer": 1.1,
    "Challenger": 1.2,
    "Influencer": 1.3,
    "Champion": 1.5,
    "Elite": 1.7,
    "Legend": 2.0,
}

BASE_POINTS = {
    "daily_login": 30,
    "service_purchase": 30,
    "financial_task": 175,
    "social_engagement": 175,
    "referral": 300,
    "special_campaign": 300,
    "streak_bonus": 200,
}

# New tier → naira-per-point mapping
TIER_VALUES = {
    "Explorer": Decimal("0.50"),
    "Challenger": Decimal("1.00"),
    "Influencer": Decimal("1.50"),
    "Champion": Decimal("2.00"),
    "Elite": Decimal("2.50"),
    "Legend": Decimal("3.00"),
}

MIN_POINTS_REQUIRED = 400


class Points:
    @staticmethod
    def get_user_tier(total_points: int):
        """
        Determine tier based on lifetime points.
        """
        if total_points >= 6000:
            return "Legend"
        elif total_points >= 4000:
            return "Elite"
        elif total_points >= 2500:
            return "Champion"
        elif total_points >= 1500:
            return "Influencer"
        elif total_points >= 800:
            return "Challenger"
        elif total_points >= 400:
            return "Explorer"
        return "Starter"

    @staticmethod
    def calculate_redeemable(user_points: int, total_points: int):
        """
        Returns a tuple: (points_redeemable, naira_value, tier_name).
        """
        tier = Points.get_user_tier(total_points)

        if tier == "Starter" or user_points < MIN_POINTS_REQUIRED:
            return 0, Decimal("0.00"), tier  # No redemption allowed

        rate = TIER_VALUES.get(tier, Decimal("0.50"))
        naira_value = Decimal(MIN_POINTS_REQUIRED) * rate

        # Points used is always MIN_POINTS_REQUIRED for eligible tiers
        points_used = MIN_POINTS_REQUIRED

        return points_used, naira_value, tier

    @staticmethod
    def refresh_user_points(user):
        """
        Fetch points from NextBee API and update Points model.
        Also updates tier name and naira value.
        """
        response = NextBee.points_summary(member_email=user.email)
        if response.status_code == 200:
            data = response.json()

            latest_balance = int(data.get("total_points", 0))        # lifetime points
            available_points = int(data.get("available_points", 0))  # usable points

            redeemable_points, naira_value, tier_name = Points.calculate_redeemable(
                available_points, latest_balance
            )

            points_obj, _ = PointsModel.objects.get_or_create(user=user)

            # Update naira value of points.
            user.points_naira_value = naira_value
            user.save(update_fields=["points_naira_value"])

            with transaction.atomic():
                points_obj.balance = available_points
                points_obj.tier = tier_name
                points_obj.naira_value = naira_value
                points_obj.save(update_fields=["balance", "tier", "naira_value"])
        else:
            logging.warning(f"Could not refresh points for {user.email}: {response.text}")

    @staticmethod
    def determine(activity_type: str, level: str) -> int:
        base = BASE_POINTS.get(activity_type, 0)
        multiplier = LEVEL_MULTIPLIERS.get(level, 1.0)
        return int(base * multiplier)

    # ── Internal points engine (no NextBee) ───────────────────────────────────

    @staticmethod
    def check_credibility(user) -> tuple[bool, str]:
        """
        Verify a user is eligible to receive points before any award.

        Checks (in order):
        1. Account must be active and verified.
        2. Trust score must be above the hard floor (20). Below this the user
           has too many rejected/flagged submissions to be trusted automatically.
        3. Lifetime rejection rate must be under 60 % (catches repeat fraudsters
           who occasionally get approved).
        4. Absolute flagged-submission count must be under 6.

        Returns (True, "OK") when all checks pass, or (False, reason) on the
        first failing check so the caller knows exactly why the award was blocked.
        """
        if not user.is_active:
            return False, "Account is inactive"

        if not user.is_verified:
            return False, "Account is not verified"

        try:
            from tasks.models import UserTrustScore
            trust = UserTrustScore.objects.get(user=user)

            if trust.requires_manual_review:
                return False, f"Trust score too low ({trust.score}/100) — manual review required"

            if trust.flagged_submissions >= 6:
                return False, f"Too many flagged submissions ({trust.flagged_submissions})"

            if trust.total_submissions >= 5:
                rejection_rate = trust.rejected_submissions / trust.total_submissions
                if rejection_rate > 0.6:
                    return False, f"Rejection rate too high ({int(rejection_rate * 100)}%)"

        except Exception:
            # No trust record yet (brand new user) — allow
            pass

        return True, "OK"

    @staticmethod
    def award(
        user,
        amount: int,
        reason: str,
        source: str = "task_completion",
        reference_id: str = None,
        triggered_by=None,
        bypass_credibility: bool = False,
    ) -> tuple[bool, str]:
        """
        Award points to a user.

        Flow:
          1. Run credibility check — block immediately if the user fails.
             Pass bypass_credibility=True to skip this (used for refunds).
          2. Inside a single atomic transaction:
             a. Get-or-create the user's Points record.
             b. Add amount to the usable balance.
             c. Add amount to user.total_points (lifetime counter used for tier).
             d. Recalculate tier and naira_value from the new lifetime total.
             e. Write an immutable PointTransaction ledger entry.
          3. Return (True, message) on success or (False, reason) on failure.

        The atomic block means the balance, tier, and ledger entry are always
        consistent — partial writes cannot happen.
        """
        if not bypass_credibility:
            credible, msg = Points.check_credibility(user)
            if not credible:
                logger.warning("Points award blocked for %s: %s", user.email, msg)
                return False, msg

        try:
            with transaction.atomic():
                points_obj, _ = PointsModel.objects.select_for_update().get_or_create(user=user)

                new_balance = points_obj.balance + amount
                new_lifetime = (user.total_points or 0) + amount
                new_tier = Points.get_user_tier(new_lifetime)
                rate = TIER_VALUES.get(new_tier, Decimal("0"))
                new_naira = Decimal(new_balance) * rate

                points_obj.balance = new_balance
                points_obj.tier = new_tier
                points_obj.naira_value = new_naira
                points_obj.save(update_fields=["balance", "tier", "naira_value"])

                user.total_points = new_lifetime
                user.save(update_fields=["total_points"])

                PointTransaction.objects.create(
                    user=user,
                    transaction_type=PointTransaction.AWARD,
                    amount=amount,
                    reason=reason,
                    source=source,
                    reference_id=str(reference_id) if reference_id else None,
                    triggered_by=triggered_by,
                    balance_after=new_balance,
                )
        except Exception as exc:
            logger.exception("Failed to award %d points to %s", amount, user.email)
            return False, str(exc)

        logger.info("Awarded %d pts to %s (balance: %d, tier: %s)", amount, user.email, new_balance, new_tier)
        return True, f"{amount} points awarded. New balance: {new_balance}, tier: {new_tier}"

    @staticmethod
    def deduct(
        user,
        amount: int,
        reason: str,
        source: str = "penalty",
        reference_id: str = None,
        triggered_by=None,
    ) -> tuple[bool, str]:
        """
        Deduct points from a user. Balance cannot go below zero.
        Tier is NOT recalculated downward on deduction — tier is earned, not lost.
        """
        try:
            with transaction.atomic():
                points_obj, _ = PointsModel.objects.select_for_update().get_or_create(user=user)

                actual_deduction = min(amount, points_obj.balance)
                new_balance = points_obj.balance - actual_deduction

                points_obj.balance = new_balance
                points_obj.save(update_fields=["balance"])

                PointTransaction.objects.create(
                    user=user,
                    transaction_type=PointTransaction.DEDUCT,
                    amount=actual_deduction,
                    reason=reason,
                    source=source,
                    reference_id=str(reference_id) if reference_id else None,
                    triggered_by=triggered_by,
                    balance_after=new_balance,
                )
        except Exception as exc:
            logger.exception("Failed to deduct %d points from %s", amount, user.email)
            return False, str(exc)

        logger.info("Deducted %d pts from %s (balance: %d)", actual_deduction, user.email, new_balance)
        return True, f"{actual_deduction} points deducted. New balance: {new_balance}"

    @staticmethod
    def refresh(user):
        """
        Internal equivalent of refresh_user_points (no NextBee API call).

        Recomputes the user's current balance and tier by replaying the full
        PointTransaction ledger: sum all awards minus all deductions.
        Use this to self-heal after manual DB edits or to sync a user on login.
        """
        totals = PointTransaction.objects.filter(user=user).aggregate(
            awarded=models.Sum("amount", filter=models.Q(transaction_type=PointTransaction.AWARD)),
            deducted=models.Sum("amount", filter=models.Q(transaction_type=PointTransaction.DEDUCT)),
        )
        lifetime = totals["awarded"] or 0
        deducted = totals["deducted"] or 0
        balance = max(0, lifetime - deducted)

        tier = Points.get_user_tier(lifetime)
        rate = TIER_VALUES.get(tier, Decimal("0"))
        naira_value = Decimal(balance) * rate

        points_obj, _ = PointsModel.objects.get_or_create(user=user)
        with transaction.atomic():
            points_obj.balance = balance
            points_obj.tier = tier
            points_obj.naira_value = naira_value
            points_obj.save(update_fields=["balance", "tier", "naira_value"])

            user.total_points = lifetime
            user.save(update_fields=["total_points"])

        logger.info("Refreshed points for %s: balance=%d, tier=%s", user.email, balance, tier)
        return points_obj
