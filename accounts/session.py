"""Single active session enforcement for admin / support (web dashboard) users.

Regular app users (User/Member/Partner/BrandAd) are unaffected — they stay
multi-device. For every other (privileged) role, each successful login mints a
fresh session id, records it on the user as `active_session_id`, and revokes the
previous session's refresh tokens. A login on a second machine therefore signs
the first one out: its access token's `sid` claim no longer matches the user's
current `active_session_id`, so SessionAwareJWTAuthentication rejects it.
"""

import uuid

from django.utils import timezone

from accounts.models import USER_CATEGORY_CHOICES

# Roles that are ordinary app users — allowed on as many devices as they like.
NON_PRIVILEGED_ROLES = {"User", "Member", "Partner", "BrandAd"}

# Everything else (SuperAdmin, the *Admin roles, Manager/Moderator/Agent) is a
# web-dashboard account and gets one active session at a time.
SINGLE_SESSION_ROLES = frozenset(
    role for role, _ in USER_CATEGORY_CHOICES if role not in NON_PRIVILEGED_ROLES
)


def enforces_single_session(user) -> bool:
    """True when `user`'s role is limited to one active session."""
    return bool(user and user.active_role in SINGLE_SESSION_ROLES)


def rotate_session(user) -> uuid.UUID:
    """Start a fresh session for `user` and revoke the previous one.

    Returns the new session id; the caller embeds it in the JWT as the `sid`
    claim. Must be called *before* the new refresh token is minted, otherwise
    the freshly created OutstandingToken gets blacklisted along with the old
    ones.
    """
    from rest_framework_simplejwt.token_blacklist.models import (
        BlacklistedToken,
        OutstandingToken,
    )

    session_id = uuid.uuid4()

    # Only tokens that could still be used are worth blacklisting; expired ones
    # are already dead. Keeps the loop bounded for a long-lived admin account.
    stale = OutstandingToken.objects.filter(
        user=user, expires_at__gt=timezone.now()
    )
    for token in stale:
        BlacklistedToken.objects.get_or_create(token=token)

    user.active_session_id = session_id
    user.save(update_fields=["active_session_id"])
    return session_id
