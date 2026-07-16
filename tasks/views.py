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
from rest_framework.pagination import PageNumberPagination

from django.db.models import Q, F
from adverts.models import CreateAd, StoreVisitQRCode
from commons import Messaging, first_validation_error
from gamification.models import StreakChallenge, UserStreak
from gamification.points import Points
from security import encrypt, decrypt
from user_profile.fcm import send_push_to_user
from .jobs import (
    approve_brand_submission_now,
    run_verification,
    run_brand_verification,
)
from .models import (
    BrandTaskSubmission,
    SocialTask,
    StoreVisitArrival,
    TaskSubmission,
    UserTrustScore,
)
from user_profile.models import UserLocation
from .serializers import (
    BrandTaskFeedSerializer,
    BrandTaskSubmissionSerializer,
    CompleteWebviewTaskSerializer,
    InAppTaskFeedSerializer,
    ScanStoreVisitQRSerializer,
    SocialTaskFeedSerializer,
    SocialTaskSerializer,
    StoreVisitArrivalIdSerializer,
    StoreVisitArriveSerializer,
    SubmitTaskSerializer,
    TaskSubmissionSerializer,
    UserTrustScoreSerializer,
)
from modules.geo_algorithm import (
    LocationMatcher,
    TaskSortingStrategy,
    DEFAULT_RADIUS_KM,
    get_distance_band,
)

logger = logging.getLogger(__name__)


class PaginationStyle(PageNumberPagination):
    page_size = 20


def _brand_feed_cache_version_key(user_id):
    return f"brand_task_feed_version:{user_id}"


def _get_brand_feed_cache_version(user_id):
    version = cache.get(_brand_feed_cache_version_key(user_id))
    if version is None:
        version = 1
        cache.set(_brand_feed_cache_version_key(user_id), version, timeout=None)
    return version


def invalidate_brand_feed_cache(user):
    """Invalidate brand feed cache for a user by bumping their cache version."""
    version_key = _brand_feed_cache_version_key(user.id)
    try:
        cache.incr(version_key)
    except ValueError:
        cache.set(version_key, 1, timeout=None)


@extend_schema(
    summary="List available social tasks",
    tags=["Tasks"],
    description="Returns all active social tasks that are currently available for the authenticated user to complete. Supports optional filtering by platform and task type.",
    parameters=[
        OpenApiParameter(
            name="platform",
            type=OpenApiTypes.STR,
            description="Filter by social platform (e.g. twitter, instagram)",
        ),
        OpenApiParameter(
            name="task_type",
            type=OpenApiTypes.STR,
            description="Filter by task type (e.g. Follow, Comment, Post)",
        ),
    ],
    responses={200: SocialTaskSerializer(many=True)},
)
class SocialTaskListView(generics.ListAPIView):
    serializer_class = SocialTaskSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        submitted_ids = (
            TaskSubmission.objects.filter(user=user)
            .exclude(status="Rejected")
            .values_list("task_id", flat=True)
        )
        qs = (
            SocialTask.objects.filter(is_active=True)
            .exclude(id__in=submitted_ids)
            .order_by("-created_at")
        )
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
        return Response(
            data=encrypt(
                {
                    "status": "success",
                    "message": "Tasks retrieved successfully.",
                    "data": serializer.data,
                }
            ),
            status=status.HTTP_200_OK,
        )


@extend_schema(
    summary="List my task submissions",
    tags=["Tasks"],
    description="Returns all social task submissions made by the authenticated user, including verification status and AI review results.",
    responses={200: TaskSubmissionSerializer(many=True)},
)
class MySubmissionsView(generics.ListAPIView):
    serializer_class = TaskSubmissionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            TaskSubmission.objects.filter(user=self.request.user)
            .select_related("task", "verification")
            .order_by("-created_at")
        )

    def list(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_queryset(), many=True)
        return Response(
            data=encrypt(
                {
                    "status": "success",
                    "message": "Submissions retrieved successfully.",
                    "data": serializer.data,
                }
            ),
            status=status.HTTP_200_OK,
        )


