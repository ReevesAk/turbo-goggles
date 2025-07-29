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


def calculate_points(activity_type: str, level: str) -> int:
    base = BASE_POINTS.get(activity_type, 0)
    multiplier = LEVEL_MULTIPLIERS.get(level, 1.0)
    return int(base * multiplier)
