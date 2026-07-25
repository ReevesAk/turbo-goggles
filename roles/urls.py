from django.urls import path

from .views import (
    RegisterSuperAdmin,
    AddAdmin,
    AdAdminContd,
    AddRoleToAdmin,
    GetProfileImage,
    RemoveAdminRole,
    DisableAdminrole,
    EnableAdminrole,
    GetAllAdminUsers,
    DeleteAdmin,
    VerifiedUsersCount,
    VerifiedBrandAdsCount,
    VerifiedPartnersCount,
    LoginAdmin,
    SwitchRoles,
    AddProduct,
    AddAddress,
    SetAdminPin,
    GetAllAdminActivites,
    GetAllAppActivites,
    GetSingleAdminActivity,
    GetAllSingleAdminUserActivity,
    AdminTypesListView,
    GetAllWalletAdminUsers,
    GetAllAdminUsersTypes,
    GetAllWalletStatus,
    ActivityTitleListView,
    AdminForgotPin,
    PinVerifyOTP,
    ResetPin,
    AdminDashboardDataView,
    IncomeActivityDashboardView,
    CashInVsCashOutChartView,
    ServicesBreakdownView,
    CustomerInsightView,
    AlertAndRiskView,
    AllTransactionsView,
    GamificationPicapointsOverviewView,
    TaskInsightView,
    DemographicBreakdownView,
    PendingSettlementListView,
    TransactionDetailView,
    ReconciliationDifferencesListView,
    ReconciliationDifferenceDetailView,
    DuplicateTransactionsListView,
    DuplicateTransactionDetailView,
    FraudAlertsListView,
    MessageThirdPartyView,
    CancelPendingTransactionView,
    StaffEmailVerifyOTP,
    StaffForgotPassword,
    StaffPasswordResendOTP,
    StaffResetPassword,
    CreateKnowledgeBaseView,
    AdminKnowledgeBaseDetailView,
    AdminKnowledgeBaseListView,
    KnowledgeBaseListView,
    KnowledgeBaseDetailView,
    GamificationDashboardView,
)

from .tasks import (
    CreateStepCampaign,
    GetAllStepCampaigns,
    GetSingleStepCampaign,
    SendNewsLetter,
    CampaignParticipantListView,
    CreateInAppTaskView,
    ListInAppTasksView,
    InAppTaskDetailView,
    UpdateInAppTaskView,
    CreateRewardRuleView,
    ListRewardRulesView,
    RewardRuleDetailView,
    UpdateRewardRuleView,
    CreateRewardTierView,
    UpdateRewardTierView,
)
from .wallets import (
    GetallWalletUsers,
    WalletSearch,
    ChangeWalletStatusView,
    UserKYCListView,
    UpgradeToTier3Wallet,
    RequestCorporateAddressVerification,
    SubmitCorporateTo9PSB,
)
from .treasury import (
    GetAllTreasuryAccounts,
    TreasuryAccountSearch,
    ChangeTreasuryAccountStatusView,
)

from .partners import (
    GetAllPartnersUsers,
    RestrictPartnerAccountView,
    AdminViewPartnerServiceList,
    PartnerSearch,
    PendingCommissionServiceList,
    SetPartnerServiceCommission,
)
from .brand import (
    RestrictBrandAdAccountView,
    GetAllBrandAdUsers,
    AdStatsView,
    ListAllCampaignsAdminView,
    ListBrandSubmissionsAdminView,
    PendingSubmissionsAdminView,
    ReviewTaskSubmissionAdminView,
    BrandTaskListAdminView,
    BrandTaskDetailAdminView,
    BoostTaskPointsView,
)
from .streaks import (
    ListPointConfigsView,
    UpdatePointConfigView,
    CreateStreakChallengeView,
    ListStreakChallengesView,
    UpdateStreakChallengeView,
    StreakChallengeLeaderboardAdminView,
)
from .members import (
    AllMembersView,
    ListHandleChangeRequestsView,
    ReviewHandleChangeRequestView,
)
from adverts.views import GetBrandAdDetails
from user_profile.views import ProfileImage
from waitlist.views import (
    AdminWaitlistListView,
    AdminWaitlistDeleteDuplicatesView,
    WeeklyTopReferrersView,
    BulkDeleteWaitlistUsers,
)