@extend_schema(
    summary="Get my trust score",
    tags=["Tasks"],
    description="Returns the authenticated user's trust score, submission history, and auto-approval eligibility based on past task performance.",
    responses={200: UserTrustScoreSerializer},
)
class MyTrustScoreView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        trust, _ = UserTrustScore.objects.get_or_create(user=request.user)
        return Response(
            data=encrypt(
                {
                    "status": "success",
                    "message": "Trust score retrieved successfully.",
                    "data": UserTrustScoreSerializer(trust).data,
                }
            ),
            status=status.HTTP_200_OK,
        )


# ── Brand campaign task views ─────────────────────────────────────────────────
@extend_schema(
    summary="List active brand campaign tasks (gamification feed)",
    tags=["Tasks"],
    description=(
        "Returns paginated brand ad campaigns as task cards for the gamification feed. "
        "Store visit tasks are filtered by proximity to user's location (closest first). "
        "Other task types are interleaved with store visits for a balanced feed. "
        "Excludes campaigns the user has already submitted and those that have hit their slot cap."
    ),
    parameters=[
        OpenApiParameter(
            name="task_type",
            type=OpenApiTypes.STR,
            description="Filter by task type (e.g. watch_video, social_engage, app_download, store_visit)",
        ),
        OpenApiParameter(
            name="radius_km",
            type=OpenApiTypes.FLOAT,
            description="Search radius in kilometers for store visit tasks (default: 10.0)",
            default=10.0,
        ),
        OpenApiParameter(
            name="limit_store_visits",
            type=OpenApiTypes.INT,
            description="Maximum number of store visit tasks to show (default: 20)",
            default=20,
        ),
    ],
    responses={
        200: inline_serializer(
            name="BrandTaskFeedResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "data": BrandTaskFeedSerializer(many=True),
            },
        ),
    },
)
class BrandTaskFeedView(generics.ListAPIView):
    """
    Returns all active brand ad campaigns as task cards for the gamification feed.
    Excludes campaigns the user has already submitted, and campaigns that have hit
    their slot cap. Supports ?task_type= filter.

    Store visit tasks are filtered by proximity to user's location using PostGIS
    (ST_DWithin / Distance over a geography-typed location column). Tasks are
    sorted with nearby store visits prioritized, followed by other task types
    in a balanced interleaved manner.
    """

    serializer_class = BrandTaskFeedSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = PaginationStyle

    def get_user_location(self, user):
        """
        Get user's current location from UserLocation model.

        Returns:
            tuple: (latitude, longitude) or (None, None) if not found
        """
        try:
            user_location = UserLocation.objects.get(user=user)
            return user_location.latitude, user_location.longitude
        except UserLocation.DoesNotExist:
            logger.warning(f"No location found for user {user.email}")
            return None, None

    def get_queryset(self):
        user = self.request.user
        completed_ad_ids = (
            BrandTaskSubmission.objects.filter(user=user)
            .exclude(status="Rejected")
            .values_list("ad_id", flat=True)
        )

        # Base queryset
        qs = (
            CreateAd.objects.filter(is_active=True, expiry_date__gt=timezone.now())
            .exclude(id__in=completed_ad_ids)
            .prefetch_related("ad_media")
            .order_by("-created_at")
        )

        # Filter by task_type if provided
        task_type = self.request.query_params.get("task_type")
        if task_type:
            qs = qs.filter(task_type=task_type)

        # Get user's location from their profile
        user_city = user.city
        user_state = user.state
        user_country = user.country

        # Build location filter - start with nationwide
        location_filter = Q(location_type="nationwide") | Q(location_type__isnull=True)

        # Add state-level targeting if user has state
        if user_state:
            location_filter |= Q(
                location_type="states", brand_location__state=user_state
            )

        # Add city-level targeting if user has city
        if user_city:
            location_filter |= Q(location_type="cities", brand_location__city=user_city)

        # Apply location filter
        qs = qs.filter(location_filter)

        # Country filtering that runs independently
        if user_country:
            qs = qs.filter(
                Q(countries__isnull=True)
                | Q(countries__exact=[])
                | Q(countries__contains=[user_country])
            )

        # Filter out ads that have hit their slot cap
        qs = qs.filter(slots_filled__lt=F("slot_cap"))

        # Prevent duplicate rows from relational joins
        return qs.distinct()

    def list(self, request, *args, **kwargs):
        logger.info("BrandTaskFeedView accessed by user: %s", request.user.email)

        # Get radius parameter from query
        try:
            radius_km = float(request.query_params.get("radius_km", DEFAULT_RADIUS_KM))
        except (TypeError, ValueError):
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "radius_km must be a valid number.",
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        radius_km = min(radius_km, 50.0)  # Cap at 50km

        # Get limit for store visits
        try:
            limit_store_visits = int(request.query_params.get("limit_store_visits", 20))
        except (TypeError, ValueError):
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "limit_store_visits must be a valid integer.",
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = request.user
        location_key = f"{user.city}:{user.state}:{user.country}"
        cache_version = _get_brand_feed_cache_version(user.id)
        cache_key = (
            f"brand_task_feed:{request.user.id}:{location_key}:"
            f"{radius_km}:{limit_store_visits}:v{cache_version}"
        )

        cached = cache.get(cache_key)
        if cached:
            return Response(data=encrypt(cached), status=status.HTTP_200_OK)

        # Fetch data from DB if not cached
        user_lat, user_lon = self.get_user_location(request.user)

        # Get base queryset
        queryset = self.get_queryset()

        # Separate store visits from other task types
        store_visits = queryset.filter(task_type="store_visit")
        other_brand_tasks = queryset.exclude(task_type="store_visit")

        # Process store visits with location filtering
        store_data = []
        if user_lat is not None and user_lon is not None:
            # Use the location matcher (PostGIS-backed) to filter and sort store visits in a single indexed DB query.
            matcher = LocationMatcher()
            matched_store_tasks = matcher.match_tasks_to_user(
                tasks_queryset=store_visits,
                user_lat=user_lat,
                user_lon=user_lon,
                radius_km=radius_km,
                max_results=limit_store_visits,
            )

            # Serialize matched store tasks
            for item in matched_store_tasks:
                task = item["task"]
                task_data = BrandTaskFeedSerializer(
                    task, context={"request": request}
                ).data
                task_data["distance_km"] = item["distance_km"]
                task_data["distance_meters"] = item["distance_meters"]
                task_data["distance_band"] = get_distance_band(item["distance_km"])
                store_data.append(task_data)

            logger.info(
                f"Found {len(store_data)} nearby store visits within {radius_km}km"
            )
        else:
            # Show store visits but without distance info when user location is unavailable
            store_data = BrandTaskFeedSerializer(
                store_visits, many=True, context={"request": request}
            ).data
            for task_data in store_data:
                task_data["distance_km"] = None
                task_data["distance_band"] = "Location unknown"

        # Process other brand tasks that are not store visits (no distance filtering)
        other_brand_data = BrandTaskFeedSerializer(
            other_brand_tasks, many=True, context={"request": request}
        ).data
        for task_data in other_brand_data:
            task_data["distance_km"] = None
            task_data["distance_band"] = "N/A"

        # Get social tasks
        completed_social_ids = (
            TaskSubmission.objects.filter(user=user)
            .exclude(status="Rejected")
            .values_list("task_id", flat=True)
        )
        social_qs = (
            SocialTask.objects.filter(is_active=True)
            .exclude(id__in=completed_social_ids)
            .select_related("ad")
            .prefetch_related("ad__ad_media")
            .order_by("-created_at")
        )
        social_data = SocialTaskFeedSerializer(
            [t for t in social_qs if t.is_available], many=True
        ).data
        for task_data in social_data:
            task_data["distance_km"] = None
            task_data["distance_band"] = "N/A"

        # Get in-app tasks
        inapp_qs = StreakChallenge.objects.filter(
            is_active=True,
            is_cancelled=False,
            end_date__gte=timezone.now(),
        ).order_by("-created_at")
        inapp_data = InAppTaskFeedSerializer(inapp_qs, many=True).data
        for task_data in inapp_data:
            task_data["distance_km"] = None
            task_data["distance_band"] = "N/A"

        # Apply sorting strategy to combine all tasks
        sorted_tasks = TaskSortingStrategy.sort_tasks_by_priority_and_distance(
            brand_tasks=store_data + other_brand_data,
            social_tasks=social_data,
            inapp_tasks=inapp_data,
            user_lat=user_lat,
            user_lon=user_lon,
            radius_km=radius_km,
        )

        def _is_store_visit(task_data):
            return (
                task_data.get("task_type") == "store_visit"
                or task_data.get("type") == "store_visit"
            )

        store_tasks = [t for t in sorted_tasks if _is_store_visit(t)]
        other_tasks = [t for t in sorted_tasks if not _is_store_visit(t)]

        if store_tasks and other_tasks:
            # Interleave store tasks with other types
            interleaved = TaskSortingStrategy.interleave_tasks_by_type(
                store_tasks=store_tasks,
                other_tasks=other_tasks,
                max_store_per_cycle=3,
            )
            final_data = interleaved
        else:
            # use sorted order if only one type exists
            final_data = sorted_tasks

        # Properly handle store_visit filter without hiding valid tasks
        task_type_filter = self.request.query_params.get("task_type")
        if task_type_filter:
            if task_type_filter == "store_visit":
                # If location is NOT available, distance_km will be None but they're still valid store visits
                final_data = [
                    t
                    for t in final_data
                    if t.get("task_type") == "store_visit"
                    or t.get("type") == "store_visit"
                ]
                # Add a note in metadata about location status
                location_status = "available" if user_lat is not None else "unavailable"
                logger.info(
                    f"Filtered to {len(final_data)} store visits (location {location_status})"
                )
            else:
                # Filter by task_type field in the data
                final_data = [
                    t
                    for t in final_data
                    if t.get("task_type") == task_type_filter
                    or t.get("type") == task_type_filter
                ]

        # Prepare response data with metadata
        response_data = {
            "status": "success",
            "message": "Tasks retrieved successfully.",
            "data": final_data,
            "metadata": {
                "total_tasks": len(final_data),
                "store_visits_found": len(store_tasks),
                "other_tasks_found": len(other_tasks),
                "user_location": (
                    {"latitude": user_lat, "longitude": user_lon}
                    if user_lat is not None
                    else None
                ),
                "search_radius_km": radius_km,
                "has_user_location": user_lat is not None,
                "location_filter_applied": (
                    task_type_filter == "store_visit" if task_type_filter else False
                ),
            },
        }

        cache.set(cache_key, response_data, timeout=60)
        return Response(data=encrypt(response_data), status=status.HTTP_200_OK)


