from django.urls import path

from .views import ChatView, SessionHistoryView, SessionListView

urlpatterns = [
    path("chat/", ChatView.as_view(), name="ai-support-chat"),
    path("sessions/", SessionListView.as_view(), name="ai-support-sessions"),
    path("sessions/<uuid:session_id>/", SessionHistoryView.as_view(), name="ai-support-session-detail"),
]
