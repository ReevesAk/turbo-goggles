from django.urls import path
from .views import (  # SubmitActivityImageView,
    ActiveStreakChallengesView,
    AddStepsView,
    AdminUGCDetailView,
    AdminUGCListCreateView,
    AdminUGCSubmissionsListView,
    AdminUGCSubmissionStatsView,
    BrandUGCDetailView,
    BrandUGCListCreateView,
    CampaignStatusView,
    GenerateWalkToEarnReferralCodeView,
    GetMemberPointsSummary,
    JoinCampaignView,
    JoinStreakChallengeView,
    MyStreakHistoryView,
    MyStreakProgressView,
    MyReferralStatusView,
    NextBeeGamificationLSSOLogin,
    PointsLeaderboardView,
    RedeemPointsToWallet,
    ReviewUGCSubmissionAdminView,
    StreakLeaderboardView,
    UGCDetailView,
    UGCLeaderboardView,
    UGCTaskSubmitView,
    UGCTaskWithSubmissionView,
    UserUGCProgressView,
    UserUGCTaskSubmissionsView,
)

from roles.tasks import GetAllStepCampaigns, GetSingleStepCampaign

app_name = "gamification"

urlpatterns = [
    # ==========================================
    # NextBee Gamification SSO
    # ==========================================
    path(
        "nextbee-gamification-sso-login",
        NextBeeGamificationLSSOLogin.as_view(),
        name="nextbee_gamification_sso_login",
    ),
    # ==========================================
    # Step Campaign Endpoints
    # ==========================================
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
        "campaigns/<uuid:campaign_id>/join/",
        JoinCampaignView.as_view(),
        name="join-campaign",
    ),
    path(
        "campaigns/<uuid:campaign_id>/add-steps/",
        AddStepsView.as_view(),
        name="add-steps",
    ),
    path(
        "campaigns/<uuid:campaign_id>/status/",
        CampaignStatusView.as_view(),
        name="campaign-status",
    ),
    # ==========================================
    # Streak Challenge Endpoints
    # ==========================================
    path("streaks/", ActiveStreakChallengesView.as_view(), name="streak-list"),
    path(
        "streaks/<uuid:challenge_id>/join/",
        JoinStreakChallengeView.as_view(),
        name="streak-join",
    ),
    path(
        "streaks/my-progress/",
        MyStreakProgressView.as_view(),
        name="streak-my-progress",
    ),
    path(
        "streaks/<uuid:challenge_id>/leaderboard/",
        StreakLeaderboardView.as_view(),
        name="streak-leaderboard",
    ),
    path("streaks/history/", MyStreakHistoryView.as_view(), name="streak-history"),
    # ==========================================
    # Points & Leaderboard Endpoints
    # ==========================================
    path(
        "get-member-points-summary",
        GetMemberPointsSummary.as_view(),
        name="get_member_points_summary",
    ),
    path("leaderboard/", PointsLeaderboardView.as_view(), name="points-leaderboard"),
    path(
        "redeem-points/", RedeemPointsToWallet.as_view(), name="redeem-points-to-wallet"
    ),
    # ==========================================
    # Referral Endpoints
    # ==========================================
    path(
        "referrals/my-status/",
        MyReferralStatusView.as_view(),
        name="referral-my-status",
    ),
    path(
        "referrals/walk-to-earn-code/",
        GenerateWalkToEarnReferralCodeView.as_view(),
        name="referral-generate-walk-to-earn-code",
    ),
    # ==========================================
    # User Generated Content (UGC) Endpoints
    # ==========================================
    # Public endpoint - accessible to any authenticated user
    # GET /v1/ugc/tasks/<id>/ - Get detailed view of a specific task (cached for 5min)
    # Browsing UGC tasks now happens via the unified feed (tasks/brand/feed/),
    # not a standalone list here - the mobile client never called this list.
    path("ugc/tasks/<uuid:id>/", UGCDetailView.as_view(), name="ugc-detail"),
    # Brand endpoints - accessible to BrandAd and BrandAdAdmin roles
    # GET /v1/ugc/brand/tasks/ - List tasks owned by the authenticated brand
    # POST /v1/ugc/brand/tasks/ - Create a new UGC task (requires wallet/card payment)
    # GET /v1/ugc/brand/tasks/<id>/ - Retrieve a specific task owned by the brand
    # PATCH /v1/ugc/brand/tasks/<id>/ - Update a task owned by the brand
    # DELETE /v1/ugc/brand/tasks/<id>/ - Delete a task owned by the brand (only if slots_filled = 0)
    path(
        "ugc/brand/tasks/",
        BrandUGCListCreateView.as_view(),
        name="brand-ugc-list-create",
    ),
    path(
        "ugc/brand/tasks/<uuid:id>/",
        BrandUGCDetailView.as_view(),
        name="brand-ugc-detail",
    ),
    # Admin endpoints - accessible only to SuperAdmin users
    # GET /v1/ugc/admin/tasks/ - List all UGC tasks across all brands
    # POST /v1/ugc/admin/tasks/ - Create a task on behalf of a brand (no payment required)
    # GET /v1/ugc/admin/tasks/<id>/ - Retrieve any task by ID
    # PATCH /v1/ugc/admin/tasks/<id>/ - Update any task by ID
    # DELETE /v1/ugc/admin/tasks/<id>/ - Delete any task by ID (only if slots_filled = 0)
    path(
        "ugc/admin/tasks/",
        AdminUGCListCreateView.as_view(),
        name="admin-ugc-list-create",
    ),
    path(
        "ugc/admin/tasks/<uuid:id>/",
        AdminUGCDetailView.as_view(),
        name="admin-ugc-detail",
    ),
    path(
        "ugc/tasks/<uuid:id>/with-submission/",
        UGCTaskWithSubmissionView.as_view(),
        name="task-with-submission",
    ),
    path(
        "ugc/submissions/",
        UserUGCTaskSubmissionsView.as_view(),
        name="user-submissions",
    ),
    path("ugc/submit/", UGCTaskSubmitView.as_view(), name="submit-task"),
    path("ugc/progress/", UserUGCProgressView.as_view(), name="user-progress"),
    path("ugc/leaderboard/", UGCLeaderboardView.as_view(), name="leaderboard"),
    # Admin endpoints (read-only)
    path(
        "ugc/admin/submissions/",
        AdminUGCSubmissionsListView.as_view(),
        name="admin-submissions",
    ),
    path(
        "ugc/admin/submissions/<uuid:id>/review/",
        ReviewUGCSubmissionAdminView.as_view(),
        name="admin-review-submission",
    ),
    path(
        "ugc/admin/stats/",
        AdminUGCSubmissionStatsView.as_view(),
        name="admin-stats",
    ),
    # path("submit-activity-image", SubmitActivityImageView.as_view(), name="submit_activity_image"),
]
