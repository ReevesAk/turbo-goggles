import logging

from django.contrib.auth.hashers import check_password
from django.db.models import Q
from django.core.cache import cache

# In project imports.
from .serializers import (
    ListPartnerUsersSerializer,
    RestrictPartnersSerializers,
)
from .views import PaginationStyle
from .models import RestrictPartnerAccount, ActivityModel
from partners.serializers import PartnerServiceSerializer, PartnerProfileSerializer
from partners.models import PartnerServices

# Third party imports.
from rest_framework import generics, status, exceptions
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication

from drf_spectacular.utils import extend_schema

from accounts.models import User, AccountType, UserNotification
from permissions import IsNotDisabled, IsPartnerAdminOrSuperAdmin

from security import encrypt, decrypt

logger = logging.getLogger(__name__)


@extend_schema(summary="List all partner users", tags=["Partner Services"])
class GetAllPartnersUsers(generics.ListAPIView):
    """
    GetAllAdminUsers is the GET request to retrieve the count
    of all admin users.
    """

    queryset = User.objects.all()
    serializer_class = ListPartnerUsersSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsPartnerAdminOrSuperAdmin, IsNotDisabled)
    pagination_class = PaginationStyle

    def get_queryset(self):
        partners = User.objects.filter(account_types__user_type="Partner").distinct()
        return partners

    def list(self, request, *args, **kwargs):
        cache_key = "all_partner_users"
        cached_response = cache.get(cache_key)

        if cached_response:
            logger.info("Returning cached partner users list")
            return Response(data=encrypt(cached_response), status=status.HTTP_200_OK)

        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)

        if page is not None:
            serialized_users = self.get_serializer(page, many=True)
            response_data = {
                "status": "success",
                "message": "All partner users retrieved successfully",
                "No of Partner Users": queryset.count(),
                "Partners user object": serialized_users.data,
            }
        else:
            response_data = {
                "status": "success",
                "message": "No partner users found.",
                "No of Partner Users": 0,
                "Partners user object": [],
            }

        # Save to cache (short TTL)
        cache.set(cache_key, response_data, timeout=300)  # 5 minutes
        return Response(data=encrypt(response_data), status=status.HTTP_200_OK)


