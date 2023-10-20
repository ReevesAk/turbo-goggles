from django.urls import path

from .views import GetUserDetails, UpdateUserProfile, UpgradeToMember, ChangePassword

urlpatterns = [
    path("get-user-profile/", GetUserDetails.as_view(), name="get_user_profile"),
    path("update-user/", UpdateUserProfile.as_view(), name="update_user"),
    path("upgrade-to-member/", UpgradeToMember.as_view(), name="upgrade_to_member"),
    path("change-password/", ChangePassword.as_view(), name="change_password"),
]
