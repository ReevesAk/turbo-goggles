from django.urls import path

from .views import (
    JobList,
    CreateJob,
    JobDetail,
    UpdateJob,
    DeleteJob,
    SubmitJobApplication,
    JobApplicationList,
    JobApplicationDetail,
    DeleteJobApplication,
)

app_name = "web"

urlpatterns = [
    path("jobs/", JobList.as_view(), name="job-list"),
    path("jobs/create/", CreateJob.as_view(), name="job-create"),
    path("jobs/<int:id>/", JobDetail.as_view(), name="job-detail"),
    path("jobs/<int:id>/update/", UpdateJob.as_view(), name="job-update"),
    path("jobs/<int:id>/delete/", DeleteJob.as_view(), name="job-delete"),
    path("career/submit-application", SubmitJobApplication.as_view(), name="submit_application"),
    # Applications endpoints.
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
]
