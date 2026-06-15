import logging

from django.core.cache import cache

from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.pagination import PageNumberPagination

from adverts.models import CreateAd
from security import encrypt, decrypt
from .jobs import run_verification, approve_brand_submission
from user_profile.fcm import send_push_to_admins
from .models import BrandTaskSubmission, SocialTask, TaskSubmission, UserTrustScore
from .serializers import (
    BrandTaskFeedSerializer,
    BrandTaskSubmissionSerializer,

    SocialTaskSerializer,
    SubmitBrandTaskSerializer,
    SubmitTaskSerializer,
    TaskSubmissionSerializer,
    UserTrustScoreSerializer,
)

logger = logging.getLogger(__name__)


class PaginationStyle(PageNumberPagination):
    page_size = 20



@extend_schema(summary="List available social tasks", tags=["Social Tasks"])
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
        return Response(serializer.data)


@extend_schema(summary="Submit proof for a social task", tags=["Social Tasks"])
class SubmitTaskView(generics.CreateAPIView):
    serializer_class = SubmitTaskSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        submission = serializer.save()

        run_verification.delay(str(submission.pk))

        return Response(
            {"detail": "Submission received. Verification in progress.", "id": str(submission.pk)},
            status=status.HTTP_201_CREATED,
        )


@extend_schema(summary="List my task submissions", tags=["Social Tasks"])
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


@extend_schema(summary="Get my trust score", tags=["Social Tasks"])
class MyTrustScoreView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        trust, _ = UserTrustScore.objects.get_or_create(user=request.user)
        return Response(UserTrustScoreSerializer(trust).data)


# ── Brand campaign task views ─────────────────────────────────────────────────

@extend_schema(summary="List active brand campaign tasks (gamification feed)", tags=["Brand Tasks"])
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

        qs = self.get_queryset()
        # Exclude slot-capped campaigns
        available = [ad for ad in qs if not (ad.slot_cap and ad.slots_filled >= ad.slot_cap)]

        page = self.paginate_queryset(available)
        serializer = (
            self.get_serializer(page, many=True)
            if page is not None
            else self.get_serializer(available, many=True)
        )

        response_data = {
            "status": "success",
            "message": "Brand tasks retrieved successfully.",
            "data": serializer.data,
        }

        cache.set(cache_key, response_data, timeout=60)

        return Response(data=encrypt(response_data), status=status.HTTP_200_OK)


@extend_schema(summary="Submit completion proof for a brand campaign task", tags=["Brand Tasks"])
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


@extend_schema(summary="List my brand task submissions", tags=["Brand Tasks"])
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


