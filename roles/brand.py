import logging
from decimal import Decimal

from django.contrib.auth.hashers import check_password
from django.core.cache import cache
from django.db.models import Count, Q
from django.utils import timezone

# In project imports.
from .serializers import (
    RestrictBrandAdSerializers,
    ListBrandAdSerializer,
)
from .models import RestrictBrandAdAccount, ActivityModel
from adverts.models import CreateAd
from adverts.serializers import AdSerializers
from tasks.models import BrandTaskSubmission, TaskSubmission
from tasks.serializers import (
    BrandTaskSubmissionSerializer,
    TaskSubmissionSerializer,
    AdminReviewSerializer,
)
from tasks.jobs import (
    approve_brand_submission,
    reject_brand_submission,
    manual_approve,
    manual_reject,
)

# Third party imports.
from rest_framework import generics, status, exceptions
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination

import rest_framework.serializers as s
from drf_spectacular.utils import extend_schema, inline_serializer

from accounts.models import User, AccountType, UserNotification
from commons import is_slot_target_reached
from permissions import (
    IsNotDisabled,
    IsAdAdminOrSuperAdmin,
)
from security import encrypt, decrypt

logger = logging.getLogger(__name__)


class PaginationStyle(PageNumberPagination):
    page_size = 10


@extend_schema(
    summary="Restrict a BrandAd account",
    tags=["Brand Ads"],
    description="Places spending and posting restrictions on a BrandAd account. Requires the admin's PIN for confirmation.",
    request=RestrictBrandAdSerializers,
    responses={
        200: inline_serializer(
            "RestrictBrandAdResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        401: inline_serializer(
            "RestrictBrandAdUnauthorized",
            fields={"status": s.CharField(), "error": s.CharField()},
        ),
    },
)
class RestrictBrandAdAccountView(generics.CreateAPIView):
    """
    RestrictBrandAdAccount is the POST requests that handles the
    restricting of brand Ads accounts.
    """

    serializer_class = RestrictBrandAdSerializers
    permission_classes = (IsAuthenticated, IsNotDisabled, IsAdAdminOrSuperAdmin)

    def post(self, request, *args, **kwargs):
        user_id = kwargs.get("brand_id")

        try:
            logger.info(
                f"Received request to restrict BrandAd account for user_id: {user_id}. Initiated by admin: {request.user.id}."
            )

            brand_ad = User.objects.get(id=user_id)
            logger.info(f"Successfully retrieved User object for user_id: {user_id}.")

            is_brandAd = AccountType.objects.filter(
                user=brand_ad, user_type="BrandAd"
            ).exists()
            logger.debug(
                f"BrandAd account type check for user_id {user_id}: {is_brandAd}."
            )
            if not is_brandAd:
                logger.warning(
                    f"User with id {user_id} is not registered as a BrandAd."
                )
                raise exceptions.ValidationError("User is not registered as a BrandAd.")

            decrypted_payload = decrypt(request.data)
            serializer = self.get_serializer(data=decrypted_payload)
            if serializer.is_valid(raise_exception=True):
                logger.info(
                    f"Serializer validation successful for user_id: {user_id}. Data: {serializer.validated_data}"
                )

                pin = serializer.validated_data.get("pin")
                if check_password(password=pin, encoded=request.user.admin_pin):
                    logger.info(
                        f"Pin verification successful for admin: {request.user.id}."
                    )

                    brand_account = RestrictBrandAdAccount.objects.create(
                        user=brand_ad,
                        reason=decrypted_payload.get("reason"),
                        minimum_debit=decrypted_payload.get("minimum_debit"),
                        maximum_debit=decrypted_payload.get("maximum_debit"),
                        post_per_day=decrypted_payload.get("post_per_day"),
                    )
                    logger.info(
                        f"Restricted BrandAd account created for user_id: {user_id}. ID: {brand_account.id}."
                    )

                    # Set the is_restricted flag to true.
                    brand_account.is_restricted = True
                    brand_account.save()
                    logger.info(
                        f"BrandAd account restriction flag set to True for user_id: {user_id}."
                    )

                    # Register Admin activity.
                    ActivityModel.objects.create(
                        user=request.user,
                        title="Restrict Admin.",
                        description=f"Brand, {brand_account.firstname} has been restricted by {request.user.full_name}.",
                    )
                    logger.info(
                        f"Admin activity logged for user_id: {request.user.id}."
                    )

                    reason = decrypted_payload.get("reason")
                    UserNotification.objects.create(
                        user=brand_account.user,
                        title="Restrict Account.",
                        message=f"Your account has been restricted for this reason: {reason}.",
                    )
                    logger.info(
                        f"Notification sent to user_id: {user_id} about account restriction."
                    )

                    return Response(
                        data=encrypt(
                            {
                                "status": "success",
                                "message": "BrandAd account restricted successfully.",
                                "data": {
                                    "restricted_account_id": brand_account.id,
                                    "user_detail": serializer.data,
                                },
                            }
                        ),
                        status=status.HTTP_200_OK,
                    )
                else:
                    logger.warning(
                        f"Pin verification failed for admin: {request.user.id}."
                    )
                    return Response(
                        data=encrypt({"status": "fail", "error": "Incorrect pin"}),
                        status=status.HTTP_401_UNAUTHORIZED,
                    )

        except User.DoesNotExist:
            logger.error(f"User with id {user_id} does not exist.")
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "User does not exist.",
                    }
                ),
                status=status.HTTP_404_NOT_FOUND,
            )
        except exceptions.ValidationError as ve:
            logger.warning(
                f"Validation error while processing request for user_id: {user_id}. Error: {ve}"
            )
            return Response(
                data=encrypt({"status": "fail", "message": str(ve)}),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            logger.exception(
                f"Unexpected error occurred while processing request for user_id: {user_id}."
            )
            return Response(
                data=encrypt(
                    {"status": "fail", "message": f"An unexpected error occurred.{e}"}
                ),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


@extend_schema(
    summary="List all BrandAd users (admin view)",
    tags=["Brand Ads"],
    description="Returns a paginated list of all registered BrandAd users with their ad and social profile details.",
    responses={200: ListBrandAdSerializer(many=True)},
)
class GetAllBrandAdUsers(generics.ListAPIView):
    """
    GetAllBrandAdUsers is the GET request to retrieve the count
    of all brandad users.
    """

    queryset = User.objects.all()
    serializer_class = ListBrandAdSerializer
    permission_classes = (IsAuthenticated, IsNotDisabled, IsAdAdminOrSuperAdmin)
    pagination_class = PaginationStyle

    def get_queryset(self):
        return (
            CreateAd.objects.filter(user__account_types__user_type="BrandAd")
            .select_related("user")
            .prefetch_related("brand_location", "user__account_types")
            .distinct()
        )

    def list(self, request, *args, **kwargs):
        cache_key = "brandad_users_list"

        # ✅ check cache
        cached_response = cache.get(cache_key)
        if cached_response:
            return Response(data=encrypt(cached_response), status=status.HTTP_200_OK)

        queryset = self.get_queryset()
        total_count = queryset.count()

        page = self.paginate_queryset(queryset)
        if page is not None:
            serialized_users = self.get_serializer(page, many=True)
        else:
            serialized_users = self.get_serializer(queryset, many=True)

        response_data = {
            "status": "success",
            "message": "All brand advert users retrieved successfully.",
            "No of BrandAd Users": total_count,
            "BrandAd user object": serialized_users.data,
        }

        # ✅ save to cache (short TTL)
        cache.set(cache_key, response_data, timeout=300)

        return Response(data=encrypt(response_data), status=status.HTTP_200_OK)


@extend_schema(
    summary="Get ad statistics for a BrandAd user",
    tags=["Brand Ads"],
    description="Returns aggregated ad statistics (total, active, completed) and graph data for a specific BrandAd user.",
    responses={
        200: inline_serializer(
            "AdStatsResponse",
            fields={
                "status": s.CharField(),
                "data": s.DictField(),
                "graph": s.DictField(),
            },
        ),
    },
)
class AdStatsView(generics.RetrieveAPIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request, user_id, *args, **kwargs):
        try:
            cache_key = f"ad_stats_{user_id}"

            cached_data = cache.get(cache_key)
            if cached_data:
                return Response(encrypt(cached_data), status=status.HTTP_200_OK)

            stats = CreateAd.objects.filter(user_id=user_id).aggregate(
                total=Count("id"),
                active=Count("id", filter=Q(is_active=True)),
                completed=Count("id", filter=Q(is_active=False)),
            )
            ad_requests = stats["total"]
            active_ads = stats["active"]
            completed_ads = stats["completed"]

            # If no extra status field exists,

            graph_data = {
                "labels": [
                    "Ad Requests",
                    "Active Ads",
                ],
                "values": [
                    ad_requests,
                    active_ads,
                ],
            }

            data = {
                "status": "success",
                "message": "All brand advert details retrieved successfully.",
                "data": {
                    "No of ad requests": ad_requests,
                    "No of active_ads": active_ads,
                    "No of completed_ads": completed_ads,
                },
                "graph": graph_data,
            }

            cache.set(cache_key, data, timeout=300)

            return Response(encrypt(data), status=status.HTTP_200_OK)

        except Exception as e:
            logger.error("Error fetching ad statistics: %s", str(e), exc_info=True)
            return Response(
                encrypt({"error": "Could not fetch ad statistics"}),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


@extend_schema(
    summary="[Admin] List all brand campaigns, optionally filtered by task type",
    tags=["Brand Ads"],
    description="Admin view returning all ad campaigns across all brands with optional filtering by task_type and is_active query params.",
    responses={200: AdSerializers(many=True)},
)
class ListAllCampaignsAdminView(generics.ListAPIView):
    """
    Admin view: list every ad campaign across all brands.
    Supports ?task_type= and ?is_active= query params.
    """

    serializer_class = AdSerializers
    permission_classes = (IsAuthenticated, IsAdAdminOrSuperAdmin)
    pagination_class = PaginationStyle

    def get_queryset(self):
        qs = (
            CreateAd.objects.select_related("user")
            .prefetch_related("brand_location", "ad_media")
            .order_by("-created_at")
        )
        task_type = self.request.query_params.get("task_type")
        is_active = self.request.query_params.get("is_active")

        if task_type:
            qs = qs.filter(task_type=task_type)
        if is_active is not None:
            qs = qs.filter(is_active=is_active.lower() == "true")

        return qs

    def list(self, request, *args, **kwargs):
        logger.info(
            "ListAllCampaignsAdminView accessed by admin: %s", request.user.email
        )

        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        serializer = (
            self.get_serializer(page, many=True)
            if page is not None
            else self.get_serializer(queryset, many=True)
        )

        response_data = {
            "status": "success",
            "message": "Campaigns retrieved successfully.",
            "total": queryset.count(),
            "data": serializer.data,
        }

        return Response(data=encrypt(response_data), status=status.HTTP_200_OK)


@extend_schema(
    summary="[Admin] List all brand task submissions with optional status filter",
    tags=["Brand Ads"],
    description="Admin view returning all BrandTaskSubmissions across all campaigns. Supports ?status= (Pending/Approved/Rejected) and ?task_type= filters.",
    responses={200: BrandTaskSubmissionSerializer(many=True)},
)
class ListBrandSubmissionsAdminView(generics.ListAPIView):
    """
    Admin view: list all BrandTaskSubmissions across all campaigns.
    Supports ?status= (Pending/Approved/Rejected) and ?task_type= filters.
    """

    serializer_class = BrandTaskSubmissionSerializer
    permission_classes = (IsAuthenticated, IsAdAdminOrSuperAdmin)
    pagination_class = PaginationStyle

    def get_queryset(self):
        qs = BrandTaskSubmission.objects.select_related(
            "ad", "user", "reviewed_by"
        ).order_by("-created_at")
        submission_status = self.request.query_params.get("status")
        task_type = self.request.query_params.get("task_type")

        if submission_status:
            qs = qs.filter(status=submission_status)
        if task_type:
            qs = qs.filter(ad__task_type=task_type)

        return qs

    def list(self, request, *args, **kwargs):
        logger.info(
            "ListBrandSubmissionsAdminView accessed by admin: %s", request.user.email
        )

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
            "total": queryset.count(),
            "data": serializer.data,
        }

        return Response(data=encrypt(response_data), status=status.HTTP_200_OK)


@extend_schema(
    summary="[Admin] Combined pending queue — social and brand task submissions",
    tags=["Brand Ads"],
    description="Returns all pending social task submissions and brand task submissions in a single response for the admin review queue.",
    responses={
        200: inline_serializer(
            "PendingSubmissionsResponse",
            fields={
                "status": s.CharField(),
                "social": s.DictField(),
                "brand": s.DictField(),
            },
        ),
    },
)
class PendingSubmissionsAdminView(generics.GenericAPIView):
    permission_classes = (IsAuthenticated, IsAdAdminOrSuperAdmin)

    def get(self, request, *args, **kwargs):
        logger.info(
            "PendingSubmissionsAdminView accessed by admin: %s", request.user.email
        )

        social_qs = (
            TaskSubmission.objects.filter(status="Pending")
            .select_related("task", "user", "verification")
            .order_by("created_at")
        )
        brand_qs = (
            BrandTaskSubmission.objects.filter(status="Pending")
            .select_related("ad", "user")
            .order_by("created_at")
        )

        response_data = {
            "status": "success",
            "message": "Pending submissions retrieved successfully.",
            "social": {
                "total": social_qs.count(),
                "data": TaskSubmissionSerializer(social_qs, many=True).data,
            },
            "brand": {
                "total": brand_qs.count(),
                "data": BrandTaskSubmissionSerializer(brand_qs, many=True).data,
            },
        }

        return Response(data=encrypt(response_data), status=status.HTTP_200_OK)


@extend_schema(
    summary="[Admin] Approve or reject a task submission (social or brand)",
    tags=["Brand Ads"],
    description="Approve or reject a social or brand task submission by ID. The action is dispatched asynchronously via Celery.",
    request=AdminReviewSerializer,
    responses={
        200: inline_serializer(
            "ReviewTaskSubmissionResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        404: inline_serializer(
            "ReviewTaskSubmissionNotFound",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class ReviewTaskSubmissionAdminView(generics.GenericAPIView):
    permission_classes = (IsAuthenticated, IsAdAdminOrSuperAdmin)

    def post(self, request, submission_id, *args, **kwargs):
        decrypted_data = decrypt(request.data)
        serializer = AdminReviewSerializer(data=decrypted_data)
        serializer.is_valid(raise_exception=True)

        action = serializer.validated_data["action"]
        reason = serializer.validated_data.get("reason", "")

        submission = None
        submission_type = None

        try:
            submission = TaskSubmission.objects.select_related("task", "user").get(
                pk=submission_id
            )
            submission_type = "social"
        except TaskSubmission.DoesNotExist:
            pass

        if submission is None:
            try:
                submission = BrandTaskSubmission.objects.select_related(
                    "ad", "user"
                ).get(pk=submission_id)
                submission_type = "brand"
            except BrandTaskSubmission.DoesNotExist:
                pass

        if submission is None:
            return Response(
                data=encrypt({"status": "fail", "message": "Submission not found."}),
                status=status.HTTP_404_NOT_FOUND,
            )

        if submission_type == "social":
            if action == "approve":
                manual_approve.delay(str(submission.pk), str(request.user.pk))
            else:
                manual_reject.delay(str(submission.pk), str(request.user.pk), reason)
            label = submission.task.title
        else:
            if action == "approve":
                approve_brand_submission.delay(str(submission.pk), str(request.user.pk))
            else:
                reject_brand_submission.delay(
                    str(submission.pk), str(request.user.pk), reason
                )
            label = submission.ad.campaign_name

        ActivityModel.objects.create(
            user=request.user,
            title="Task Submission Review",
            description=(
                f"{request.user.full_name} {action}d {submission_type} submission "
                f"for '{label}'."
            ),
        )

        logger.info(
            "Admin %s %sd %s submission %s.",
            request.user.email,
            action,
            submission_type,
            submission.pk,
        )

        return Response(
            data=encrypt(
                {
                    "status": "success",
                    "message": f"Submission queued for {action}.",
                }
            ),
            status=status.HTTP_200_OK,
        )


# ── Brand Task admin views
@extend_schema(
    summary="[Admin] List all brand ad tasks with summary stats",
    tags=["Brand Ads"],
    description="Returns active/expired task counts, pending verification requests, and a paginated task card list. Supports ?status= and ?task_type= filters.",
    responses={
        200: inline_serializer(
            "BrandTaskListResponse",
            fields={
                "status": s.CharField(),
                "stats": s.DictField(),
                "total": s.IntegerField(),
                "data": s.ListField(),
            },
        ),
    },
)
class BrandTaskListAdminView(generics.GenericAPIView):
    """
    GET /v1/roles/brands/tasks/
    Returns summary stats + paginated list of brand ad tasks.
    Supports ?status=active|expired and ?task_type= filters.
    """

    permission_classes = (IsAuthenticated, IsAdAdminOrSuperAdmin)
    pagination_class = PaginationStyle

    def get(self, request):
        now = timezone.now()
        status_filter = request.query_params.get("status")
        task_type = request.query_params.get("task_type")

        qs = CreateAd.objects.select_related("user").prefetch_related(
            "ad_media", "brand_submissions"
        )

        if task_type:
            qs = qs.filter(task_type=task_type)
        if status_filter == "active":
            qs = qs.filter(is_active=True, expiry_date__gt=now)
        elif status_filter == "expired":
            qs = qs.filter(Q(is_active=False) | Q(expiry_date__lte=now))

        active_count = CreateAd.objects.filter(
            is_active=True, expiry_date__gt=now
        ).count()
        expired_count = CreateAd.objects.filter(
            Q(is_active=False) | Q(expiry_date__lte=now)
        ).count()
        verification_request_count = BrandTaskSubmission.objects.filter(
            status="Pending"
        ).count()

        page = self.paginate_queryset(qs.order_by("-created_at"))
        items = page if page is not None else qs.order_by("-created_at")

        task_cards = []
        for ad in items:
            media = ad.ad_media.first()
            pending = ad.brand_submissions.filter(status="Pending").count()
            days_left = max(0, (ad.expiry_date - now).days) if ad.expiry_date else None
            task_cards.append(
                {
                    "id": ad.id,
                    "task_name": ad.task_name,
                    "task_description": ad.task_description,
                    "task_type": ad.task_type,
                    "task_type_display": (
                        ad.get_task_type_display() if ad.task_type else None
                    ),
                    "brand_objective": ad.brand_objective,
                    "reward_points": ad.reward_points,
                    "slot_cap": ad.slot_cap,
                    "slots_filled": ad.slots_filled,
                    "slots_remaining": (
                        max(0, ad.slot_cap - ad.slots_filled) if ad.slot_cap else None
                    ),
                    "days_left": days_left,
                    "created_at": ad.created_at,
                    "thumbnail": media.images or media.videos if media else None,
                    "verification_request_count": pending,
                    "is_active": ad.is_active,
                }
            )

        return Response(
            data=encrypt(
                {
                    "status": "success",
                    "stats": {
                        "active_tasks": active_count,
                        "expired_tasks": expired_count,
                        "verification_requests": verification_request_count,
                    },
                    "total": qs.count(),
                    "data": task_cards,
                }
            ),
            status=status.HTTP_200_OK,
        )


@extend_schema(
    summary="[Admin] Get full detail for a brand ad task",
    tags=["Brand Ads"],
    description="Returns complete task info, performance breakdown, demographic split, and pending verification requests for a single brand ad task.",
    responses={
        200: inline_serializer(
            "BrandTaskDetailResponse",
            fields={
                "status": s.CharField(),
                "data": s.DictField(),
                "performance_breakdown": s.DictField(),
                "verification_requests": s.DictField(),
            },
        ),
        404: inline_serializer(
            "BrandTaskDetailNotFound",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class BrandTaskDetailAdminView(generics.GenericAPIView):
    """
    GET /v1/roles/brands/tasks/<ad_id>/
    Full task detail: info, performance breakdown, demographic, verification requests.
    """

    permission_classes = (IsAuthenticated, IsAdAdminOrSuperAdmin)

    def get(self, request, ad_id):
        try:
            ad = (
                CreateAd.objects.select_related("user")
                .prefetch_related(
                    "ad_media", "brand_location", "brand_submissions__user"
                )
                .get(id=ad_id)
            )
        except CreateAd.DoesNotExist:
            return Response(
                data=encrypt({"status": "fail", "message": "Brand task not found."}),
                status=status.HTTP_404_NOT_FOUND,
            )

        # Submissions
        approved_submissions = ad.brand_submissions.filter(status="Approved")
        pending_submissions = ad.brand_submissions.filter(status="Pending")

        approved_count = approved_submissions.count()
        total_points_rewarded = approved_count * (ad.reward_points or 0)
        budget_spent = Decimal(str(ad.amount or 0))

        # ── Performance demographic from approved participants' profiles ───────
        from django.db.models import Count as DjCount

        # User model has no gender/demography fields; return empty breakdowns
        gender_counts = {}
        demography_counts = {}

        # State-level breakdown from participants' locations
        state_counts = (
            approved_submissions.select_related("user")
            .values("user__state")
            .annotate(count=DjCount("id"))
            .order_by("-count")
        )

        # Media
        media = [{"images": m.images, "videos": m.videos} for m in ad.ad_media.all()]
        locations = [
            {"state": loc.state, "city": loc.city} for loc in ad.brand_location.all()
        ]

        # Verification request list
        verification_requests = [
            {
                "submission_id": str(sub.pk),
                "user_email": sub.user.email,
                "screenshot_url": sub.screenshot_url,
                "submitted_at": sub.created_at,
            }
            for sub in pending_submissions.select_related("user")
        ]

        now = timezone.now()
        days_left = max(0, (ad.expiry_date - now).days) if ad.expiry_date else None
        duration_days = int(ad.campaign_duration) if ad.campaign_duration else None
        is_completed = is_slot_target_reached(ad.slot_cap, ad.slots_filled)

        return Response(
            data=encrypt(
                {
                    "status": "success",
                    "data": {
                        "id": ad.id,
                        "task_name": ad.task_name,
                        "task_description": ad.task_description,
                        "task_type": ad.task_type,
                        "task_type_display": (
                            ad.get_task_type_display() if ad.task_type else None
                        ),
                        "brand_name": ad.business_or_brand_name,
                        "business_type": ad.type_of_business,
                        "industry": ad.industry,
                        "brand_objective": ad.brand_objective,
                        "user_action": ad.engagement_type,
                        "comment_prompt": (
                            ad.task_details.get("comment_prompt")
                            if ad.task_details
                            else None
                        ),
                        "timing": (
                            ad.task_details.get("timing") if ad.task_details else None
                        ),
                        "auto_boost": ad.auto_boost,
                        "auto_boost_points": ad.auto_boost_points,
                        "reward_points": ad.reward_points,
                        "slot_cap": ad.slot_cap,
                        "slots_filled": ad.slots_filled,
                        "slots_remaining": (
                            max(0, ad.slot_cap - ad.slots_filled)
                            if ad.slot_cap
                            else None
                        ),
                        "duration_days": duration_days,
                        "days_left": days_left,
                        "is_completed": bool(is_completed),
                        "is_active": ad.is_active,
                        "brand_socials": ad.brand_socials,
                        "ad_media": media,
                        "brand_location": locations,
                        "created_at": ad.created_at,
                    },
                    "performance_breakdown": {
                        "campaign_budget": ad.amount,
                        "budget_spent": str(budget_spent),
                        "ads_credit": str(ad.ads_credit),
                        "total_points_rewarded": total_points_rewarded,
                        "points_reward_per_person": ad.reward_points,
                        "auto_boost_points": ad.auto_boost_points,
                    },
                    "performance_demographic": {
                        "by_gender": dict(gender_counts),
                        "by_demography": dict(demography_counts),
                        "by_state": list(state_counts),
                    },
                    "verification_requests": {
                        "total": pending_submissions.count(),
                        "data": verification_requests,
                    },
                }
            ),
            status=status.HTTP_200_OK,
        )


@extend_schema(
    summary="[Admin] Boost reward points for a brand ad task",
    tags=["Brand Ads"],
    description="Increases the reward_points for a brand ad task by a specified amount and records the boost in auto_boost_points.",
    request=inline_serializer(
        "BoostTaskPointsRequest", fields={"amount": s.IntegerField()}
    ),
    responses={
        200: inline_serializer(
            "BoostTaskPointsResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "data": s.DictField(),
            },
        ),
        400: inline_serializer(
            "BoostTaskPointsError",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class BoostTaskPointsView(generics.GenericAPIView):
    """
    POST /v1/roles/brands/tasks/<ad_id>/boost-points/
    Increases reward_points for an ad by the given amount and tracks it in auto_boost_points.
    """

    permission_classes = (IsAuthenticated, IsAdAdminOrSuperAdmin)

    def post(self, request, ad_id):
        try:
            ad = CreateAd.objects.get(id=ad_id)
        except CreateAd.DoesNotExist:
            return Response(
                data=encrypt({"status": "fail", "message": "Brand task not found."}),
                status=status.HTTP_404_NOT_FOUND,
            )

        payload = decrypt(request.data)
        boost_amount = payload.get("amount")

        try:
            boost_amount = int(boost_amount)
            if boost_amount <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return Response(
                data=encrypt(
                    {"status": "fail", "message": "amount must be a positive integer."}
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        ad.reward_points = (ad.reward_points or 0) + boost_amount
        ad.auto_boost_points += boost_amount
        ad.save(update_fields=["reward_points", "auto_boost_points"])

        logger.info(
            "Admin %s boosted task %s by %d pts (new reward: %d)",
            request.user.email,
            ad_id,
            boost_amount,
            ad.reward_points,
        )

        return Response(
            data=encrypt(
                {
                    "status": "success",
                    "message": f"Points boosted by {boost_amount}.",
                    "data": {
                        "reward_points": ad.reward_points,
                        "auto_boost_points": ad.auto_boost_points,
                    },
                }
            ),
            status=status.HTTP_200_OK,
        )
