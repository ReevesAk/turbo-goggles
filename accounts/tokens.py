from .models import User
from rest_framework_simplejwt.tokens import RefreshToken

from .session import enforces_single_session, rotate_session

user = User


def create_jwt_pair_for_user(user: user):
    # Privileged (admin/support) roles get a single active session: rotating it
    # here revokes the previous login before the new refresh token is minted.
    session_id = rotate_session(user) if enforces_single_session(user) else None

    refresh = RefreshToken.for_user(user)
    if session_id is not None:
        refresh["sid"] = str(session_id)

    access = refresh.access_token
    access["aud"] = "picadailys"
    access["iss"] = "https://api.picadailys.com/"
    tokens = {"access": str(access), "refresh": str(refresh)}

    return tokens
