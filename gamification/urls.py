from django.urls import path
from .views import (
    NextBeeGamificationLSSOLogin,
    JoinCampaignView,
    AddStepsView,
    CampaignStatusView,
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
    path('campaigns/<uuid:campaign_id>/join/', JoinCampaignView.as_view(), name='join-campaign'),
    path('campaigns/<uuid:campaign_id>/add-steps/', AddStepsView.as_view(), name='add-steps'),
    path('campaigns/<uuid:campaign_id>/status/', CampaignStatusView.as_view(), name='campaign-status'),
    path("get-member-points-summary", GetMemberPointsSummary.as_view(), name="get_member_points_summary"),
]