app_name = "roles"


urlpatterns = [
    path("register-super-admin", RegisterSuperAdmin.as_view(), name="resgiter_admin"),
    path("add-admin", AddAdmin.as_view(), name="create_new_admin"),
    path("add-admin-contd/<str:user_id>/", AdAdminContd.as_view(), name="admin-update"),
    path("admin-login", LoginAdmin.as_view(), name="admin_login"),
    path("admin-profile-img", ProfileImage.as_view(), name="profile_img"),
    path("get-profile-image", GetProfileImage.as_view(), name="get_profile_image"),
    path("list-admin-types", AdminTypesListView.as_view(), name="list_admin_types"),
    path("add-role-to-admin", AddRoleToAdmin.as_view(), name="add_role_to_admin"),
    path(
        "remove-role-from-admin",
        RemoveAdminRole.as_view(),
        name="remove_role_from_admin",
    ),
    # Authorization management endpoints.
    path("admin-forgot-pin", AdminForgotPin.as_view(), name="admin_forgot_pin"),
    path("verify-pin-otp", PinVerifyOTP.as_view(), name="verify_pin_otp"),
    path("reset-pin", ResetPin.as_view(), name="reset_pin"),
    path(
        "staff-forgot-password",
        StaffForgotPassword.as_view(),
        name="staff_forgot_password",
    ),
    path(
        "staff-password-resend-otp",
        StaffPasswordResendOTP.as_view(),
        name="staff_password_resend_otp",
    ),
    path(
        "staff-email-verify-otp",
        StaffEmailVerifyOTP.as_view(),
        name="staff_email_verify_otp",
    ),
    path(
        "staff-reset-password",
        StaffResetPassword.as_view(),
        name="staff_reset_password",
    ),
    path("list-admin-users", GetAllAdminUsers.as_view(), name="list_admin_users"),
    path(
        "list-admin-user-types",
        GetAllAdminUsersTypes.as_view(),
        name="list_admin_user_types",
    ),
    path("disable-admin", DisableAdminrole.as_view(), name="disable_admin"),
    path("re-enable-admin", EnableAdminrole.as_view(), name="enable_admin"),
    path("delete-admin", DeleteAdmin.as_view(), name="delete_admin_users"),
    path("set-admin-pin", SetAdminPin.as_view(), name="set_admin_pin"),
    path("verified-users", VerifiedUsersCount.as_view(), name="verified-users-list"),
    path(
        "verified-brandAds", VerifiedBrandAdsCount.as_view(), name="verified-ads-list"
    ),
    path(
        "wallet-admins-list",
        GetAllWalletAdminUsers.as_view(),
        name="wallet_admins_list",
    ),
    path(
        "verified-partners",
        VerifiedPartnersCount.as_view(),
        name="verified-partners-list",
    ),
    path("list-kyc-users", UserKYCListView.as_view(), name="list_kyc_users"),
    # Activity Logs Endpoints.
    path(
        "activity/get-all-app-activities",
        GetAllAppActivites.as_view(),
        name="get_all_app_activities",
    ),
    path(
        "activity/get-all-admin-activities",
        GetAllAdminActivites.as_view(),
        name="get_all_admin-activities",
    ),
    path(
        "activity/<uuid:activity_id>/single-activity",
        GetSingleAdminActivity.as_view(),
        name="single_activity",
    ),
    path(
        "activity/<str:email>/single-get-all",
        GetAllSingleAdminUserActivity.as_view(),
        name="single_get_all",
    ),
    path("activity/title-list", ActivityTitleListView.as_view(), name="title-list"),
    # Gamification Tasks endpoints.
    path(
        "tasks/campaigns/create",
        CreateStepCampaign.as_view(),
        name="create-step-campaign",
    ),
    path(
        "tasks/campaigns/all",
        GetAllStepCampaigns.as_view(),
        name="get-all-step-campaigns",
    ),
    path(
        "tasks/campaigns/<uuid:campaign_id>/get",
        GetSingleStepCampaign.as_view(),
        name="get-single-step-campaign",
    ),
    path(
        "tasks/campaigns/with-participants",
        CampaignParticipantListView.as_view(),
        name="campaigns-with-participants",
    ),
    path(
        "tasks/send-newsletter",
        SendNewsLetter.as_view(),
        name="send_newsletter",
    ),
    # In-app task admin endpoints
    path("tasks/in-app/", ListInAppTasksView.as_view(), name="in_app_task_list"),
    path(
        "tasks/in-app/create/", CreateInAppTaskView.as_view(), name="in_app_task_create"
    ),
    path(
        "tasks/in-app/<uuid:task_id>/",
        InAppTaskDetailView.as_view(),
        name="in_app_task_detail",
    ),
    path(
        "tasks/in-app/<uuid:task_id>/update/",
        UpdateInAppTaskView.as_view(),
        name="in_app_task_update",
    ),
    # PicaPoints reward rule admin endpoints
    path(
        "tasks/in-app/rewards/",
        ListRewardRulesView.as_view(),
        name="reward_rule_list",
    ),
    path(
        "tasks/in-app/rewards/create/",
        CreateRewardRuleView.as_view(),
        name="reward_rule_create",
    ),
    path(
        "tasks/in-app/rewards/<uuid:rule_id>/",
        RewardRuleDetailView.as_view(),
        name="reward_rule_detail",
    ),
    path(
        "tasks/in-app/rewards/<uuid:rule_id>/update/",
        UpdateRewardRuleView.as_view(),
        name="reward_rule_update",
    ),
    path(
        "tasks/in-app/rewards/<uuid:rule_id>/tiers/create/",
        CreateRewardTierView.as_view(),
        name="reward_tier_create",
    ),
    path(
        "tasks/in-app/rewards/tiers/<uuid:tier_id>/update/",
        UpdateRewardTierView.as_view(),
        name="reward_tier_update",
    ),
    path("switch-roles", SwitchRoles.as_view(), name="switch_roles"),
    # Partner endpoints.
    path(
        "partners/get-all-partners",
        GetAllPartnersUsers.as_view(),
        name="get_all_partners",
    ),
    path(
        "partners/<int:partner_id>/restrict-partner",
        RestrictPartnerAccountView.as_view(),
        name="restrict_partner",
    ),
    path(
        "partners/<str:partner_email>/get-partner-services",
        AdminViewPartnerServiceList.as_view(),
        name="view_partners_services",
    ),
    path("partners/<str:search_term>/", PartnerSearch.as_view(), name="partner_search"),
    path(
        "partners/pending-commission-services",
        PendingCommissionServiceList.as_view(),
        name="pending_commission_services",
    ),
    path(
        "partners/service/<int:service_id>/set-commission",
        SetPartnerServiceCommission.as_view(),
        name="set_service_commission",
    ),
    # BrandAd endpoints.
    path(
        "brands/<int:brand_id>/restrict-brandAd",
        RestrictBrandAdAccountView.as_view(),
        name="restrict_brandAd",
    ),
    path(
        "brands/get-all-brandAds",
        GetAllBrandAdUsers.as_view(),
        name="get_all_brandAds",
    ),
    path(
        "brand/ad-profile/<str:email>/", GetBrandAdDetails.as_view(), name="ad_profile"
    ),
    path(
        "brand/ad-stats-view/<int:user_id>/",
        AdStatsView.as_view(),
        name="ad-stats_view",
    ),
    path(
        "brands/campaigns/",
        ListAllCampaignsAdminView.as_view(),
        name="list_all_campaigns",
    ),
    path(
        "brands/submissions/",
        ListBrandSubmissionsAdminView.as_view(),
        name="list_brand_submissions",
    ),
    path(
        "tasks/pending/",
        PendingSubmissionsAdminView.as_view(),
        name="admin_pending_submissions",
    ),
    path(
        "tasks/<uuid:submission_id>/review/",
        ReviewTaskSubmissionAdminView.as_view(),
        name="admin_review_submission",
    ),
    # Brand task admin endpoints
    path("brands/tasks/", BrandTaskListAdminView.as_view(), name="brand_task_list"),
    path(
        "brands/tasks/<int:ad_id>/",
        BrandTaskDetailAdminView.as_view(),
        name="brand_task_detail",
    ),
    path(
        "brands/tasks/<int:ad_id>/boost-points/",
        BoostTaskPointsView.as_view(),
        name="brand_task_boost_points",
    ),
    # Streak challenge admin endpoints
    path("streaks/", ListStreakChallengesView.as_view(), name="admin_streak_list"),
    path(
        "streaks/create/",
        CreateStreakChallengeView.as_view(),
        name="admin_streak_create",
    ),
    path(
        "streaks/<uuid:challenge_id>/update/",
        UpdateStreakChallengeView.as_view(),
        name="admin_streak_update",
    ),
    path(
        "streaks/<uuid:challenge_id>/leaderboard/",
        StreakChallengeLeaderboardAdminView.as_view(),
        name="admin_streak_leaderboard",
    ),
    # PointConfig admin endpoints
    path("points/", ListPointConfigsView.as_view(), name="admin_point_configs"),
    path(
        "points/<str:key>/",
        UpdatePointConfigView.as_view(),
        name="admin_point_config_update",
    ),
    # Fmcg admin endpoints
    path("fmcg/add-product", AddProduct.as_view(), name="add_product"),
    path("fmcg/add-address", AddAddress.as_view(), name="add_address"),
    # Wallet endpoints.
    path(
        "wallets/upgrade-from-tier2-to-tier3",
        UpgradeToTier3Wallet.as_view(),
        name="upgrade_from_tier2_to_tier3",
    ),
    path(
        "wallets/corporate/request-address-verification",
        RequestCorporateAddressVerification.as_view(),
        name="corporate_request_address_verification",
    ),
    path(
        "wallets/corporate/submit-to-9psb",
        SubmitCorporateTo9PSB.as_view(),
        name="corporate_submit_to_9psb",
    ),
    path(
        "wallets/get-all-wallet-users",
        GetallWalletUsers.as_view(),
        name="get_all_wallet_users",
    ),
    path("get-wallet-status", GetAllWalletStatus.as_view(), name="get_wallet_status"),
    path("wallets/<str:search_term>/", WalletSearch.as_view(), name="wallet_search"),
    path(
        "wallets/change-wallet-status",
        ChangeWalletStatusView.as_view(),
        name="change_wallet_status",
    ),
    path(
        "admin-dashboard-data",
        AdminDashboardDataView.as_view(),
        name="admin_dashboard_data",
    ),
    path(
        "gamification-dashboard",
        GamificationDashboardView.as_view(),
        name="gamification_dashboard",
    ),
    path(
        "income-activity-dashboard",
        IncomeActivityDashboardView.as_view(),
        name="income_activity_dashboard",
    ),
    path(
        "cash-in-vs-cash-out-chart",
        CashInVsCashOutChartView.as_view(),
        name="cash_in_vs_cash_out_chart",
    ),
    path(
        "services-breakdown",
        ServicesBreakdownView.as_view(),
        name="services_breakdown",
    ),
    path(
        "customer-insight",
        CustomerInsightView.as_view(),
        name="customer_insight",
    ),
    path(
        "alert-and-risk",
        AlertAndRiskView.as_view(),
        name="alert_and_risk",
    ),
    path(
        "all-transactions",
        AllTransactionsView.as_view(),
        name="all_transactions",
    ),
    path(
        "picapoints-overview",
        GamificationPicapointsOverviewView.as_view(),
        name="picapoints_overview",
    ),
    path(
        "task-insight",
        TaskInsightView.as_view(),
        name="task_insight",
    ),
    path(
        "demographic-breakdown",
        DemographicBreakdownView.as_view(),
        name="demographic_breakdown",
    ),
    # Alert and Risk drill-downs.
    path(
        "alert-and-risk/pending-settlement",
        PendingSettlementListView.as_view(),
        name="pending_settlement_list",
    ),
    path(
        "alert-and-risk/pending-settlement/<str:transaction_id>",
        TransactionDetailView.as_view(),
        name="transaction_detail",
    ),
    path(
        "alert-and-risk/reconciliation-differences",
        ReconciliationDifferencesListView.as_view(),
        name="reconciliation_differences_list",
    ),
    path(
        "alert-and-risk/reconciliation-differences/<str:transaction_id>",
        ReconciliationDifferenceDetailView.as_view(),
        name="reconciliation_difference_detail",
    ),
    path(
        "alert-and-risk/duplicate-transactions",
        DuplicateTransactionsListView.as_view(),
        name="duplicate_transactions_list",
    ),
    path(
        "alert-and-risk/duplicate-transactions/<str:transaction_id>",
        DuplicateTransactionDetailView.as_view(),
        name="duplicate_transaction_detail",
    ),
    path(
        "alert-and-risk/duplicate-transactions/<str:transaction_id>/cancel-pending",
        CancelPendingTransactionView.as_view(),
        name="cancel_pending_transaction",
    ),
    path(
        "alert-and-risk/fraud-alerts",
        FraudAlertsListView.as_view(),
        name="fraud_alerts_list",
    ),
    path(
        "alert-and-risk/message-third-party",
        MessageThirdPartyView.as_view(),
        name="message_third_party",
    ),
    # Treasury account admin endpoints.
    path(
        "treasury/get-all-accounts",
        GetAllTreasuryAccounts.as_view(),
        name="get_all_treasury_accounts",
    ),
    path(
        "treasury/change-account-status",
        ChangeTreasuryAccountStatusView.as_view(),
        name="change_treasury_account_status",
    ),
    path(
        "treasury/<str:search_term>/",
        TreasuryAccountSearch.as_view(),
        name="treasury_account_search",
    ),
    # User Knowledge base endpoints.
    path(
        "knowledge-base/", KnowledgeBaseListView.as_view(), name="knowledge-base-list"
    ),
    path(
        "knowledge-base/<int:id>/",
        KnowledgeBaseDetailView.as_view(),
        name="knowledge-base-detail",
    ),
    # Admin Knowledge base endpoints.
    path("knowledge-base/create", CreateKnowledgeBaseView.as_view(), name="kb_create"),
    path("knowledge-base/all", AdminKnowledgeBaseListView.as_view(), name="kb_list"),
    path(
        "knowledge-base/<int:pk>/",
        AdminKnowledgeBaseDetailView.as_view(),
        name="kb_detail",
    ),
    # Member endpoints.
    path("members/all", AllMembersView.as_view(), name="all_members"),
    # Handle change request admin endpoints.
    path(
        "members/handle-change-requests/",
        ListHandleChangeRequestsView.as_view(),
        name="handle_change_requests",
    ),
    path(
        "members/handle-change-requests/<int:pk>/review/",
        ReviewHandleChangeRequestView.as_view(),
        name="review_handle_change",
    ),
    # Waitlist endpoints.
    path(
        "waitlist/all-users",
        AdminWaitlistListView.as_view(),
        name="admin_waitlist_users",
    ),
    path(
        "waitlist/delete-duplicates/",
        AdminWaitlistDeleteDuplicatesView.as_view(),
        name="admin-waitlist-delete-duplicates",
    ),
    path(
        "waitlist/weekly-top-referrers",
        WeeklyTopReferrersView.as_view(),
        name="weekly_top_referrers",
    ),
    path(
        "waitlist/bulk-delete/",
        BulkDeleteWaitlistUsers.as_view(),
        name="waitlist-bulk-delete",
    ),
]
