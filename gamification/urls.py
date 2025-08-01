from django.urls import path
from .views import (
    NextBeeGamificationLSSOLogin,
    JoinOrAddStepsView,
    GetMemberPointsSummary
)
from roles.tasks import (
    GetAllStepCampaigns,
    GetSingleStepCampaign
)


app_name = "gamification"

urlpatterns = [
    path(
        "nextbee-gamification-sso-login",
        NextBeeGamificationLSSOLogin.as_view(),
        name="nextbee_gamification_sso_login",
    ),
    path(
        "campaigns/all",
        GetAllStepCampaigns.as_view(),
        name="get-all-step-campaigns",
    ),
    path(
        "campaigns/<uuid:campaign_id>/",
        GetSingleStepCampaign.as_view(),
        name="get-single-step-campaign",
    ),
    path(
        "join-or-add-steps",
        JoinOrAddStepsView.as_view(),
        name="join_or_add_steps",
    ),
    path("get-member-points-summary", GetMemberPointsSummary.as_view(), name="get_member_points_summary"),
]
