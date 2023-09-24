from .models import User
from rest_framework_simplejwt.tokens import RefreshToken

user = User


def create_jwt_pair_for_user(user: user):
    refresh = RefreshToken.for_user(user)

    tokens = {"access": str(refresh.access_token), "refresh": str(refresh)}

    return tokens
