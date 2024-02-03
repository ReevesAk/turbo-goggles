from django.urls import path

from .views import (
    GetUserDetails,
    UpdateUserProfile,
    MemberUserSwitch,
    ChangePassword,
    ProfileImage,
    DeleteUser,
    WebhookView,
)

urlpatterns = [
    path("profile-img/", ProfileImage.as_view(), name="profile_img"),
    path("get-user-profile/", GetUserDetails.as_view(), name="get_user_profile"),
    path("update-user/", UpdateUserProfile.as_view(), name="update_user"),
    path("upgrade-to-member/", MemberUserSwitch.as_view(), name="upgrade_to_member"),
    path("change-password/", ChangePassword.as_view(), name="change_password"),
    path("webhook/", WebhookView.as_view(), name="webhook_view"),
    path("delete/", DeleteUser.as_view(), name="delete"),
]
