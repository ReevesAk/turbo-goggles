import logging

from django.core.cache import cache
from django.utils import timezone

import rest_framework.serializers as s
from drf_spectacular.utils import extend_schema, OpenApiParameter, inline_serializer
from drf_spectacular.types import OpenApiTypes
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.pagination import PageNumberPagination
from yaml import serializer

from adverts.models import CreateAd
from gamification.models import StreakChallenge
from security import encrypt, decrypt
from .jobs import (
    approve_brand_submission,
    approve_brand_submission_now,
    run_verification,
)
from user_profile.fcm import send_push_to_admins
from .models import BrandTaskSubmission, SocialTask, TaskSubmission, UserTrustScore
from .serializers import (
    BrandTaskFeedSerializer,
    BrandTaskSubmissionSerializer,
    CompleteWebviewTaskSerializer,
    InAppTaskFeedSerializer,
    SocialTaskSerializer,
    SubmitBrandTaskSerializer,
    SubmitTaskSerializer,
    TaskSubmissionSerializer,
    UserTrustScoreSerializer,
)

logger = logging.getLogger(__name__)


class PaginationStyle(PageNumberPagination):
    page_size = 20



@extend_schema(
    summary="List available social tasks",
    tags=["Tasks"],
    description="Returns all active social tasks that are currently available for the authenticated user to complete. Supports optional filtering by platform and task type.",
    parameters=[
        OpenApiParameter(name="platform", type=OpenApiTypes.STR, description="Filter by social platform (e.g. twitter, instagram)"),
        OpenApiParameter(name="task_type", type=OpenApiTypes.STR, description="Filter by task type (e.g. Follow, Comment, Post)"),
    ],
    responses={200: SocialTaskSerializer(many=True)},
)
class SocialTaskListView(generics.ListAPIView):
    serializer_class = SocialTaskSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = SocialTask.objects.filter(is_active=True).order_by("-created_at")
        platform = self.request.query_params.get("platform")
        task_type = self.request.query_params.get("task_type")
        if platform:
            qs = qs.filter(platform=platform)
        if task_type:
            qs = qs.filter(task_type=task_type)
        return qs

    def list(self, request, *args, **kwargs):
        qs = [t for t in self.get_queryset() if t.is_available]
        serializer = self.get_serializer(qs, many=True)
        return Response(data=encrypt({
            "status": "success",
            "message": "Tasks retrieved successfully.",
            "data": serializer.data,
        }), status=status.HTTP_200_OK)


@extend_schema(
    summary="Submit proof for a social task",
    tags=["Tasks"],
    description="Submit a screenshot URL or post URL as proof of completing a social task. A verification code is returned for Comment and Post task types.",
    request=SubmitTaskSerializer,
    responses={
        201: inline_serializer(name="SubmitTaskResponse", fields={
            "detail": s.CharField(),
            "id": s.UUIDField(),
            "verification_code": s.CharField(required=False),
            "verification_note": s.CharField(required=False),
        }),
        400: inline_serializer(name="SubmitTaskError", fields={"status": s.CharField(), "message": s.CharField()}),
    },
)
class SubmitTaskView(generics.CreateAPIView):
    serializer_class = SubmitTaskSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def create(self, request, *args, **kwargs):
        try:
            decrypted_payload = decrypt(request.data)
            if not isinstance(decrypted_payload, dict):
                raise ValueError("Decrypted payload is not a valid object.")
            user_data = {
                key: value.strip() if isinstance(value, str) else value
                for key, value in decrypted_payload.items()
            }
            serializer = self.get_serializer(data=user_data, context={"request": request})
            serializer.is_valid(raise_exception=True)
            submission = serializer.save()

            run_verification.delay(str(submission.pk))

            response_data = {
                "status": "success",
                "message": "Submission received. Verification in progress.",
                "data": {"submission_id": str(submission.pk)},
            }
            if submission.verification_code:
                response_data["data"]["verification_code"] = submission.verification_code
                response_data["data"]["verification_note"] = (
                    f"Include this code verbatim in your {submission.task.task_type.lower()}: "
                    f"{submission.verification_code}"
                )

            return Response(data=encrypt(response_data), status=status.HTTP_201_CREATED)

        except s.ValidationError as err:
            logger.warning("SubmitTaskView validation failed for user %s: %s", request.user.id, err.detail)
            return Response(
                data=encrypt({"status": "error", "message": err.detail}),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as err:
            logger.error("SubmitTaskView failed for user %s: %s", request.user.id, str(err), exc_info=True)
            return Response(
                data=encrypt({"status": "error", "message": "Submission failed. Please try again."}),
                status=status.HTTP_400_BAD_REQUEST,
            )


@extend_schema(
    summary="List my task submissions",
    tags=["Tasks"],
    description="Returns all social task submissions made by the authenticated user, including verification status and AI review results.",
    responses={200: TaskSubmissionSerializer(many=True)},
)
class MySubmissionsView(generics.ListAPIView):
    serializer_class = TaskSubmissionSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            TaskSubmission.objects.filter(user=self.request.user)
            .select_related("task", "verification")
            .order_by("-created_at")
        )

    def list(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_queryset(), many=True)
        return Response(data=encrypt({
            "status": "success",
            "message": "Submissions retrieved successfully.",
            "data": serializer.data,
        }), status=status.HTTP_200_OK)


