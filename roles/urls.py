from django.urls import path
from .views import (
    RegisterSuperAdmin,
    AddAdmin,
    AdAdminContd,
    AddRoleToAdmin,
    RemoveAdminRole,
    DisableAdminrole,
    EnableAdminrole,
    GetAllAdminUsers,
    DeleteAdmin,
    JobApplications,
    JobApplicationList,
    JobApplicationDetail,
    DeleteJobApplication,
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
)
from .tasks import (
    AssignTask,
    GetAllTasks,
    GetSingleTask,
    UpdateUserTask,
    GetAllSubmittedTasks,
    GetSingleSubmittedTask,
    ReviewTask,
)
from .wallets import GetallWalletUsers

from .partners import GetAllPartnersUsers, RestrictPartnerAccountView
from .brand import RestrictBrandAdAccountView, GetAllBrandAdUsers
from user_profile.views import ProfileImage


urlpatterns = [
    path("register-super-admin", RegisterSuperAdmin.as_view(), name="resgiter_admin"),
    path("add-admin", AddAdmin.as_view(), name="create_new_admin"),
    path("add-admin-contd/<str:user_id>/", AdAdminContd.as_view(), name="admin-update"),
    path("admin-login", LoginAdmin.as_view(), name="admin_login"),
    path("admin-profile-img", ProfileImage.as_view(), name="profile_img"),
    path("list-admin-types", AdminTypesListView.as_view(), name="list_admin_types"),
    path("add-role-to-admin", AddRoleToAdmin.as_view(), name="add_role_to_admin"),
    path("title-list", ActivityTitleListView.as_view(), name="title-list"),
    path(
        "remove-role-from-admin",
        RemoveAdminRole.as_view(),
        name="remove_role_from_admin",
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
    # Gamification Tasks endpoints.
    path("task/assign", AssignTask.as_view(), name="assign_task"),
    path(
        "task/get-single-task/<uuid:task_id>/",
        GetSingleTask.as_view(),
        name="get_single_task",
    ),
    path("task/get-all-tasks", GetAllTasks.as_view(), name="get_all_tasks"),
    path("task/update", UpdateUserTask.as_view(), name="update_task"),
    path(
        "task/get-all-submitted",
        GetAllSubmittedTasks.as_view(),
        name="get_all_submitted",
    ),
    path(
        "task/get-single-submitted/<uuid:task_id>/",
        GetSingleSubmittedTask.as_view(),
        name="single_submited_tasks",
    ),
    path("task/review-task", ReviewTask.as_view(), name="review_task"),
    # Applications endpoints.
    path("career/job-aplication", JobApplications.as_view(), name="job_aplications"),
    path(
        "career/get-applications",
        JobApplicationList.as_view(),
        name="application-list",
    ),
    path(
        "career/applications/<str:email>/",
        JobApplicationDetail.as_view(),
        name="application-detail",
    ),
    path(
        "career/applications/<int:pk>/delete/",
        DeleteJobApplication.as_view(),
        name="delete-application",
    ),
    path("switch-roles", SwitchRoles.as_view(), name="switch_roles"),
    # Partner endpoints.
    path(
        "partner-admin/get-all-partners",
        GetAllPartnersUsers.as_view(),
        name="get_all_partners",
    ),
    path(
        "partner-admin/<int:partner_id>/restrict-partner",
        RestrictPartnerAccountView.as_view(),
        name="restrict_partner",
    ),
    # BrandAd endpoints.
    path(
        "brand-admin/<int:brand_id>/restrict-brandAd",
        RestrictBrandAdAccountView.as_view(),
        name="restrict_brandAd",
    ),
    path(
        "brand-admin/get-all-brandAds",
        GetAllBrandAdUsers.as_view(),
        name="get_all_brandAds",
    ),
    # Fmcg admin endpoints
    path("fmcg/add-product", AddProduct.as_view(), name="add_product"),
    path("fmcg/add-address", AddAddress.as_view(), name="add_address"),
    # Wallet endpoints.
    path(
        "wallet/get-all-wallet-users",
        GetallWalletUsers.as_view(),
        name="get_all_wallet_users",
    ),
    path("get-wallet-status", GetAllWalletStatus.as_view(), name="get_wallet_status"),
]
