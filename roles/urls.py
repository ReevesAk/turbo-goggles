from django.urls import path
from .views import (
    RegisterSuperAdmin,
    CreateOtherAdmin,
    UpdateAdminRole,
    ListAdmin,
    GetAllCustomers,
    DeleteAdmin,
    JobApplications,
    JobApplicationList,
    JobApplicationDetail,
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


urlpatterns = [
    path("register-super-admin/", RegisterSuperAdmin.as_view(), name="resgiter_admin"),
    path("create-new-admin/", CreateOtherAdmin.as_view(), name="create_new_admin"),
    path("update-admin-role/", UpdateAdminRole.as_view(), name="update_admin_role"),
    path("list-admin-users/", ListAdmin.as_view(), name="list_admin_users"),
    path("get-all-customers/", GetAllCustomers.as_view(), name="get_all_customers"),
    path("delete-admin/", DeleteAdmin.as_view(), name="delete_admin_users"),
    # Gamification Tasks endpoints.
    path("task/assign", AssignTask.as_view(), name="assign_task"),
    path(
        "task/get-single-task/<uuid:task_id>/",
        GetSingleTask.as_view(),
        name="get_single_task",
    ),
    path("task/get-all-tasks/", GetAllTasks.as_view(), name="get_all_tasks"),
    path("task/update/", UpdateUserTask.as_view(), name="update_task"),
    path(
        "task/get-all-submitted/",
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
        "career/get-applications/",
        JobApplicationList.as_view(),
        name="application-list",
    ),
    path(
        "career/applications/<str:email>/",
        JobApplicationDetail.as_view(),
        name="application-detail",
    ),
]
