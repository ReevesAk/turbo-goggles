import logging

from django.shortcuts import get_object_or_404
from django.db.models import Prefetch

# Third party imports.
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication

from drf_spectacular.utils import extend_schema

# In project imports.
from gamification.serializers import (
    StepCampaignSerializer,
    StepCampaignListSerializer,
    StepCampaignDetailSerializer,
    CampaignWithParticipantsSerializer,
)
from accounts.models import User, UserNotification
from gamification.models import StepCampaignModel, StepSessionModel
from permissions import IsTaskAdminOrSuperAdmin, IsSuperAdmin
from security import encrypt, decrypt


logger = logging.getLogger(__name__)


class CreateStepCampaign(generics.GenericAPIView):
    """
    CreateStepCampaign is the POST request handler that allows a Task Admin
    to create a new step count campaign.
    """

    serializer_class = StepCampaignSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, IsTaskAdminOrSuperAdmin]

    def post(self, request, *args, **kwargs):
        logger.info("Request to start step count campaign.")

        decrypted_payload = decrypt(request.data)
        serializer = self.get_serializer(data=decrypted_payload)
        if not serializer.is_valid(raise_exception=True):
            return Response(
                data=encrypt({"status": "error", "message": serializer.errors}),
                status=status.HTTP_400_BAD_REQUEST,
            )
        logger.info("Serializer validated successfully.")
        campaign = serializer.save()

        response_data = {
            "status": "Success",
            "message": "Campaign created successfully.",
            "data": {
                "campaign_id": str(campaign.campaign_id),
                "name": campaign.name,
                "description": campaign.description,
                "duration": str(campaign.duration),
                "reward_points": campaign.reward_points,
                "step_target": campaign.step_target,
                "time_limit": str(campaign.time_limit),
            },
        }
        logger.info(
            f"Campaign started successfully, campaign_id: {response_data['data']['campaign_id']}"
        )

        survey_users = User.objects.filter(has_done_survey=True)
        for user in survey_users:
            UserNotification.objects.create(
                user=user,
                title="New Step Count Campaign",
                message=f"A new step count campaign '{serializer.validated_data['name']}' has been assigned to you.",
            )

        return Response(data=encrypt(response_data), status=status.HTTP_201_CREATED)


class GetAllStepCampaigns(generics.ListAPIView):
    """
    GetAllStepCampaigns is the GET request handler that allows a Task Admin
    to retrieve all step count campaigns.
    """

    serializer_class = StepCampaignListSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    queryset = StepCampaignModel.objects.all().order_by("-created_at")

    @extend_schema(
        description="Retrieve all step count campaigns",
        responses={200: {"description": "List of step campaigns"}},
    )
    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)

        response_data = {
            "status": "Success",
            "message": "Step campaigns retrieved successfully.",
            "data": serializer.data,
        }
        return Response(data=encrypt(response_data), status=status.HTTP_200_OK)


class GetSingleStepCampaign(generics.RetrieveAPIView):
    """
    GetSingleStepCampaign is the GET request handler that allows a Task Admin
    to retrieve a specific step campaign along with participating users.
    """

    serializer_class = StepCampaignDetailSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    @extend_schema(
        description="Retrieve a specific step campaign and its participants",
        responses={200: {"description": "Step campaign details with participants"}},
    )
    def retrieve(self, request, *args, **kwargs):
        campaign_id = kwargs.get("campaign_id")
        campaign = get_object_or_404(StepCampaignModel, id=campaign_id)
        serializer = self.get_serializer(campaign)

        response_data = {
            "status": "Success",
            "message": "Step campaign retrieved successfully.",
            "data": serializer.data,
        }
        return Response(data=encrypt(response_data), status=status.HTTP_200_OK)


class CampaignParticipantListView(generics.ListAPIView):
    serializer_class = CampaignWithParticipantsSerializer

    def get_queryset(self):
        return StepCampaignModel.objects.prefetch_related(
            Prefetch(
                "sessions", queryset=StepSessionModel.objects.select_related("user")
            )
        )

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)

        return Response(
            data=encrypt(
                {
                    "success": True,
                    "message": "Campaigns retrieved successfully",
                    "data": serializer.data,
                }
            ),
            status=status.HTTP_200_OK,
        )
