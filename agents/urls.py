from django.urls import path

from .views import (
    AgentStatusView,
    AgentOnboardView,
    AgentWebTokenView,
    AgentMeView,
    AgentReferralsView,
    AgentWithdrawView,
)

app_name = "agents"

urlpatterns = [
    path("status/", AgentStatusView.as_view(), name="agent_status"),
    path("onboard/", AgentOnboardView.as_view(), name="agent_onboard"),
    path("web-token/", AgentWebTokenView.as_view(), name="agent_web_token"),
    path("me/", AgentMeView.as_view(), name="agent_me"),
    path("referrals/", AgentReferralsView.as_view(), name="agent_referrals"),
    path("withdraw/", AgentWithdrawView.as_view(), name="agent_withdraw"),
]