@extend_schema(
    summary="Get my trust score",
    tags=["Tasks"],
    description="Returns the authenticated user's trust score, submission history, and auto-approval eligibility based on past task performance.",
    responses={200: UserTrustScoreSerializer},
)
class MyTrustScoreView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        trust, _ = UserTrustScore.objects.get_or_create(user=request.user)
        return Response(data=encrypt({
            "status": "success",
            "message": "Trust score retrieved successfully.",
            "data": UserTrustScoreSerializer(trust).data,
        }), status=status.HTTP_200_OK)


# ── Brand campaign task views ─────────────────────────────────────────────────

@extend_schema(
    summary="List active brand campaign tasks (gamification feed)",
    tags=["Tasks"],
    description="Returns paginated brand ad campaigns as task cards for the gamification feed. Excludes campaigns the user has already submitted and those that have hit their slot cap.",
    parameters=[
        OpenApiParameter(name="task_type", type=OpenApiTypes.STR, description="Filter by task type (e.g. watch_video, social_engage, app_download)"),
    ],
    responses={
        200: inline_serializer(name="BrandTaskFeedResponse", fields={
            "status": s.CharField(),
            "message": s.CharField(),
            "data": BrandTaskFeedSerializer(many=True),
        }),
    },
)
class BrandTaskFeedView(generics.ListAPIView):
    """
    Returns all active brand ad campaigns as task cards for the gamification feed.
    Excludes campaigns the user has already submitted, and campaigns that have hit
    their slot cap. Supports ?task_type= filter.
    """

    serializer_class = BrandTaskFeedSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    pagination_class = PaginationStyle

    def get_queryset(self):
        user = self.request.user
        completed_ad_ids = BrandTaskSubmission.objects.filter(
            user=user
        ).values_list("ad_id", flat=True)

        qs = (
            CreateAd.objects.filter(is_active=True)
            .exclude(id__in=completed_ad_ids)
            .prefetch_related("ad_media")
            .order_by("-created_at")
        )

        task_type = self.request.query_params.get("task_type")
        if task_type:
            qs = qs.filter(task_type=task_type)

        return qs

    def list(self, request, *args, **kwargs):
        logger.info("BrandTaskFeedView accessed by user: %s", request.user.email)

        cache_key = f"brand_task_feed:{request.user.id}"
        cached = cache.get(cache_key)
        if cached:
            return Response(data=encrypt(cached), status=status.HTTP_200_OK)

        brand_data = BrandTaskFeedSerializer(self.get_queryset(), many=True).data

        today = timezone.now().date()
        inapp_qs = StreakChallenge.objects.filter(
            is_active=True,
            is_cancelled=False,
            end_date__gte=today,
        ).order_by("-created_at")
        inapp_data = InAppTaskFeedSerializer(inapp_qs, many=True).data

        response_data = {
            "status": "success",
            "message": "Tasks retrieved successfully.",
            "data": list(brand_data) + list(inapp_data),
        }

        cache.set(cache_key, response_data, timeout=60)
        return Response(data=encrypt(response_data), status=status.HTTP_200_OK)


@extend_schema(
    summary="Submit completion proof for a brand campaign task",
    tags=["Tasks"],
    description="Submit proof of completing a brand campaign task. Social engage and app download tasks require a screenshot and are queued for review; all other types are auto-approved immediately.",
    request=SubmitBrandTaskSerializer,
    responses={
        201: inline_serializer(name="SubmitBrandTaskResponse", fields={
            "status": s.CharField(),
            "message": s.CharField(),
            "data": inline_serializer(name="SubmitBrandTaskData", fields={"submission_id": s.UUIDField()}),
        }),
        400: inline_serializer(name="SubmitBrandTaskError", fields={"status": s.CharField(), "message": s.CharField()}),
    },
)
class SubmitBrandTaskView(generics.CreateAPIView):
    """
    User submits proof of completing a brand campaign task.
    - watch_video / website_visit / survey / store_visit: auto-approved on submission.
    - social_engage / app_download: screenshot required, queued for review.
    """

    serializer_class = SubmitBrandTaskSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def create(self, request, *args, **kwargs):
        try:
            decrypted_data = decrypt(request.data)
            serializer = self.get_serializer(
                data=decrypted_data, context={"request": request}
            )
            serializer.is_valid(raise_exception=True)
            submission = serializer.save()

            task_type = submission.ad.task_type
            needs_screenshot_review = task_type in ("social_engage", "app_download")

            if needs_screenshot_review:
                # Stays Pending — admin/AI reviews the screenshot
                logger.info(
                    "Brand task submission %s queued for review (type: %s)",
                    submission.pk, task_type,
                )
                send_push_to_admins(
                    title="Brand Task Needs Review",
                    body=f"{request.user.full_name or request.user.email} submitted proof for '{submission.ad.campaign_name}' — requires review.",
                    data={"type": "brand_review", "submission_id": str(submission.pk)},
                )
                return Response(
                    data=encrypt({
                        "status": "success",
                        "message": "Submission received. Your screenshot is being reviewed.",
                        "data": {"submission_id": str(submission.pk)},
                    }),
                    status=status.HTTP_201_CREATED,
                )
            else:
                # Auto-approve: timer/QR/survey completed client-side
                approve_brand_submission.delay(str(submission.pk), None)
                logger.info(
                    "Brand task submission %s auto-approved (type: %s)",
                    submission.pk, task_type,
                )
                return Response(
                    data=encrypt({
                        "status": "success",
                        "message": "Task completed! Points are being credited.",
                        "data": {"submission_id": str(submission.pk)},
                    }),
                    status=status.HTTP_201_CREATED,
                )

        except Exception as err:
            logger.error("Brand task submission failed: %s", str(err), exc_info=True)
            return Response(
                data=encrypt({"status": "error", "message": "Submission failed. Please try again."}),
                status=status.HTTP_400_BAD_REQUEST,
            )


