from django.urls import path

from .views import (
    MySubmissionsView,
    MyTrustScoreView,
    SocialTaskListView,
    UnifiedSubmitView,
    BrandTaskFeedView,
    CompleteWebviewTaskView,
    MyBrandSubmissionsView,
    SubmitBrandTaskView,
)

urlpatterns = [
    # Unified feed and submission
    path("feed/", BrandTaskFeedView.as_view(), name="task-feed"),
    path("submit/", UnifiedSubmitView.as_view(), name="task-submit-unified"),
    path("webview/complete/", CompleteWebviewTaskView.as_view(), name="task-webview-complete"),
    path("my-submissions/", MyBrandSubmissionsView.as_view(), name="task-my-submissions"),

    # Legacy endpoints (keep for backwards compatibility)
    path("brand/feed/", BrandTaskFeedView.as_view(), name="brand-task-feed"),
    path("brand/submit/", SubmitBrandTaskView.as_view(), name="brand-task-submit"),
    path("brand/webview/complete/", CompleteWebviewTaskView.as_view(), name="brand-webview-complete"),
    path("brand/my-submissions/", MyBrandSubmissionsView.as_view(), name="brand-my-submissions"),
    path("submissions/", MySubmissionsView.as_view(), name="my-submissions"),
    path("trust-score/", MyTrustScoreView.as_view(), name="trust-score"),
    path("", SocialTaskListView.as_view(), name="task-list"),
]
