from django.urls import path

from .views import (
    JoinBetaUserWaitList,
    WaitlistDashboardView,
)

app_name = "waitlist"


urlpatterns = [
    path("join-betauser-waitlist", JoinBetaUserWaitList.as_view(), name="join_betauser_waitlist"),
    path("waitlist-dashboard", WaitlistDashboardView.as_view(), name="waitlist_dashboard"),
]
