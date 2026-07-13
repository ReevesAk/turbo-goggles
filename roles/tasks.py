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

import rest_framework.serializers as s
from drf_spectacular.utils import extend_schema, OpenApiParameter, inline_serializer
from drf_spectacular.types import OpenApiTypes

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
    RewardRuleSerializer,
    RewardRuleCreateSerializer,
    RewardRuleUpdateSerializer,
    RewardTierCreateSerializer,
    RewardTierUpdateSerializer,
)
from accounts.models import User, UserNotification
from gamification.models import (
    StepCampaignModel,
    StepSessionModel,
    StreakChallenge,
    RewardRule,
    RewardTier,
)
from permissions import IsTaskAdminOrSuperAdmin, IsAdAdminOrSuperAdmin
from security import encrypt, decrypt
from commons import Messaging

logger = logging.getLogger(__name__)


@extend_schema(
    summary="[Admin] Create a step count campaign",
    tags=["Tasks"],
    description="Creates a new step count campaign and notifies all users who have completed the survey. Returns the created campaign's details.",
    request=StepCampaignSerializer,
    responses={
        201: inline_serializer(
            "CreateStepCampaignResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "data": s.DictField(),
            },
        ),
        400: inline_serializer(
            "CreateStepCampaignError",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class CreateStepCampaign(generics.GenericAPIView):
    """
    CreateStepCampaign is the POST request handler that allows a Task Admin
    to create a new step count campaign.
    """

    serializer_class = StepCampaignSerializer
    permission_classes = [IsAuthenticated, IsTaskAdminOrSuperAdmin]

    def post(self, request, *args, **kwargs):
        logger.info("Request to start step count campaign.")

        decrypted_payload = decrypt(request.data)
        serializer = self.get_serializer(data=decrypted_payload)
        if not serializer.is_valid(raise_exception=True):
            return Response(
                data=encrypt({"status": "fail", "message": serializer.errors}),
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


@extend_schema(
    summary="List all step count campaigns",
    tags=["Tasks"],
    description="Returns all step count campaigns ordered by creation date. Results are cached for 10 minutes.",
    responses={
        200: inline_serializer(
            "GetAllStepCampaignsResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "data": s.ListField(),
            },
        ),
    },
)
class GetAllStepCampaigns(generics.ListAPIView):
    """
    GetAllStepCampaigns is the GET request handler that allows a Task Admin
    to retrieve all step count campaigns.
    """

    serializer_class = StepCampaignListSerializer
    permission_classes = [IsAuthenticated]
    queryset = StepCampaignModel.objects.all().order_by("-created_at")

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


@extend_schema(
    summary="[Admin] Get a single step campaign with participants",
    tags=["Tasks"],
    description="Retrieves full details for a specific step count campaign, including a list of all participating users.",
    responses={
        200: inline_serializer(
            "GetSingleStepCampaignResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "data": s.DictField(),
            },
        ),
        404: inline_serializer(
            "GetSingleStepCampaignNotFound", fields={"detail": s.CharField()}
        ),
    },
)
class GetSingleStepCampaign(generics.RetrieveAPIView):
    """
    GetSingleStepCampaign is the GET request handler that allows a Task Admin
    to retrieve a specific step campaign along with participating users.
    """

    serializer_class = StepCampaignDetailSerializer
    permission_classes = [IsAuthenticated]

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


@extend_schema(
    summary="[Admin] List all campaigns with participant details",
    tags=["Tasks"],
    description="Returns all step count campaigns alongside their enrolled participants. Results are cached for 10 minutes.",
    responses={
        200: inline_serializer(
            "CampaignParticipantListResponse",
            fields={
                "success": s.BooleanField(),
                "message": s.CharField(),
                "data": s.ListField(),
            },
        ),
    },
)
class CampaignParticipantListView(generics.ListAPIView):
    serializer_class = CampaignWithParticipantsSerializer
    permission_classes = [IsAuthenticated, IsTaskAdminOrSuperAdmin]

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


@extend_schema(
    summary="[Admin] Send a newsletter to users",
    tags=["Tasks"],
    description="Sends a newsletter email to the specified list of recipients. Requires Task Admin or Super Admin permission.",
    request=SendNewsletterSerializer,
    responses={
        201: inline_serializer(
            "SendNewsLetterResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "data": s.DictField(),
            },
        ),
        400: inline_serializer(
            "SendNewsLetterError",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class SendNewsLetter(generics.GenericAPIView):
    """
    SendNewsLetter is the POST request handler that allows a Task Admin
    to send newsletters to users.
    """

    serializer_class = SendNewsletterSerializer
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


@extend_schema(
    summary="[Admin] Create an in-app task (streak challenge)",
    tags=["Tasks"],
    description="Creates a new in-app streak challenge task. Requires Ad Admin or Super Admin permission.",
    request=InAppTaskCreateSerializer,
    responses={
        201: inline_serializer(
            "CreateInAppTaskResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "data": s.DictField(),
            },
        ),
        400: inline_serializer(
            "CreateInAppTaskError",
            fields={"status": s.CharField(), "errors": s.DictField()},
        ),
    },
)
class CreateInAppTaskView(generics.GenericAPIView):
    """POST /v1/roles/tasks/in-app/create/ — create a new in-app task."""

    permission_classes = [IsAuthenticated, IsAdAdminOrSuperAdmin]

    def post(self, request):
        payload = decrypt(request.data)
        serializer = InAppTaskCreateSerializer(data=payload)
        if not serializer.is_valid():
            return Response(
                data=encrypt({"status": "fail", "errors": serializer.errors}),
                status=status.HTTP_400_BAD_REQUEST,
            )

        task = serializer.save(created_by=request.user)
        logger.info("In-app task '%s' created by %s", task.name, request.user.email)

        return Response(
            data=encrypt(
                {
                    "status": "success",
                    "message": "Task created successfully.",
                    "data": InAppTaskSerializer(task).data,
                }
            ),
            status=status.HTTP_201_CREATED,
        )


@extend_schema(
    summary="[Admin] List in-app tasks with optional status filter",
    tags=["Tasks"],
    description="Returns all in-app streak challenge tasks. Optionally filter by status: active, inactive, or cancelled.",
    parameters=[
        OpenApiParameter(
            name="status",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            description="Filter by task status: active, inactive, or cancelled",
            required=False,
        ),
    ],
    responses={
        200: inline_serializer(
            "ListInAppTasksResponse",
            fields={
                "status": s.CharField(),
                "total": s.IntegerField(),
                "data": s.ListField(),
            },
        ),
    },
)
class ListInAppTasksView(generics.GenericAPIView):
    """
    GET /v1/roles/tasks/in-app/?status=active|inactive|cancelled
    Returns all in-app tasks, optionally filtered by status.
    """

    permission_classes = [IsAuthenticated, IsAdAdminOrSuperAdmin]

    def get(self, request):
        status_filter = request.query_params.get("status")
        now = timezone.now()

        qs = StreakChallenge.objects.all().order_by("-created_at")

        if status_filter == "active":
            qs = qs.filter(
                is_cancelled=False,
                is_active=True,
                is_paused=False,
                start_date__lte=now,
                end_date__gte=now,
            )
        elif status_filter == "inactive":
            # not yet started, expired, or paused — anything not active and not cancelled
            qs = qs.exclude(is_cancelled=True).exclude(
                is_active=True,
                is_paused=False,
                start_date__lte=now,
                end_date__gte=now,
            )
        elif status_filter == "cancelled":
            qs = qs.filter(is_cancelled=True)

        data = InAppTaskSerializer(qs, many=True).data
        return Response(
            data=encrypt({"status": "success", "total": qs.count(), "data": data}),
            status=status.HTTP_200_OK,
        )


@extend_schema(
    summary="[Admin] Get a single in-app task with stats",
    tags=["Tasks"],
    description="Retrieves full details for a specific in-app streak challenge, including total rewards distributed and participant count.",
    responses={
        200: inline_serializer(
            "InAppTaskDetailResponse",
            fields={
                "status": s.CharField(),
                "stats": s.DictField(),
                "data": s.DictField(),
            },
        ),
        404: inline_serializer(
            "InAppTaskDetailNotFound",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class InAppTaskDetailView(generics.GenericAPIView):
    """GET /v1/roles/tasks/in-app/<task_id>/ — retrieve a single in-app task with stats."""

    permission_classes = [IsAuthenticated, IsAdAdminOrSuperAdmin]

    def get(self, request, task_id):
        from gamification.models import UserStreak

        try:
            task = StreakChallenge.objects.get(id=task_id)
        except StreakChallenge.DoesNotExist:
            return Response(
                data=encrypt({"status": "fail", "message": "Task not found."}),
                status=status.HTTP_404_NOT_FOUND,
            )

        completed_count = UserStreak.objects.filter(
            challenge=task, reward_issued=True
        ).count()
        total_rewards_distributed = completed_count * task.reward_points
        participants = UserStreak.objects.filter(challenge=task).count()

        return Response(
            data=encrypt(
                {
                    "status": "success",
                    "stats": {
                        "total_rewards_distributed": total_rewards_distributed,
                        "participants": participants,
                    },
                    "data": InAppTaskSerializer(task).data,
                }
            ),
            status=status.HTTP_200_OK,
        )


@extend_schema(
    summary="[Admin] Update or cancel an in-app task",
    tags=["Tasks"],
    description="Partially updates an in-app streak challenge task. Can be used to edit fields, pause, or cancel the task.",
    request=InAppTaskUpdateSerializer,
    responses={
        200: inline_serializer(
            "UpdateInAppTaskResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "data": s.DictField(),
            },
        ),
        400: inline_serializer(
            "UpdateInAppTaskError",
            fields={"status": s.CharField(), "errors": s.DictField()},
        ),
        404: inline_serializer(
            "UpdateInAppTaskNotFound",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class UpdateInAppTaskView(generics.GenericAPIView):
    """PATCH /v1/roles/tasks/in-app/<task_id>/update/ — edit, pause, or cancel a task."""

    permission_classes = [IsAuthenticated, IsAdAdminOrSuperAdmin]

    def patch(self, request, task_id):
        try:
            task = StreakChallenge.objects.get(id=task_id)
        except StreakChallenge.DoesNotExist:
            return Response(
                data=encrypt({"status": "fail", "message": "Task not found."}),
                status=status.HTTP_404_NOT_FOUND,
            )

        payload = decrypt(request.data)
        serializer = InAppTaskUpdateSerializer(task, data=payload, partial=True)
        if not serializer.is_valid():
            return Response(
                data=encrypt({"status": "fail", "errors": serializer.errors}),
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer.save()
        logger.info("In-app task '%s' updated by %s", task.name, request.user.email)

        return Response(
            data=encrypt(
                {
                    "status": "success",
                    "message": "Task updated successfully.",
                    "data": InAppTaskSerializer(task).data,
                }
            ),
            status=status.HTTP_200_OK,
        )


@extend_schema(
    summary="[Admin] Create a PicaPoints reward rule",
    tags=["Tasks"],
    description="Creates a new reward rule for a PicaPoints mission category (e.g. airtime purchase, KYC upgrade). Value bands are added separately via the tier endpoints.",
    request=RewardRuleCreateSerializer,
    responses={
        201: inline_serializer(
            "CreateRewardRuleResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "data": s.DictField(),
            },
        ),
        400: inline_serializer(
            "CreateRewardRuleError",
            fields={"status": s.CharField(), "errors": s.DictField()},
        ),
    },
)
class CreateRewardRuleView(generics.GenericAPIView):
    """POST /v1/roles/tasks/in-app/rewards/create/ — create a new PicaPoints reward rule."""

    permission_classes = [IsAuthenticated, IsAdAdminOrSuperAdmin]

    def post(self, request):
        payload = decrypt(request.data)
        serializer = RewardRuleCreateSerializer(data=payload)
        if not serializer.is_valid():
            return Response(
                data=encrypt({"status": "fail", "errors": serializer.errors}),
                status=status.HTTP_400_BAD_REQUEST,
            )

        rule = serializer.save(created_by=request.user)
        logger.info("RewardRule '%s' created by %s", rule.source, request.user.email)

        return Response(
            data=encrypt(
                {
                    "status": "success",
                    "message": "Reward rule created successfully.",
                    "data": RewardRuleSerializer(rule).data,
                }
            ),
            status=status.HTTP_201_CREATED,
        )


@extend_schema(
    summary="List all PicaPoints reward rules",
    tags=["Tasks"],
    description="Returns all PicaPoints reward rules with their value-banded tiers.",
    responses={
        200: inline_serializer(
            "ListRewardRulesResponse",
            fields={
                "status": s.CharField(),
                "total": s.IntegerField(),
                "data": s.ListField(),
            },
        ),
    },
)
class ListRewardRulesView(generics.GenericAPIView):
    """GET /v1/roles/tasks/in-app/rewards/ — list all reward rules."""

    permission_classes = [IsAuthenticated, IsAdAdminOrSuperAdmin]

    def get(self, request):
        rules = RewardRule.objects.all().prefetch_related("tiers").order_by("source")
        data = RewardRuleSerializer(rules, many=True).data
        return Response(
            data=encrypt({"status": "success", "total": rules.count(), "data": data}),
            status=status.HTTP_200_OK,
        )


@extend_schema(
    summary="[Admin] Get a single PicaPoints reward rule",
    tags=["Tasks"],
    description="Retrieves a single PicaPoints reward rule with its value-banded tiers.",
    responses={
        200: inline_serializer(
            "RewardRuleDetailResponse",
            fields={"status": s.CharField(), "data": s.DictField()},
        ),
        404: inline_serializer(
            "RewardRuleDetailNotFound",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class RewardRuleDetailView(generics.GenericAPIView):
    """GET /v1/roles/tasks/in-app/rewards/<rule_id>/ — retrieve a single reward rule."""

    permission_classes = [IsAuthenticated, IsAdAdminOrSuperAdmin]

    def get(self, request, rule_id):
        try:
            rule = RewardRule.objects.prefetch_related("tiers").get(id=rule_id)
        except RewardRule.DoesNotExist:
            return Response(
                data=encrypt({"status": "fail", "message": "Reward rule not found."}),
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            data=encrypt(
                {"status": "success", "data": RewardRuleSerializer(rule).data}
            ),
            status=status.HTTP_200_OK,
        )


@extend_schema(
    summary="[Admin] Update a PicaPoints reward rule",
    tags=["Tasks"],
    description="Partially updates a PicaPoints reward rule — edit caps, toggle active state, or mark one-time-only.",
    request=RewardRuleUpdateSerializer,
    responses={
        200: inline_serializer(
            "UpdateRewardRuleResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "data": s.DictField(),
            },
        ),
        400: inline_serializer(
            "UpdateRewardRuleError",
            fields={"status": s.CharField(), "errors": s.DictField()},
        ),
        404: inline_serializer(
            "UpdateRewardRuleNotFound",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class UpdateRewardRuleView(generics.GenericAPIView):
    """PATCH /v1/roles/tasks/in-app/rewards/<rule_id>/update/ — edit a reward rule."""

    permission_classes = [IsAuthenticated, IsAdAdminOrSuperAdmin]

    def patch(self, request, rule_id):
        try:
            rule = RewardRule.objects.get(id=rule_id)
        except RewardRule.DoesNotExist:
            return Response(
                data=encrypt({"status": "fail", "message": "Reward rule not found."}),
                status=status.HTTP_404_NOT_FOUND,
            )

        payload = decrypt(request.data)
        serializer = RewardRuleUpdateSerializer(rule, data=payload, partial=True)
        if not serializer.is_valid():
            return Response(
                data=encrypt({"status": "fail", "errors": serializer.errors}),
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer.save()
        logger.info("RewardRule '%s' updated by %s", rule.source, request.user.email)

        return Response(
            data=encrypt(
                {
                    "status": "success",
                    "message": "Reward rule updated successfully.",
                    "data": RewardRuleSerializer(rule).data,
                }
            ),
            status=status.HTTP_200_OK,
        )


@extend_schema(
    summary="[Admin] Add a value-band tier to a reward rule",
    tags=["Tasks"],
    description="Adds a new value band (e.g. ₦500-999 → 5 points) to an existing PicaPoints reward rule.",
    request=RewardTierCreateSerializer,
    responses={
        201: inline_serializer(
            "CreateRewardTierResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "data": s.DictField(),
            },
        ),
        400: inline_serializer(
            "CreateRewardTierError",
            fields={"status": s.CharField(), "errors": s.DictField()},
        ),
        404: inline_serializer(
            "CreateRewardTierNotFound",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class CreateRewardTierView(generics.GenericAPIView):
    """POST /v1/roles/tasks/in-app/rewards/<rule_id>/tiers/create/ — add a value band."""

    permission_classes = [IsAuthenticated, IsAdAdminOrSuperAdmin]

    def post(self, request, rule_id):
        try:
            rule = RewardRule.objects.get(id=rule_id)
        except RewardRule.DoesNotExist:
            return Response(
                data=encrypt({"status": "fail", "message": "Reward rule not found."}),
                status=status.HTTP_404_NOT_FOUND,
            )

        payload = decrypt(request.data)
        serializer = RewardTierCreateSerializer(data=payload)
        if not serializer.is_valid():
            return Response(
                data=encrypt({"status": "fail", "errors": serializer.errors}),
                status=status.HTTP_400_BAD_REQUEST,
            )

        tier = serializer.save(rule=rule)
        logger.info(
            "RewardTier added to '%s' (%s-%s → %spts) by %s",
            rule.source,
            tier.min_value,
            tier.max_value,
            tier.points,
            request.user.email,
        )

        return Response(
            data=encrypt(
                {
                    "status": "success",
                    "message": "Reward tier added successfully.",
                    "data": RewardRuleSerializer(rule).data,
                }
            ),
            status=status.HTTP_201_CREATED,
        )


@extend_schema(
    summary="[Admin] Update or delete a reward tier",
    tags=["Tasks"],
    description="Partially updates a value band on a PicaPoints reward rule.",
    request=RewardTierUpdateSerializer,
    responses={
        200: inline_serializer(
            "UpdateRewardTierResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "data": s.DictField(),
            },
        ),
        400: inline_serializer(
            "UpdateRewardTierError",
            fields={"status": s.CharField(), "errors": s.DictField()},
        ),
        404: inline_serializer(
            "UpdateRewardTierNotFound",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class UpdateRewardTierView(generics.GenericAPIView):
    """PATCH /v1/roles/tasks/in-app/rewards/tiers/<tier_id>/update/ — edit a value band.
    DELETE on the same route removes the tier entirely."""

    permission_classes = [IsAuthenticated, IsAdAdminOrSuperAdmin]

    def patch(self, request, tier_id):
        try:
            tier = RewardTier.objects.select_related("rule").get(id=tier_id)
        except RewardTier.DoesNotExist:
            return Response(
                data=encrypt({"status": "fail", "message": "Reward tier not found."}),
                status=status.HTTP_404_NOT_FOUND,
            )

        payload = decrypt(request.data)
        serializer = RewardTierUpdateSerializer(tier, data=payload, partial=True)
        if not serializer.is_valid():
            return Response(
                data=encrypt({"status": "fail", "errors": serializer.errors}),
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer.save()
        logger.info("RewardTier %s updated by %s", tier_id, request.user.email)

        return Response(
            data=encrypt(
                {
                    "status": "success",
                    "message": "Reward tier updated successfully.",
                    "data": RewardRuleSerializer(tier.rule).data,
                }
            ),
            status=status.HTTP_200_OK,
        )

    def delete(self, request, tier_id):
        try:
            tier = RewardTier.objects.select_related("rule").get(id=tier_id)
        except RewardTier.DoesNotExist:
            return Response(
                data=encrypt({"status": "fail", "message": "Reward tier not found."}),
                status=status.HTTP_404_NOT_FOUND,
            )

        rule = tier.rule
        tier.delete()
        logger.info("RewardTier %s deleted by %s", tier_id, request.user.email)

        return Response(
            data=encrypt(
                {
                    "status": "success",
                    "message": "Reward tier deleted successfully.",
                    "data": RewardRuleSerializer(rule).data,
                }
            ),
            status=status.HTTP_200_OK,
        )
