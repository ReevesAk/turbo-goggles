from django.urls import path

from .views import (
    MySubmissionsView,
    MyTrustScoreView,
    SocialTaskListView,
    BrandTaskFeedView,
    CompleteWebviewTaskView,
    MyBrandSubmissionsView,
    SubmitBrandTaskView,
    SubmitSurveyTaskView,
)

urlpatterns = [
    path("brand/feed/", BrandTaskFeedView.as_view(), name="task-feed"),
    path("brand/submit/", SubmitBrandTaskView.as_view(), name="brand-task-submit"),
    path("brand/webview/complete/", CompleteWebviewTaskView.as_view(), name="task-webview-complete"),
    path("brand/survey/submit/", SubmitSurveyTaskView.as_view(), name="brand-survey-submit"),
    path("brand/my-submissions/", MyBrandSubmissionsView.as_view(), name="task-my-submissions"),
    path("submissions/", MySubmissionsView.as_view(), name="my-submissions"),
    path("trust-score/", MyTrustScoreView.as_view(), name="trust-score"),
    path("", SocialTaskListView.as_view(), name="task-list"),
]
