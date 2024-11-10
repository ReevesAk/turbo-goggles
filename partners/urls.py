from django.urls import path
from .views import (
    CreatePartner,
    ListAllPartners,
    CreatePartnerService,
    UpdatePartnerService,
    DeletePartnerService,
    PartnerServiceList,
    AllPartnersServiceList,
    GetPartnerDetails,
    UpdatePartnerProfile,
    VerifyCACView,
    PartnerServicePhotosList,
    PartnerServiceGymTrainersPhotosList,
    PartnerServiceDetailView,
)

urlpatterns = [
    path("create-partners", CreatePartner.as_view(), name="create_partners"),
    path("partner-profile", GetPartnerDetails.as_view(), name="get_partner_profile"),
    path("verify-cac", VerifyCACView.as_view(), name="verify_cac"),
    path("list-all-partners", ListAllPartners.as_view(), name="all_partners"),
    path(
        "partner-service",
        CreatePartnerService.as_view(),
        name="create_partner_service",
    ),
    path(
        "update-service/<int:service_id>/",
        UpdatePartnerService.as_view(),
        name="update_service",
    ),
    path(
        "delete-service/<int:id>/",
        DeletePartnerService.as_view(),
        name="delete_service",
    ),
    path(
        "list-partner-service",
        PartnerServiceList.as_view(),
        name="partner-service",
    ),
    path(
        "all-partners-services/<str:business>/",
        AllPartnersServiceList.as_view(),
        name="all_partner_service",
    ),
    path(
        "service/<int:service_id>/",
        PartnerServiceDetailView.as_view(),
        name="service-detail",
    ),
    path("profile-update", UpdatePartnerProfile.as_view(), name="update_profile"),
    path("partner-photos", PartnerServicePhotosList.as_view(), name="partner_photos"),
    path(
        "gym-trainer-photos",
        PartnerServiceGymTrainersPhotosList.as_view(),
        name="gym_trainer_photos",
    ),
]
