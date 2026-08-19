from django.db.models import Q

from accounts.models import User
from user_profile.choices import LEVELS
from user_profile.models import MemberSurvey

TIER_ORDER = [lvl["title"] for lvl in LEVELS]

# Temporarily disabled: gender/age/state/tier/verification/location targeting
# is switched off below so eligible_members() only applies the has_done_survey
# gate. Flip this back to True to re-integrate the rest - the filter logic is
# left in place untouched, just skipped.
_APPLY_EXTRA_TARGETING_FILTERS = False


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

    NOTE: all targeting kwargs below are currently no-ops - see
    _APPLY_EXTRA_TARGETING_FILTERS. Only has_done_survey/is_active/is_deleted
    is applied for now; the rest is re-integrated by flipping that flag.
    """
    qs = User.objects.filter(has_done_survey=True, is_active=True, is_deleted=False)

    if not _APPLY_EXTRA_TARGETING_FILTERS:
        return qs

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


def filter_by_viewer_gender(qs, user, gender_field):
    """
    Filters a task queryset (CreateAd or UserGeneratedContent) down to rows
    whose gender_field targeting matches `user`'s own MemberSurvey gender.
    A task with that field blank/unset/"all" always passes. Users with no
    survey data are not filtered - missing data isn't treated as a mismatch.
    __iexact absorbs the casing difference between CreateAd's "Male"/"Female"
    and UGC's "male"/"female".
    """
    survey = MemberSurvey.objects.filter(user=user).only("sex").first()
    user_gender = survey.sex if survey else None

    if user_gender:
        gender_q = (
            Q(**{f"{gender_field}__isnull": True})
            | Q(**{gender_field: ""})
            | Q(**{f"{gender_field}__iexact": "all"})
            | Q(**{f"{gender_field}__iexact": user_gender})
        )
        qs = qs.filter(gender_q)

    return qs


def filter_ugc_by_viewer_location(qs, user):
    """
    UGC-only location filter - UserGeneratedContent.location_perimeter plus
    flat states/cities JSON lists, structurally different from CreateAd's
    related BrandLocation model (which has its own filter already, in
    tasks/views.py's BrandTaskFeedView.get_queryset).
    """
    location_q = Q(location_perimeter="nation_wide")
    if user.state:
        location_q |= Q(location_perimeter="state", states__contains=[user.state])
    if user.city:
        location_q |= Q(location_perimeter="cities", cities__contains=[user.city])
    return qs.filter(location_q)
