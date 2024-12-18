from .models import User
from rest_framework_simplejwt.tokens import RefreshToken

user = User


def create_jwt_pair_for_user(user: user):
    refresh = RefreshToken.for_user(user)

    access = refresh.access_token
    access['aud'] = 'picadailys'
    access['iss'] = 'http://167.71.174.242/api/v1/'
    tokens = {"access": str(access), "refresh": str(refresh)}

    return tokens
