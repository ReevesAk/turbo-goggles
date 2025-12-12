from django.urls import path

from .views import (
    SubmitJobApplication,
    JobApplicationList,
    JobApplicationDetail,
    DeleteJobApplication,
)

app_name = "web"

urlpatterns = [
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
