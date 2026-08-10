from accounts.models import User
from user_profile.choices import LEVELS

TIER_ORDER = [lvl["title"] for lvl in LEVELS]


def eligible_members(
    *,
    gender=None,
    age_bracket=None,
    state=None,
    min_tier=None,
    exclude_verified=False,
    location_perimeter=None,
    states=None,
    cities=None,
):
    """
    Returns the queryset of has_done_survey members matching every given
    filter. Any filter left as None/blank is skipped entirely, so calling
    this with no arguments returns the same has_done_survey pool that gets
    notified today.
    """
    qs = User.objects.filter(has_done_survey=True, is_active=True, is_deleted=False)

    if gender and gender != "all":
        # MemberSurvey.sex is stored as "Male"/"Female"; target values are
        # lowercase (TARGET_GENDER_CHOICES) - iexact handles the mismatch.
        qs = qs.filter(social_profile__sex__iexact=gender)

    if age_bracket:
        qs = qs.filter(social_profile__age_bracket__iexact=age_bracket)

    if state:
        qs = qs.filter(state__iexact=state)

    if min_tier:
        try:
            idx = TIER_ORDER.index(min_tier)
        except ValueError:
            idx = 0
        qs = qs.filter(level__in=TIER_ORDER[idx:])

    if exclude_verified:
        qs = qs.filter(is_bvn_verified=False, is_nin_verified=False)

    # UGC-style location targeting (location_perimeter + states/cities) is a
    # separate axis from the flat `state` filter above - only one is ever
    # passed by a given caller.
    if location_perimeter == "state" and states:
        qs = qs.filter(state__in=states)
    elif location_perimeter == "cities" and cities:
        qs = qs.filter(city__in=cities)

    return qs
