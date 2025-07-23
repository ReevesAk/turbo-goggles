from django.urls import path
from .views import (
    NextBeeGamificationLSSOLogin,
    JoinOrAddStepsView
)

app_name = "gamification"

urlpatterns = [
    path(
        "nextbee-gamification-sso-login",
        NextBeeGamificationLSSOLogin.as_view(),
        name="nextbee_gamification_sso_login",
    ),
    path(
        "join-or-add-steps",
        JoinOrAddStepsView.as_view(),
        name="join_or_add_steps",
    ),
]
