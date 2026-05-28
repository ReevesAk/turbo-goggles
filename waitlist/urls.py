from django.urls import path

from .views import (
    JoinBetaUserWaitList,
    WaitlistDashboardView,
    PublicWaitlistListView,
    VerifyWaitlistOTP,
)

app_name = "waitlist"


urlpatterns = [
    path(
        "join-betauser-waitlist",
        JoinBetaUserWaitList.as_view(),
        name="join_betauser_waitlist",
    ),
    path(
        "waitlist-dashboard", WaitlistDashboardView.as_view(), name="waitlist_dashboard"
    ),
    path("waitlist-users", PublicWaitlistListView.as_view(), name="waitlist_users"),
    path("verify-otp", VerifyWaitlistOTP.as_view(), name="verify_waitlist_otp"),
]
