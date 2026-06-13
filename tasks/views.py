import logging

from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from permissions import IsSuperAdmin
from .jobs import manual_approve, manual_reject, run_verification
from .models import SocialProfile, SocialTask, TaskSubmission, UserTrustScore
from .serializers import (
    AdminReviewSerializer,
    SocialProfileSerializer,
    SocialTaskSerializer,
    SubmitTaskSerializer,
    TaskSubmissionSerializer,
    UserTrustScoreSerializer,
)

logger = logging.getLogger(__name__)


class SocialProfileView(generics.RetrieveUpdateAPIView):
    """Get or update the authenticated user's linked social usernames."""

    serializer_class = SocialProfileSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get_object(self):
        profile, _ = SocialProfile.objects.get_or_create(user=self.request.user)
        return profile

    @extend_schema(summary="Get social profile", tags=["Social Tasks"])
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(summary="Update social profile", tags=["Social Tasks"])
    def patch(self, request, *args, **kwargs):
        return super().partial_update(request, *args, **kwargs)

    @extend_schema(summary="Update social profile", tags=["Social Tasks"])
    def put(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)


@extend_schema(summary="List available social tasks", tags=["Social Tasks"])
class SocialTaskListView(generics.ListAPIView):
    """All active, non-expired tasks with remaining capacity."""

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
    """
    User submits a screenshot (Cloudinary URL) as proof of completing a task.
    An async verification job is triggered immediately.
    """

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


@extend_schema(summary="[Admin] List submissions pending review", tags=["Social Tasks Admin"])
class PendingReviewListView(generics.ListAPIView):
    serializer_class = TaskSubmissionSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get_queryset(self):
        return (
            TaskSubmission.objects.filter(status="Pending")
            .select_related("task", "user", "verification")
            .order_by("created_at")
        )


@extend_schema(summary="[Admin] Approve or reject a submission", tags=["Social Tasks Admin"])
class ReviewSubmissionView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def post(self, request, submission_id):
        try:
            submission = TaskSubmission.objects.get(pk=submission_id)
        except TaskSubmission.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = AdminReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        action = serializer.validated_data["action"]
        reason = serializer.validated_data.get("reason", "")

        if action == "approve":
            manual_approve.delay(str(submission.pk), str(request.user.pk))
        else:
            manual_reject.delay(str(submission.pk), str(request.user.pk), reason)

        return Response({"detail": f"Submission queued for {action}."})
