FOLLOWERS = (
    ("Below 100", "Below 100"),
    ("100-500", "100 - 500"),
    ("500-1,000", "500 - 1,000"),
    ("1,000-5,000", "1,000 - 5,000"),
    ("5,000-10,000", "5,000 - 10,000"),
    ("10,000+", "10,000 - above"),
)

BENEFICIARIES = (
    ("16-25", "16-25"),
    ("26-35", "26-35"),
    ("35-50", "35-50"),
    ("50-above", "50-above"),
)

SEX = (
    ("Male", "Male"),
    ("Female", "Female"),
    ("Prefer not to say", "Prefer not to say"),
)

RELIGION = (
    ("Christian", "Christian"),
    ("Muslim", "Muslim"),
    ("Prefer not to say", "Prefer not to say"),
)

# Kept in sync with Points.get_user_tier() in gamification/points.py by hand.
LEVELS = [
    {"title": "Starter", "min_points": 0},
    {"title": "Explorer", "min_points": 700},
    {"title": "Challenger", "min_points": 1500},
    {"title": "Influencer", "min_points": 3000},
    {"title": "Champion", "min_points": 6000},
    {"title": "Elite", "min_points": 10000},
    {"title": "Legend", "min_points": 18000},
]
