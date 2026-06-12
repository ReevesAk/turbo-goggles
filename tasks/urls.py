from django.urls import path

from .views import (
    MySubmissionsView,
    MyTrustScoreView,
    PendingReviewListView,
    ReviewSubmissionView,
    SocialProfileView,
    SocialTaskListView,
    SubmitTaskView,
)

urlpatterns = [
    path("profile/", SocialProfileView.as_view(), name="social-profile"),
    path("", SocialTaskListView.as_view(), name="task-list"),
    path("submit/", SubmitTaskView.as_view(), name="task-submit"),
    path("submissions/", MySubmissionsView.as_view(), name="my-submissions"),
    path("trust-score/", MyTrustScoreView.as_view(), name="trust-score"),
    # Admin
    path("admin/pending/", PendingReviewListView.as_view(), name="pending-review"),
    path("admin/review/<uuid:submission_id>/", ReviewSubmissionView.as_view(), name="review-submission"),
]
