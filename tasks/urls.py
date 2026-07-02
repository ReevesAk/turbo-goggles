from django.urls import path

from .views import (
    MySubmissionsView,
    MyTrustScoreView,
    SocialTaskListView,
    BrandTaskFeedView,
    CompleteWebviewTaskView,
    MyBrandSubmissionsView,
    ScanStoreVisitQRView,
    StoreVisitArriveView,
    StoreVisitConfirmOTPView,
    StoreVisitNoShowView,
    StoreVisitSendOTPView,
    SubmitBrandTaskView,
    SubmitSurveyTaskView,
)

urlpatterns = [
    path("brand/feed/", BrandTaskFeedView.as_view(), name="task-feed"),
    path("brand/submit/", SubmitBrandTaskView.as_view(), name="brand-task-submit"),
    path("brand/webview/complete/", CompleteWebviewTaskView.as_view(), name="task-webview-complete"),
    path("brand/survey/submit/", SubmitSurveyTaskView.as_view(), name="brand-survey-submit"),
    # Store visit flow
    path("brand/store-visit/arrive/", StoreVisitArriveView.as_view(), name="store-visit-arrive"),
    path("brand/store-visit/no-show/", StoreVisitNoShowView.as_view(), name="store-visit-no-show"),
    path("brand/store-visit/send-otp/", StoreVisitSendOTPView.as_view(), name="store-visit-send-otp"),
    path("brand/store-visit/confirm-otp/", StoreVisitConfirmOTPView.as_view(), name="store-visit-confirm-otp"),
    path("brand/store-visit/scan/", ScanStoreVisitQRView.as_view(), name="store-visit-qr-scan"),
    path("brand/my-submissions/", MyBrandSubmissionsView.as_view(), name="task-my-submissions"),
    path("submissions/", MySubmissionsView.as_view(), name="my-submissions"),
    path("trust-score/", MyTrustScoreView.as_view(), name="trust-score"),
    path("", SocialTaskListView.as_view(), name="task-list"),
]
