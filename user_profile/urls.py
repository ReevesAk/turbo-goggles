from django.urls import path

from .views import (
    SwitchToBrandAd,
    SwitchToPartner,
    SwitchToUser,
    GetUserDetails,
    UpdateUserProfile,
    MemberUserSwitch,
    PostMemberSurvey,
    ChangePassword,
    ProfileImage,
    DeleteUser,
    ClaimMysteryBoxGift,
    OpenRewardBox,
    AddToFavourite,
    ListFavourites,
    RetrieveFavourite,
)
from .notifications import (
    GetAllNotifications,
    GetSingleNotification,
    ClearNotifications,
    MarkNotificationsAsRead,
    DeleteNotification,
)

urlpatterns = [
    path("switch-to-user/", SwitchToUser.as_view(), name="switch_to_user"),
    path("switch-to-partner/", SwitchToPartner.as_view(), name="switch_to_partner"),
    path("switch-to-brandAd/", SwitchToBrandAd.as_view(), name="switch_to_brandAd"),
    path("profile-img/", ProfileImage.as_view(), name="profile_img"),
    path("get-user-profile/", GetUserDetails.as_view(), name="get_user_profile"),
    path("update-user/", UpdateUserProfile.as_view(), name="update_user"),
    path("upgrade-to-member/", MemberUserSwitch.as_view(), name="upgrade_to_member"),
    path("member-survey/", PostMemberSurvey.as_view(), name="member_survey"),
    path("change-password/", ChangePassword.as_view(), name="change_password"),
    path("open-box/", OpenRewardBox.as_view(), name="open_box"),
    path("claim-gift/", ClaimMysteryBoxGift.as_view(), name="claim_gift"),
    path("delete/", DeleteUser.as_view(), name="delete"),
    # Notification endpoints.
    path("notification/<int:id>/get", GetSingleNotification.as_view(), name="get_ntfn"),
    path("notification/get-all", GetAllNotifications.as_view(), name="get_ntfns"),
    path(
        "notification/mark-as-read",
        MarkNotificationsAsRead.as_view(),
        name="mark_ntfn_as_read",
    ),
    path("notification/clear", ClearNotifications.as_view(), name="clear_ntfn"),
    path(
        "notification/<int:id>/delete", DeleteNotification.as_view(), name="delete_ntfn"
    ),
    # Favourites endpoints
    path("favourites/add", AddToFavourite.as_view(), name="add_favourite"),
    path("favourites/list-all", ListFavourites.as_view(), name="list_favourites"),
    path("favourites/<uuid:id>/get", RetrieveFavourite.as_view(), name="get_favourite")
]
