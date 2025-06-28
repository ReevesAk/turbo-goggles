import logging
from django.contrib.auth.hashers import check_password

# In project imports.
from .serializers import RestrictBrandAdSerializers, ListBrandAdSerializer
from .models import RestrictBrandAdAccount, ActivityModel
from adverts.models import AdBudget

# Third party imports.
from rest_framework import generics, status, exceptions
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.pagination import PageNumberPagination

from accounts.models import User, AccountType, UserNotification
from permissions import (
    IsNotDisabled,
    IsAdAdminOrSuperAdmin,
)
from security import encrypt, decrypt

logger = logging.getLogger(__name__)


class PaginationStyle(PageNumberPagination):
    page_size = 10


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

            account_types = AccountType.objects.filter(user=brand_ad)
            logger.debug(
                f"Retrieved account types for user_id: {user_id}: {account_types}."
            )

            # Check if any AccountType has "BrandAd" in user_type
            is_brandAd = any(acct.user_type == "BrandAd" for acct in account_types)
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
        brand = User.objects.filter(accounttype__user_type="BrandAd").distinct()
        return brand

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)

        if page is not None:
            serialized_users = self.get_serializer(page, many=True)
            return Response(
                data=(
                    {
                        "status": "success",
                        "message": "All brand advert users retrieved successfully.",
                        "No of BrandAd Users": queryset.count(),
                        "BrandAd user object": serialized_users.data,
                    }
                ),
                status=status.HTTP_200_OK,
            )


class AdStatsView(generics.RetrieveAPIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        try:
            # Raw counts
            ad_requests = AdBudget.objects.filter(has_made_request=True).count()
            active_ads = AdBudget.objects.filter(is_active_ad=True).count()
            completed_ads = AdBudget.objects.filter(is_completed=True).count()
            not_promoted = AdBudget.objects.filter(
                has_made_request=False, is_active_ad=False, is_completed=False
            ).count()

            # Graph-friendly format
            graph_data = {
                "labels": ["Ad Requests", "Active Ads", "Completed Ads", "Not Promoted"],
                "values": [ad_requests, active_ads, completed_ads, not_promoted],
            }

            # Full response
            data = {
                "status": "success",
                "message": "All brand advert details retrieved successfully.",
                "data": {
                    "No of ad requests": ad_requests,
                    "No of active_ads": active_ads,
                    "No of completed_ads": completed_ads,
                    "No of ads not promoted_yet": not_promoted,
                },
                "graph": graph_data,
            }

            return Response(encrypt(data), status=status.HTTP_200_OK)

        except Exception as e:
            logger.error("Error fetching ad statistics: %s", str(e), exc_info=True)
            return Response(
                encrypt({"error": "Could not fetch ad statistics"}),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
