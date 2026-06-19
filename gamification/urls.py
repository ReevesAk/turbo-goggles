from django.urls import path
from .views import (
    NextBeeGamificationLSSOLogin,
    JoinCampaignView,
    AddStepsView,
    CampaignStatusView,
    ActiveStreakChallengesView,
    JoinStreakChallengeView,
    MyStreakProgressView,
    StreakLeaderboardView,
    MyStreakHistoryView,
    GetMemberPointsSummary,
    PointsLeaderboardView,
    # SubmitActivityImageView,
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
    path("campaigns/<uuid:campaign_id>/join/", JoinCampaignView.as_view(), name="join-campaign"),
    path("campaigns/<uuid:campaign_id>/add-steps/", AddStepsView.as_view(), name="add-steps"),
    path("campaigns/<uuid:campaign_id>/status/", CampaignStatusView.as_view(), name="campaign-status"),
    # Streak challenge endpoints
    path("streaks/", ActiveStreakChallengesView.as_view(), name="streak-list"),
    path("streaks/<uuid:challenge_id>/join/", JoinStreakChallengeView.as_view(), name="streak-join"),
    path("streaks/my-progress/", MyStreakProgressView.as_view(), name="streak-my-progress"),
    path("streaks/<uuid:challenge_id>/leaderboard/", StreakLeaderboardView.as_view(), name="streak-leaderboard"),
    path("streaks/history/", MyStreakHistoryView.as_view(), name="streak-history"),
    path("get-member-points-summary", GetMemberPointsSummary.as_view(), name="get_member_points_summary"),
    path("leaderboard/", PointsLeaderboardView.as_view(), name="points-leaderboard"),
    # path("submit-activity-image", SubmitActivityImageView.as_view(), name="submit_activity_image"),
]