@extend_schema(summary="Restrict a partner account", tags=["Partner Services"])
class RestrictPartnerAccountView(generics.CreateAPIView):
    """
    RestrictPartnerAccount is the POST requests that handles the
    restricting of partner accounts.
    """

    serializer_class = RestrictPartnersSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsNotDisabled, IsPartnerAdminOrSuperAdmin)

    def post(self, request, *args, **kwargs):
        user_id = kwargs.get("partner_id")

        try:
            logger.info(
                f"Received request to restrict partner account for user_id: {user_id} by admin: {request.user.id}"
            )

            partner = User.objects.get(id=user_id)
            logger.info(f"Successfully retrieved User object for user_id: {user_id}")

            account_types = AccountType.objects.filter(user=partner)
            logger.debug(f"Account types for user_id {user_id}: {account_types}")

            # Check if any AccountType has "Partner" in user_type
            is_partner = any(acct.user_type == "Partner" for acct in account_types)
            if not is_partner:
                logger.warning(
                    f"User with id {user_id} is not registered as a partner."
                )
                raise exceptions.ValidationError("User is not registered as a partner.")

            decrypted_payload = decrypt(request.data)
            serializer = self.get_serializer(data=decrypted_payload)
            if serializer.is_valid(raise_exception=True):
                logger.info(
                    f"Serializer validation successful for user_id: {user_id}. Data: {serializer.validated_data}"
                )

                pin = serializer.validated_data.get("pin")
                if check_password(password=pin, encoded=request.user.admin_pin):
                    logger.info(
                        f"Pin verification successful for admin: {request.user.id}"
                    )

                    partner_account = RestrictPartnerAccount.objects.create(
                        user=partner,
                        reason=request.data.get("reason"),
                        minimum_debit=request.data.get("minimum_debit"),
                        maximum_debit=request.data.get("maximum_debit"),
                        post_per_day=request.data.get("post_per_day"),
                    )
                    logger.info(
                        f"Created restricted partner account for user_id: {user_id}, ID: {partner_account.id}"
                    )

                    # Set the is_restricted flag to true
                    partner_account.is_restricted = True
                    partner_account.save()
                    logger.info(
                        f"Set is_restricted flag to True for user_id: {user_id}"
                    )

                    authenticated_user = request.user
                    user_name = (
                        "Superuser"
                        if authenticated_user.active_role == "Superuser"
                        else (
                            authenticated_user.full_name
                            if authenticated_user.active_role
                            in {
                                "SuperAdmin",
                                "TaskAdmin",
                                "AdAdmin",
                                "MembersAdmin",
                                "UserAdmin",
                                "PartnersAdmin",
                                "ContentAdmin",
                                "IntegrationAdmin",
                                "WalletAdmin",
                                "FmcgAdmin",
                            }
                            else "Unknown"
                        )
                    )

                    # Register Admin activity
                    ActivityModel.objects.create(
                        user=request.user,
                        title="Restrict Admin.",
                        description=f"Partner, {partner.firstname} has been restricted by {user_name}.",
                    )
                    logger.info(
                        f"Admin activity logged for user_id: {user_id} by admin: {request.user.id}"
                    )

                    reason = request.data.get("reason")
                    UserNotification.objects.create(
                        user=partner,
                        title="Restrict Account.",
                        message=f"Your account has been restricted for this reason: {reason}.",
                    )
                    logger.info(
                        f"Notification sent to user_id: {user_id} about account restriction"
                    )

                    return Response(
                        data=encrypt(
                            {
                                "status": "success",
                                "message": "Partner account restricted successfully.",
                                "data": {
                                    "restricted_account_id": partner_account.id,
                                    "user_detail": serializer.data,
                                },
                            }
                        ),
                        status=status.HTTP_200_OK,
                    )
                else:
                    logger.warning(
                        f"Pin verification failed for admin: {request.user.id}"
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
            logger.warning(f"Validation error for user_id: {user_id}. Error: {ve}")
            return Response(
                data=encrypt({"status": "fail", "message": str(ve)}),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            logger.exception(
                f"Unexpected error occurred while processing request for user_id: {user_id}."
            )
            return Response(
                data=encrypt({"status": "error", "message": "An unexpected error occurred. Please try again."}),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


@extend_schema(
    summary="List all services for a partner (admin view)", tags=["Partner Services"]
)
class AdminViewPartnerServiceList(generics.ListAPIView):
    """AdminViewPartnerServiceList lists all the services belonging to
    Partner whose email is passed in params.
    """

    serializer_class = PartnerServiceSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsNotDisabled, IsPartnerAdminOrSuperAdmin)
    pagination_class = PaginationStyle

    def get_queryset(self):
        email = self.kwargs.get("partner_email")
        if not email:
            return None  # Returning None if email is missing

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return None  # Returning None if user doesn't exist

        return PartnerServices.objects.filter(user=user).order_by("created_at")

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()

        # Check for missing email or non-existent user
        if queryset is None:
            email = self.kwargs.get("partner_email")
            error_message = (
                "Email parameter is required"
                if not email
                else "User with the provided email does not exist."
            )
            return Response(
                data=encrypt({"status": "fail", "error": error_message}),
                status=(
                    status.HTTP_400_BAD_REQUEST
                    if not email
                    else status.HTTP_404_NOT_FOUND
                ),
            )

        # Serialize and respond with the queryset data
        serializer = self.serializer_class(queryset, many=True)
        return Response(
            data=encrypt(
                {
                    "status": "success",
                    "message": "Services retrieved successfully.",
                    "data": serializer.data,
                }
            ),
            status=status.HTTP_200_OK,
        )


@extend_schema(
    summary="Search partners by name, category, or business name",
    tags=["Partner Services"],
)
class PartnerSearch(generics.ListAPIView):
    """
    PartnerSearch handles the GET request for searching
    partners by business name, category, or partner name.
    Only users with the user_type 'Partner' are considered.
    """

    serializer_class = PartnerProfileSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        search_term = kwargs.get("search_term")
        logger.info(f"Received search request for term: {search_term}")

        try:
            # Filter users who have user_type as 'Partner'
            partners = User.objects.filter(
                Q(accounttype__user_type="Partner")
                & (
                    Q(business_name__icontains=search_term)
                    | Q(brand_name__icontains=search_term)
                    | Q(business_category__icontains=search_term)
                    | Q(full_name__icontains=search_term)
                )
            ).distinct()

            serializer = self.get_serializer(partners, many=True)

            if partners.exists():
                data = {
                    "status": "success",
                    "message": "Partners fetched successfully.",
                    "data": serializer.data,
                }
                logger.info(
                    f"Found {partners.count()} partners matching the search term: {search_term}"
                )
                return Response(data=encrypt(data), status=status.HTTP_200_OK)
            else:
                data = {
                    "status": "fail",
                    "message": "No partners matching that query found.",
                    "data": [],
                }
                logger.warning(
                    f"No partners found matching the search term: {search_term}"
                )
                return Response(data=encrypt(data), status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            logger.exception(f"Error occurred while searching for partners: {e}")
            return Response(
                data=encrypt(
                    {
                        "status": "error",
                        "message": "An error occurred while processing the request.",
                    }
                ),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
