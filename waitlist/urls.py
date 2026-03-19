from django.urls import path

from .views import (
    JoinBetaUserWaitList
)

app_name = "waitlist"


urlpatterns = [
    path("join-betauser-waitlist", JoinBetaUserWaitList.as_view(), name="join_betauser_waitlist"),
]