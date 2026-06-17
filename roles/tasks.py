import logging

from django.template.loader import render_to_string
from django.shortcuts import get_object_or_404
from django.db.models import Prefetch
from django.core.cache import cache
from django.utils import timezone

# Third party imports.
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication

from drf_spectacular.utils import extend_schema

# In project imports.
from .serializers import (
    SendNewsletterSerializer,
)

from gamification.serializers import (
    StepCampaignSerializer,
    StepCampaignListSerializer,
    StepCampaignDetailSerializer,
    CampaignWithParticipantsSerializer,
    InAppTaskCreateSerializer,
    InAppTaskSerializer,
    InAppTaskUpdateSerializer,
)
from accounts.models import User, UserNotification
from gamification.models import StepCampaignModel, StepSessionModel, StreakChallenge
from permissions import IsTaskAdminOrSuperAdmin, IsAdAdminOrSuperAdmin
from security import encrypt, decrypt
from commons import Messaging

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
        UserNotification.objects.bulk_create(
            [
                UserNotification(
                    user=user,
                    title="New Step Count Campaign",
                    message=f"A new step count campaign '{serializer.validated_data['name']}' has been assigned to you.",
                )
                for user in survey_users
            ],
            batch_size=500,
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
        cache_key = "all_step_campaigns"
        cached_data = cache.get(cache_key)

        if cached_data:
            logger.info(
                "Returning cached step campaigns for user %s", request.user.email
            )
            encrypted_response = encrypt(cached_data)
            return Response(data=encrypted_response, status=status.HTTP_200_OK)

        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)

        response_data = {
            "status": "Success",
            "message": "Step campaigns retrieved successfully.",
            "data": serializer.data,
        }

        # Save to cache (short TTL)
        cache.set(cache_key, response_data, timeout=600)  # 10 minutes

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
        campaign = get_object_or_404(StepCampaignModel, campaign_id=campaign_id)
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
        cache_key = "campaigns_with_participants"
        cached_data = cache.get(cache_key)
        if cached_data:
            logger.info(
                "Returning cached campaigns with participants at %s", timezone.now()
            )
            return Response(data=encrypt(cached_data), status=status.HTTP_200_OK)

        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)

        response_data = {
            "success": True,
            "message": "Campaigns retrieved successfully",
            "data": serializer.data,
        }

        # Save to cache (short TTL)
        cache.set(cache_key, response_data, timeout=600)  # 10 minutes
        logger.info("Caching campaigns with participants at %s", timezone.now())

        return Response(
            data=encrypt(response_data),
            status=status.HTTP_200_OK,
        )


class SendNewsLetter(generics.GenericAPIView):
    """
    SendNewsLetter is the POST request handler that allows a Task Admin
    to send newsletters to users.
    """

    serializer_class = SendNewsletterSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, IsTaskAdminOrSuperAdmin]

    def post(self, request, *args, **kwargs):
        logger.info("Request to send newsletter.")

        decrypted_payload = decrypt(request.data)
        serializer = self.get_serializer(data=decrypted_payload)
        serializer.is_valid(raise_exception=True)

        logger.info("Serializer validated successfully.")

        send_to_list = serializer.validated_data["send_to"]
        title = serializer.validated_data["title"]
        content = serializer.validated_data["content"]
        volume = serializer.validated_data["volume"]

        text_content = render_to_string(
            template_name="empty_email.html",
            context={
                "custom_text": content,
                "support_email": "support@picadailys.com",
                "picadailys_phone": "02012271894  02012271895",
            },
        )

        # 🔹 Send to each recipient
        for email in send_to_list:
            Messaging.send_email(
                sender_email="notifications@picadailys.com",
                body=content,
                email=email,  # single email per send
                html_content=text_content,
                subject=title,
            )

        response_data = {
            "status": "Success",
            "message": "Newsletter sent successfully.",
            "data": {
                "volume": volume,
                "total_recipients": len(send_to_list),
                "send_to": send_to_list,
                "title": title,
                "content": content,
            },
        }

        logger.info(
            f"Newsletter sent successfully to {len(send_to_list)} recipient(s)."
        )

        return Response(data=encrypt(response_data), status=status.HTTP_201_CREATED)


