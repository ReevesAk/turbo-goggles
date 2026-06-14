import logging

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
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.pagination import PageNumberPagination

from drf_spectacular.utils import extend_schema

from accounts.models import User, AccountType, UserNotification
from permissions import (
    IsNotDisabled,
    IsAdAdminOrSuperAdmin,
)
from security import encrypt, decrypt

logger = logging.getLogger(__name__)


class PaginationStyle(PageNumberPagination):
    page_size = 10


@extend_schema(summary="Restrict a BrandAd account", tags=["Brand Ads"])
class RestrictBrandAdAccountView(generics.CreateAPIView):
    """
    RestrictBrandAdAccount is the POST requests that handles the
    restricting of brand Ads accounts.
    """

    serializer_class = RestrictBrandAdSerializers
    authentication_classes = [JWTAuthentication]
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
                        "status": "error",
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
                    {"status": "error", "message": f"An unexpected error occurred.{e}"}
                ),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


@extend_schema(summary="List all BrandAd users (admin view)", tags=["Brand Ads"])
class GetAllBrandAdUsers(generics.ListAPIView):
    """
    GetAllBrandAdUsers is the GET request to retrieve the count
    of all brandad users.
    """

    queryset = User.objects.all()
    serializer_class = ListBrandAdSerializer
    authentication_classes = [JWTAuthentication]
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


@extend_schema(summary="Get ad statistics for a BrandAd user", tags=["Brand Ads"])
class AdStatsView(generics.RetrieveAPIView):
    authentication_classes = [JWTAuthentication]
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
)
class ListAllCampaignsAdminView(generics.ListAPIView):
    """
    Admin view: list every ad campaign across all brands.
    Supports ?task_type= and ?is_active= query params.
    """

    serializer_class = AdSerializers
    authentication_classes = [JWTAuthentication]
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
)
class ListBrandSubmissionsAdminView(generics.ListAPIView):
    """
    Admin view: list all BrandTaskSubmissions across all campaigns.
    Supports ?status= (Pending/Approved/Rejected) and ?task_type= filters.
    """

    serializer_class = BrandTaskSubmissionSerializer
    authentication_classes = [JWTAuthentication]
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
    tags=["Task Review"],
)
class PendingSubmissionsAdminView(generics.GenericAPIView):
    authentication_classes = [JWTAuthentication]
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
    tags=["Task Review"],
)
class ReviewTaskSubmissionAdminView(generics.GenericAPIView):
    authentication_classes = [JWTAuthentication]
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
