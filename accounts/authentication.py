"""Project authentication classes."""

from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication

from accounts.session import enforces_single_session


class SessionAwareJWTAuthentication(JWTAuthentication):
    """JWTAuthentication that also enforces one active session per privileged user.

    When an admin/support user signs in on another device, the previous token's
    `sid` claim stops matching `user.active_session_id`, and any request that
    carries it is rejected with a `session_superseded` code. The web client
    keys on that code to show a "signed out on another device" message and send
    the user back to login.

    Regular app users have no `active_session_id` and are never checked here.
    """

    def get_user(self, validated_token):
        user = super().get_user(validated_token)

        if enforces_single_session(user) and user.active_session_id is not None:
            if str(validated_token.get("sid")) != str(user.active_session_id):
                raise AuthenticationFailed(
                    {
                        "code": "session_superseded",
                        "detail": (
                            "You have been signed out because your account was "
                            "signed in on another device."
                        ),
                    },
                    code="session_superseded",
                )

        return user
