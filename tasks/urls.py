from django.urls import path

from .views import (
    # Social tasks
    MySubmissionsView,
    MyTrustScoreView,
    SocialTaskListView,
    SubmitTaskView,
    # Brand campaign tasks
    BrandTaskFeedView,
    MyBrandSubmissionsView,
    SubmitBrandTaskView,
)

urlpatterns = [
    path("", SocialTaskListView.as_view(), name="task-list"),
    path("submit/", SubmitTaskView.as_view(), name="task-submit"),
    path("submissions/", MySubmissionsView.as_view(), name="my-submissions"),
    path("trust-score/", MyTrustScoreView.as_view(), name="trust-score"),

    path("brand/feed/", BrandTaskFeedView.as_view(), name="brand-task-feed"),
    path("brand/submit/", SubmitBrandTaskView.as_view(), name="brand-task-submit"),
    path("brand/my-submissions/", MyBrandSubmissionsView.as_view(), name="brand-my-submissions"),
]