@extend_schema(
    summary="Submit proof for a task",
    tags=["Tasks"],
    description="Submit screenshot proof for a task. The submission is verified immediately using AI. A verification code is returned for Comment and Post task types.",
    request=SubmitTaskSerializer,
    responses={
        201: inline_serializer(
            name="SubmitBrandTaskResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "data": inline_serializer(
                    name="SubmitBrandTaskData",
                    fields={
                        "submission_id": s.UUIDField(),
                        "verification_code": s.CharField(required=False),
                        "verification_note": s.CharField(required=False),
                    },
                ),
            },
        ),
        400: inline_serializer(
            name="SubmitBrandTaskError",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class SubmitBrandTaskView(generics.CreateAPIView):
    serializer_class = SubmitTaskSerializer
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

            raw_task = user_data.get("task", "")

            # Integer task id → brand campaign (CreateAd) social_engage submission.
            try:
                ad_id = int(raw_task)
                is_brand_task = True
            except (ValueError, TypeError):
                is_brand_task = False

            if is_brand_task:
                user = request.user
                try:
                    ad = CreateAd.objects.get(pk=ad_id)
                except CreateAd.DoesNotExist:
                    raise s.ValidationError({"task": ["Task not found."]})

                if not ad.is_active:
                    raise s.ValidationError(
                        {"task": ["This campaign is no longer active."]}
                    )

                if ad.task_type != "social_engage":
                    raise s.ValidationError(
                        {"task": ["This endpoint is only for social engage tasks."]}
                    )

                if (
                    BrandTaskSubmission.objects.filter(ad=ad, user=user)
                    .exclude(status="Rejected")
                    .exists()
                ):
                    raise s.ValidationError(
                        {"task": ["You have already submitted this task."]}
                    )

                screenshot_url = user_data.get("screenshot_url")
                if not screenshot_url:
                    raise s.ValidationError(
                        {"screenshot_url": ["A screenshot is required."]}
                    )

                submission = BrandTaskSubmission.objects.create(
                    ad=ad,
                    user=user,
                    screenshot_url=screenshot_url,
                    notes=user_data.get("notes", ""),
                )
                run_brand_verification.delay(str(submission.pk))
                invalidate_brand_feed_cache(user)

                return Response(
                    data=encrypt(
                        {
                            "status": "success",
                            "message": "Submission received. Verification in progress.",
                            "data": {
                                "submission_id": str(submission.pk),
                            },
                        }
                    ),
                    status=status.HTTP_201_CREATED,
                )

            # UUID task id → admin-created SocialTask submission.
            serializer = self.get_serializer(
                data=user_data, context={"request": request}
            )
            serializer.is_valid(raise_exception=True)
            submission = serializer.save()

            run_verification.delay(str(submission.pk))

            response_data = {
                "status": "success",
                "message": "Submission received. Verification in progress.",
                "data": {"submission_id": str(submission.pk)},
            }
            if submission.verification_code:
                response_data["data"][
                    "verification_code"
                ] = submission.verification_code
                response_data["data"]["verification_note"] = (
                    f"Include this code verbatim in your {submission.task.task_type.lower()}: "
                    f"{submission.verification_code}"
                )

            return Response(data=encrypt(response_data), status=status.HTTP_201_CREATED)

        except s.ValidationError as err:
            logger.warning(
                "SubmitBrandTaskView validation failed for user %s: %s",
                request.user.id,
                err.detail,
            )
            return Response(
                data=encrypt(
                    {"status": "fail", "message": first_validation_error(err.detail)}
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as err:
            logger.error(
                "SubmitBrandTaskView failed for user %s: %s",
                request.user.id,
                str(err),
                exc_info=True,
            )
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "Submission failed. Please try again.",
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )


@extend_schema(
    summary="Complete a webview or in-app task",
    tags=["Tasks"],
    description=(
        "Marks a watch_video, website_visit, survey, or store_visit brand task as done and credits points immediately. "
        "Also handles in-app StreakChallenge tasks (source='inapp'). "
        "Payload: task_id, is_done=true, source ('brand' or 'inapp')."
    ),
    request=CompleteWebviewTaskSerializer,
    responses={
        201: inline_serializer(
            name="CompleteWebviewTaskResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "data": s.DictField(),
            },
        ),
        400: inline_serializer(
            name="CompleteWebviewTaskError",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class CompleteWebviewTaskView(APIView):
    """
    Completes watch_video / website_visit / survey / store_visit brand tasks, and any
    in-app StreakChallenge tasks of those types created from the admin (source='inapp').
    """

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
            source = serializer.validated_data.get("source", "brand")

            if source == "brand":
                ad = serializer.validated_data["ad"]
                submission = BrandTaskSubmission.objects.create(
                    ad=ad,
                    user=request.user,
                    notes="Completed via mobile webview.",
                )
                points_awarded = approve_brand_submission_now(str(submission.pk), None)

                invalidate_brand_feed_cache(request.user)

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

            else:  # inapp
                challenge = serializer.validated_data["challenge"]
                today = timezone.now().date()

                user_streak, _ = UserStreak.objects.get_or_create(
                    user=request.user,
                    challenge=challenge,
                )

                if user_streak.last_activity_date == today:
                    return Response(
                        data=encrypt(
                            {
                                "status": "fail",
                                "message": "Already recorded today's activity for this challenge.",
                            }
                        ),
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                user_streak.current_count += 1
                user_streak.last_activity_date = today
                if user_streak.current_count > user_streak.longest_count:
                    user_streak.longest_count = user_streak.current_count

                points_awarded = 0
                reward_issued = False
                if (
                    user_streak.current_count >= challenge.duration_days
                    and not user_streak.reward_issued
                ):
                    awarded, _ = Points.award(
                        user=request.user,
                        amount=challenge.reward_points,
                        reason=f"Completed challenge: {challenge.name}",
                        source="inapp_task",
                        reference_id=str(challenge.id),
                    )
                    if awarded:
                        user_streak.completed = True
                        user_streak.completed_at = timezone.now()
                        user_streak.reward_issued = True
                        points_awarded = challenge.reward_points
                        reward_issued = True

                user_streak.save()
                cache.delete(f"brand_task_feed:{request.user.id}")

                response_data = {
                    "status": "success",
                    "message": (
                        "Task completed. Points credited."
                        if reward_issued
                        else "Activity recorded."
                    ),
                    "data": {
                        "challenge_id": str(challenge.id),
                        "current_count": user_streak.current_count,
                        "duration_days": challenge.duration_days,
                        "reward_points": points_awarded,
                        "reward_issued": reward_issued,
                    },
                }

            return Response(data=encrypt(response_data), status=status.HTTP_201_CREATED)

        except s.ValidationError as err:
            logger.info("Webview task completion validation failed: %s", err.detail)
            return Response(
                data=encrypt(
                    {"status": "fail", "message": first_validation_error(err.detail)}
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as err:
            logger.error("Webview task completion failed: %s", str(err), exc_info=True)
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "Task completion failed. Please try again.",
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )


def _notify_brand_of_survey(ad, answers):
    brand_user = ad.user
    rows = "".join(
        f"<tr><td style='padding:6px 12px;border:1px solid #ddd'>{i + 1}</td>"
        f"<td style='padding:6px 12px;border:1px solid #ddd'>{a.get('question', '')}</td>"
        f"<td style='padding:6px 12px;border:1px solid #ddd'>{a.get('answer', '')}</td></tr>"
        for i, a in enumerate(answers)
    )
    html = (
        f"<p>A new survey response has been submitted for your campaign "
        f"<strong>{ad.campaign_name}</strong>.</p>"
        f"<table style='border-collapse:collapse;width:100%'>"
        f"<thead><tr>"
        f"<th style='padding:6px 12px;border:1px solid #ddd'>#</th>"
        f"<th style='padding:6px 12px;border:1px solid #ddd'>Question</th>"
        f"<th style='padding:6px 12px;border:1px solid #ddd'>Answer</th>"
        f"</tr></thead><tbody>{rows}</tbody></table>"
    )
    try:
        Messaging.send_email(
            email=brand_user.email,
            sender_email="notifications@picadailys.com",
            subject=f"New Survey Response — {ad.campaign_name}",
            html_content=html,
            body=f"A new survey response was submitted for your campaign: {ad.campaign_name}.",
        )
    except Exception:
        logger.exception(
            "Failed to email survey response to brand %s", brand_user.email
        )

    try:
        send_push_to_user(
            user=brand_user,
            title="New Survey Response",
            body=f'Someone completed your survey for "{ad.campaign_name}".',
        )
    except Exception:
        logger.exception(
            "Failed to push survey notification to brand %s", brand_user.id
        )


@extend_schema(
    summary="Submit survey task answers",
    tags=["Tasks"],
    description=(
        "Submit answers for a survey brand task. Mobile is trusted to have already verified "
        "the answers — points are awarded immediately on submission. "
        "Payload: task_id (CreateAd UUID), answers (list of answer objects)."
    ),
    request=inline_serializer(
        name="SubmitSurveyTaskRequest",
        fields={
            "task_id": s.UUIDField(),
            "answers": s.ListField(
                child=s.DictField(), help_text="List of survey answer objects"
            ),
        },
    ),
    responses={
        201: inline_serializer(
            name="SubmitSurveyTaskResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "data": s.DictField(),
            },
        ),
        400: inline_serializer(
            name="SubmitSurveyTaskError",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class SubmitSurveyTaskView(APIView):
    """
    POST /v1/tasks/brand/survey/submit/

    Accepts survey answers for a brand survey task, records the submission,
    and immediately awards points (mobile has already verified the responses).
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            payload = decrypt(request.data)
            if not isinstance(payload, dict):
                raise ValueError("Invalid payload.")

            task_id = payload.get("task_id")
            answers = payload.get("answers", [])

            if not task_id:
                return Response(
                    data=encrypt({"status": "fail", "message": "task_id is required."}),
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if not isinstance(answers, list) or not answers:
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "message": "answers must be a non-empty list.",
                        }
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )

            try:
                ad = CreateAd.objects.get(
                    pk=task_id, task_type="survey", is_active=True
                )
            except CreateAd.DoesNotExist:
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "message": "Survey task not found or inactive.",
                        }
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if (
                BrandTaskSubmission.objects.filter(ad=ad, user=request.user)
                .exclude(status="Rejected")
                .exists()
            ):
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "message": "You have already submitted this survey.",
                        }
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )

            submission = BrandTaskSubmission.objects.create(
                ad=ad,
                user=request.user,
                survey_answers=answers,
                notes="Survey submitted via mobile.",
            )

            points_awarded = approve_brand_submission_now(str(submission.pk), None)

            invalidate_brand_feed_cache(request.user)

            _notify_brand_of_survey(ad, answers)

            return Response(
                data=encrypt(
                    {
                        "status": "success",
                        "message": "Survey submitted. Points credited.",
                        "data": {
                            "submission_id": str(submission.pk),
                            "task_id": str(ad.pk),
                            "reward_points": points_awarded or 0,
                            "reward_issued": True,
                        },
                    }
                ),
                status=status.HTTP_201_CREATED,
            )

        except Exception as err:
            logger.error(
                "SubmitSurveyTaskView failed for user %s: %s",
                request.user.id,
                str(err),
                exc_info=True,
            )
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "Survey submission failed. Please try again.",
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )


@extend_schema(
    summary="List my brand task submissions",
    tags=["Tasks"],
    description="Returns a paginated list of all brand campaign task submissions made by the authenticated user, including status and reward information.",
    responses={
        200: inline_serializer(
            name="MyBrandSubmissionsResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "data": BrandTaskSubmissionSerializer(many=True),
            },
        ),
    },
)
class MyBrandSubmissionsView(generics.ListAPIView):
    serializer_class = BrandTaskSubmissionSerializer
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


@extend_schema(
    summary="Complete a store-visit via QR scan or visit code",
    tags=["Tasks"],
    description=(
        "Completes a store-visit task and credits points immediately. "
        "Send either a QR token (scanned from the brand's QR code) or a visit code "
        "(short alphanumeric code the store owner reads out or shows to the user when they cannot scan). "
        "Each user can only complete a given campaign once."
    ),
    request=inline_serializer(
        name="ScanStoreVisitQRRequest",
        fields={"token": s.UUIDField()},
    ),
    responses={
        201: inline_serializer(
            name="ScanStoreVisitQRResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "data": inline_serializer(
                    name="ScanStoreVisitQRData",
                    fields={
                        "submission_id": s.UUIDField(),
                        "reward_points": s.IntegerField(),
                        "reward_issued": s.BooleanField(),
                    },
                ),
            },
        ),
        400: inline_serializer(
            name="ScanStoreVisitQRError",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class ScanStoreVisitQRView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            decrypted_data = decrypt(request.data)
            logger.info(
                "ScanStoreVisitQRView payload for user %s: %r",
                request.user.id,
                decrypted_data,
            )
            serializer = ScanStoreVisitQRSerializer(
                data=decrypted_data, context={"request": request}
            )
            serializer.is_valid(raise_exception=True)

            qr = serializer.qr
            ad = qr.ad

            submission = BrandTaskSubmission.objects.create(
                ad=ad,
                user=request.user,
                notes="Completed via QR code scan.",
            )
            points_awarded = approve_brand_submission_now(str(submission.pk), None)

            StoreVisitQRCode.objects.filter(pk=qr.pk).update(
                scan_count=F("scan_count") + 1
            )
            invalidate_brand_feed_cache(request.user)

            return Response(
                data=encrypt(
                    {
                        "status": "success",
                        "message": "Store visit recorded. Points credited.",
                        "data": {
                            "submission_id": str(submission.pk),
                            "reward_points": points_awarded or 0,
                            "reward_issued": True,
                        },
                    }
                ),
                status=status.HTTP_201_CREATED,
            )

        except s.ValidationError as err:
            message = first_validation_error(err.detail)
            logger.warning(
                "ScanStoreVisitQRView validation failed for user %s: %s",
                request.user.id,
                message,
            )
            return Response(
                data=encrypt({"status": "error", "message": message}),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as err:
            logger.error(
                "ScanStoreVisitQRView failed for user %s: %s",
                request.user.id,
                str(err),
                exc_info=True,
            )
            return Response(
                data=encrypt(
                    {"status": "error", "message": "QR scan failed. Please try again."}
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )


@extend_schema(
    summary="Arrive at a store-visit campaign",
    tags=["Tasks"],
    description=(
        "Marks the authenticated user as arrived for a store-visit campaign. "
        "Identify the campaign by task_id or by the visit code the store owner shows the user. "
        "Returns an arrival_id used in the OTP and no-show endpoints."
    ),
    request=inline_serializer(
        name="StoreVisitArriveRequest",
        fields={
            "task_id": s.IntegerField(required=False),
            "code": s.CharField(required=False),
        },
    ),
    responses={
        201: inline_serializer(
            name="StoreVisitArriveResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "data": inline_serializer(
                    name="StoreVisitArriveData",
                    fields={
                        "arrival_id": s.UUIDField(),
                        "campaign_name": s.CharField(),
                        "reward_points": s.IntegerField(),
                    },
                ),
            },
        ),
    },
)
class StoreVisitArriveView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            decrypted_data = decrypt(request.data)
            serializer = StoreVisitArriveSerializer(
                data=decrypted_data, context={"request": request}
            )
            serializer.is_valid(raise_exception=True)

            ad = serializer.ad
            existing = serializer.existing_arrival

            if existing and existing.status == "arrived":
                return Response(
                    data=encrypt(
                        {
                            "status": "success",
                            "message": "You have already checked in. Proceed with OTP or QR scan.",
                            "data": {
                                "arrival_id": str(existing.id),
                                "campaign_name": ad.campaign_name,
                                "reward_points": ad.reward_points or 0,
                            },
                        }
                    ),
                    status=status.HTTP_200_OK,
                )

            if existing:
                existing.status = "arrived"
                existing.completed_at = None
                existing.save(update_fields=["status", "completed_at"])
                arrival = existing
            else:
                arrival = StoreVisitArrival.objects.create(ad=ad, user=request.user)

            return Response(
                data=encrypt(
                    {
                        "status": "success",
                        "message": "Arrival recorded. Scan the QR code, ask the store owner for the visit code, or request an OTP.",
                        "data": {
                            "arrival_id": str(arrival.id),
                            "campaign_name": ad.campaign_name,
                            "reward_points": ad.reward_points or 0,
                        },
                    }
                ),
                status=status.HTTP_201_CREATED,
            )

        except s.ValidationError as err:
            message = first_validation_error(err.detail)
            logger.warning(
                "StoreVisitArriveView validation failed for user %s: %s",
                request.user.id,
                message,
            )
            return Response(
                data=encrypt({"status": "error", "message": message}),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as err:
            logger.error(
                "StoreVisitArriveView error for user %s: %s",
                request.user.id,
                err,
                exc_info=True,
            )
            return Response(
                data=encrypt(
                    {
                        "status": "error",
                        "message": "Could not record arrival. Please try again.",
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )


@extend_schema(
    summary="Report store not available (no-show)",
    tags=["Tasks"],
    description=(
        "Called by the user when they arrive at the store location but the brand or store owner "
        "is not present. Marks the arrival as no-show so the system can log the failed visit."
    ),
    request=inline_serializer(
        name="StoreVisitNoShowRequest",
        fields={"arrival_id": s.UUIDField()},
    ),
    responses={
        200: inline_serializer(
            name="StoreVisitNoShowResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class StoreVisitNoShowView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            decrypted_data = decrypt(request.data)
            serializer = StoreVisitArrivalIdSerializer(
                data=decrypted_data, context={"request": request}
            )
            serializer.is_valid(raise_exception=True)
            arrival = serializer.arrival

            if arrival.status != "arrived":
                return Response(
                    data=encrypt(
                        {
                            "status": "error",
                            "message": "No active arrival to report. Check in first.",
                        }
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )

            arrival.status = "no_show"
            arrival.save(update_fields=["status", "updated_at"])

            return Response(
                data=encrypt(
                    {
                        "status": "success",
                        "message": "Sorry the store was unavailable. Your visit has been logged.",
                    }
                ),
                status=status.HTTP_200_OK,
            )

        except s.ValidationError as err:
            return Response(
                data=encrypt(
                    {"status": "error", "message": first_validation_error(err.detail)}
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as err:
            logger.error(
                "StoreVisitNoShowView error for user %s: %s",
                request.user.id,
                err,
                exc_info=True,
            )
            return Response(
                data=encrypt(
                    {"status": "error", "message": "Request failed. Please try again."}
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
