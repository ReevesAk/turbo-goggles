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
    StaffEmailVerifyOTP,
    StaffForgotPassword,
    StaffPasswordResendOTP,
    StaffResetPassword,
)

from .tasks import (
    CreateStepCampaign,
    GetAllStepCampaigns,
    GetSingleStepCampaign,
    SendNewsLetter,
    CampaignParticipantListView,
)
from .wallets import (
    GetallWalletUsers,
    WalletSearch,
    ChangeWalletStatusView,
    UserKYCListView,
    UpgradeToTier3Wallet,
)

from .partners import (
    GetAllPartnersUsers,
    RestrictPartnerAccountView,
    AdminViewPartnerServiceList,
    PartnerSearch,
)
from .brand import (
    RestrictBrandAdAccountView,
    GetAllBrandAdUsers,
    AdStatsView,
)
from .members import AllMembersView
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
    path("ad-profile/<str:email>/", GetBrandAdDetails.as_view(), name="ad_profile"),
    path("ad-stats-view/<int:user_id>/", AdStatsView.as_view(), name="ad-stats_view"),
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
    # Member endpoints.
    path("members/all", AllMembersView.as_view(), name="all_members"),
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
        name="waitlist-bulk-delete"
    ),
]
