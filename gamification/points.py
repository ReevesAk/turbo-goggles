import logging
from decimal import Decimal

from django.db import transaction

from .utils import NextBee


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

            points_obj, _ = user.points_set.get_or_create(user=user)

            # Update naira value of points.
            user.points_naira_value = naira_value
            user.save(update_fields=["points_naira_value"])

            with transaction.atomic():
                points_obj.balance = available_points
                points_obj.redeemable = redeemable_points
                points_obj.tier = tier_name
                points_obj.naira_value = naira_value
                points_obj.save(update_fields=["balance", "redeemable", "tier", "naira_value"])
        else:
            logging.warning(f"Could not refresh points for {user.email}: {response.text}")

    @staticmethod
    def determine(activity_type: str, level: str) -> int:
        base = BASE_POINTS.get(activity_type, 0)
        multiplier = LEVEL_MULTIPLIERS.get(level, 1.0)
        return int(base * multiplier)
