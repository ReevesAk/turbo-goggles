from decimal import Decimal


# Unit cost table: task_type → (1-3 days, 4-7 days, 8-14 days)
UNIT_COST_TABLE = {
    "watch_video":   (Decimal("20"),   Decimal("15"),   Decimal("10")),
    "social_engage": (Decimal("50"),   Decimal("30"),   Decimal("20")),
    "app_download":  (Decimal("400"),  Decimal("200"),  Decimal("150")),
    "survey":        (Decimal("400"),  Decimal("200"),  Decimal("150")),
    "store_visit":   (Decimal("2000"), Decimal("1500"), Decimal("1200")),
    "website_visit": (Decimal("100"),  Decimal("50"),   Decimal("30")),
}

TARGETING_MULTIPLIERS = {
    "broad":      Decimal("1.00"),
    "city":       Decimal("1.15"),
    "niche":      Decimal("1.25"),
    "influencer": Decimal("1.50"),
}

TARGETING_TYPE_CHOICES = (
    ("broad",      "Broad — All of Nigeria"),
    ("city",       "City-Specific"),
    ("niche",      "Niche Behavior"),
    ("influencer", "Influencer Tier (10k+ followers)"),
)


def _duration_bucket(duration_days: int) -> int:
    """Returns index into the unit cost tuple: 0 = 1-3d, 1 = 4-7d, 2 = 8-14d."""
    if duration_days <= 3:
        return 0
    if duration_days <= 7:
        return 1
    return 2


def compute_unit_cost(task_type: str, duration_days: int) -> Decimal:
    """Base cost per engagement before the targeting multiplier."""
    row = UNIT_COST_TABLE.get(task_type)
    if not row:
        return Decimal("0")
    return row[_duration_bucket(duration_days)]


def compute_cost_per_engagement(
    task_type: str,
    duration_days: int,
    targeting_type: str = "broad",
) -> Decimal:
    """
    Final cost per engagement = unit_cost × targeting_multiplier.

    Examples
    --------
    PPE, 14 days, city  → ₦20 × 1.15 = ₦23.00
    PPA-Physical, 7 days, niche → ₦1,500 × 1.25 = ₦1,875.00
    """
    unit = compute_unit_cost(task_type, duration_days)
    multiplier = TARGETING_MULTIPLIERS.get(targeting_type, Decimal("1.00"))
    return unit * multiplier
