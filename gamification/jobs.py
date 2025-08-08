from accounts.models import User
from .points import Points


user = User


def refresh_all_users_points():
    for user in User.objects.all():
        Points.refresh_user_points(user)