class CreateInAppTaskView(generics.GenericAPIView):
    """POST /v1/roles/tasks/in-app/create/ — create a new in-app task."""

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, IsAdAdminOrSuperAdmin]

    def post(self, request):
        payload = decrypt(request.data)
        serializer = InAppTaskCreateSerializer(data=payload)
        if not serializer.is_valid():
            return Response(
                data=encrypt({"status": "error", "errors": serializer.errors}),
                status=status.HTTP_400_BAD_REQUEST,
            )

        task = serializer.save(created_by=request.user)
        logger.info("In-app task '%s' created by %s", task.name, request.user.email)

        return Response(
            data=encrypt({
                "status": "success",
                "message": "Task created successfully.",
                "data": InAppTaskSerializer(task).data,
            }),
            status=status.HTTP_201_CREATED,
        )


class ListInAppTasksView(generics.GenericAPIView):
    """
    GET /v1/roles/tasks/in-app/?status=active|scheduled|expired|cancelled
    Returns all in-app tasks, optionally filtered by status.
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, IsAdAdminOrSuperAdmin]

    def get(self, request):
        status_filter = request.query_params.get("status")
        today = timezone.now().date()

        qs = StreakChallenge.objects.all().order_by("-created_at")

        if status_filter == "active":
            qs = qs.filter(
                is_cancelled=False,
                is_active=True,
                is_paused=False,
                start_date__lte=today,
                end_date__gte=today,
            )
        elif status_filter == "scheduled":
            qs = qs.filter(is_cancelled=False, start_date__gt=today)
        elif status_filter == "expired":
            qs = qs.filter(is_cancelled=False, end_date__lt=today)
        elif status_filter == "cancelled":
            qs = qs.filter(is_cancelled=True)

        data = InAppTaskSerializer(qs, many=True).data
        return Response(
            data=encrypt({"status": "success", "total": qs.count(), "data": data}),
            status=status.HTTP_200_OK,
        )


class InAppTaskDetailView(generics.GenericAPIView):
    """GET /v1/roles/tasks/in-app/<task_id>/ — retrieve a single in-app task with stats."""

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, IsAdAdminOrSuperAdmin]

    def get(self, request, task_id):
        from gamification.models import UserStreak

        try:
            task = StreakChallenge.objects.get(id=task_id)
        except StreakChallenge.DoesNotExist:
            return Response(
                data=encrypt({"status": "error", "message": "Task not found."}),
                status=status.HTTP_404_NOT_FOUND,
            )

        completed_count = UserStreak.objects.filter(challenge=task, reward_issued=True).count()
        total_rewards_distributed = completed_count * task.reward_points
        participants = UserStreak.objects.filter(challenge=task).count()

        return Response(
            data=encrypt({
                "status": "success",
                "stats": {
                    "total_rewards_distributed": total_rewards_distributed,
                    "participants": participants,
                },
                "data": InAppTaskSerializer(task).data,
            }),
            status=status.HTTP_200_OK,
        )


class UpdateInAppTaskView(generics.GenericAPIView):
    """PATCH /v1/roles/tasks/in-app/<task_id>/update/ — edit, pause, or cancel a task."""

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, IsAdAdminOrSuperAdmin]

    def patch(self, request, task_id):
        try:
            task = StreakChallenge.objects.get(id=task_id)
        except StreakChallenge.DoesNotExist:
            return Response(
                data=encrypt({"status": "error", "message": "Task not found."}),
                status=status.HTTP_404_NOT_FOUND,
            )

        payload = decrypt(request.data)
        serializer = InAppTaskUpdateSerializer(task, data=payload, partial=True)
        if not serializer.is_valid():
            return Response(
                data=encrypt({"status": "error", "errors": serializer.errors}),
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer.save()
        logger.info("In-app task '%s' updated by %s", task.name, request.user.email)

        return Response(
            data=encrypt({
                "status": "success",
                "message": "Task updated successfully.",
                "data": InAppTaskSerializer(task).data,
            }),
            status=status.HTTP_200_OK,
        )
