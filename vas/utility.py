from accounts.models import UserNotification
from roles.models import ActivityModel


def create_notification(user, title, message):
    UserNotification.objects.create(
        user=user,
        title=title,
        message=message
    )


def create_activity(user, title, description):
    ActivityModel.objects.create(
        user=user,
        title=title,
        description=description,
    )