@extend_schema(
    summary="Complete a webview brand task",
    tags=["Tasks"],
    description="Marks a website visit or video watch task as completed from the mobile webview and credits the reward points immediately.",
    request=CompleteWebviewTaskSerializer,
    responses={
        201: inline_serializer(name="CompleteWebviewTaskResponse", fields={
            "status": s.CharField(),
            "message": s.CharField(),
            "data": inline_serializer(name="CompleteWebviewTaskData", fields={
                "submission_id": s.UUIDField(),
                "task_id": s.IntegerField(),
                "reward_points": s.IntegerField(),
                "reward_issued": s.BooleanField(),
            }),
        }),
        400: inline_serializer(name="CompleteWebviewTaskError", fields={"status": s.CharField(), "message": s.CharField()}),
    },
)
class CompleteWebviewTaskView(APIView):
    """
    Mobile webview callback for tasks that are completed client-side.
    Only watch_video and website_visit tasks are accepted here.
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            decrypted_payload = decrypt(request.data)
            if not isinstance(decrypted_payload, dict):
                raise ValueError("Decrypted payload is not a valid object.")

            user_data = {
                key: value.strip() if isinstance(value, str) else value
                for key, value in decrypted_payload.items()
            }

            serializer = CompleteWebviewTaskSerializer(
                data=user_data, context={"request": request}
            )
            serializer.is_valid(raise_exception=True)
            ad = serializer.validated_data["ad"]
            submission = BrandTaskSubmission.objects.create(
                ad=ad,
                user=request.user,
                notes="Completed via mobile webview.",
            )

            points_awarded = approve_brand_submission_now(str(submission.pk), None)
            cache.delete(f"brand_task_feed:{request.user.id}")

            response_data = {
                "status": "success",
                "message": "Task completed. Points credited.",
                "data": {
                    "submission_id": str(submission.pk),
                    "task_id": ad.id,
                    "reward_points": points_awarded or 0,
                    "reward_issued": True,
                },
            }
            return Response(data=encrypt(response_data), status=status.HTTP_201_CREATED)

        except s.ValidationError as err:
            logger.info("Webview task completion validation failed: %s", err.detail)
            return Response(
                data=encrypt({"status": "error", "message": err.detail}),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as err:
            logger.error("Webview task completion failed: %s", str(err), exc_info=True)
            return Response(
                data=encrypt({"status": "error", "message": "Task completion failed. Please try again."}),
                status=status.HTTP_400_BAD_REQUEST,
            )


@extend_schema(
    summary="List my brand task submissions",
    tags=["Tasks"],
    description="Returns a paginated list of all brand campaign task submissions made by the authenticated user, including status and reward information.",
    responses={
        200: inline_serializer(name="MyBrandSubmissionsResponse", fields={
            "status": s.CharField(),
            "message": s.CharField(),
            "data": BrandTaskSubmissionSerializer(many=True),
        }),
    },
)
class MyBrandSubmissionsView(generics.ListAPIView):
    serializer_class = BrandTaskSubmissionSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    pagination_class = PaginationStyle

    def get_queryset(self):
        return (
            BrandTaskSubmission.objects.filter(user=self.request.user)
            .select_related("ad")
            .order_by("-created_at")
        )

    def list(self, request):
        logger.info("MyBrandSubmissionsView accessed by user: %s", request.user.email)

        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        serializer = (
            self.get_serializer(page, many=True)
            if page is not None
            else self.get_serializer(queryset, many=True)
        )

        response_data = {
            "status": "success",
            "message": "Brand task submissions retrieved successfully.",
            "data": serializer.data,
        }

        return Response(data=encrypt(response_data), status=status.HTTP_200_OK)
