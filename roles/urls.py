from django.urls import path
from .views import (
    RegisterSuperAdmin,
    AddAdmin,
    AdAdminContd,
    UpdateAdminRole,
    DisableAdminrole,
    GetAllAdminUsers,
    GetAllCustomers,
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

from .partners import GetAllPartnersUsers, RestrictPartnerAccount


urlpatterns = [
    path("register-super-admin", RegisterSuperAdmin.as_view(), name="resgiter_admin"),
    path("add-admin", AddAdmin.as_view(), name="create_new_admin"),
    path("add-admin-contd/<str:user_id>/", AdAdminContd.as_view(), name="admin-update"),
    path("admin-login", LoginAdmin.as_view(), name="admin_login"),
    path("update-admin-role", UpdateAdminRole.as_view(), name="update_admin_role"),
    path("list-admin-users", GetAllAdminUsers.as_view(), name="list_admin_users"),
    path("disable-admin", DisableAdminrole.as_view(), name="disable_admin"),
    path("get-all-customers", GetAllCustomers.as_view(), name="get_all_customers"),
    path("delete-admin", DeleteAdmin.as_view(), name="delete_admin_users"),
    path("verified-users", VerifiedUsersCount.as_view(), name="verified-users-list"),
    path(
        "verified-brandAds", VerifiedBrandAdsCount.as_view(), name="verified-ads-list"
    ),
    path(
        "verified-partners",
        VerifiedPartnersCount.as_view(),
        name="verified-partners-list",
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
    path("career/applications/<int:pk>/delete/", DeleteJobApplication.as_view(), name="delete-application"),
    path("switch-roles", SwitchRoles.as_view(), name="switch_roles"),
    # Partner endpoints.
    path("partner-admin/get-all-partners", GetAllPartnersUsers.as_view(), name="get_all_partners"),
    path("partner-admin/restrict-partner", RestrictPartnerAccount.as_view(), name="restrict_partner")
]
