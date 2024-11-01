from django.contrib.auth.hashers import check_password
from django.db.models import Q

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

from accounts.models import User, AccountType, UserNotification
from commons import CamelCaseJSONRenderer
from permissions import IsNotDisabled, IsPartnerAdminOrSuperAdmin


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
    renderer_classes = [CamelCaseJSONRenderer]

    def get_queryset(self):
        partners = User.objects.filter(accounttype__user_type="Partner").distinct()
        return partners

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)

        if page is not None:
            serialized_users = self.get_serializer(page, many=True)
            return Response(
                data={
                    "status": "success",
                    "message": "All partner users retrieved successfully",
                    "No of Partner Users": queryset.count(),
                    "Partners user object": serialized_users.data,
                },
                status=status.HTTP_200_OK,
            )


class RestrictPartnerAccountView(generics.CreateAPIView):
    """
    RestrictPartnerAccount is the POST requests that handles the
    restricting of partner accounts.
    """

    serializer_class = RestrictPartnersSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsNotDisabled, IsPartnerAdminOrSuperAdmin)
    # renderer_classes = [CamelCaseJSONRenderer]

    def post(self, request, *args, **kwargs):
        user_id = kwargs.get("partner_id")

        try:
            partner = User.objects.get(id=user_id)

            account_types = AccountType.objects.filter(user=partner)
            # Check if any AccountType has "Partner" in user_type
            is_partner = any(acct.user_type == "Partner" for acct in account_types)

            if not is_partner:
                raise exceptions.ValidationError("User is not regsitered as a partner.")

            serializer = self.get_serializer(data=request.data)
            if serializer.is_valid(raise_exception=True):
                pin = serializer.validated_data.get("pin")
                if check_password(password=pin, encoded=request.user.admin_pin):
                    partner_account = RestrictPartnerAccount.objects.create(
                        user=partner,
                        reason=request.data.get("reason"),
                        minimum_debit=request.data.get("minimum_debit"),
                        maximum_debit=request.data.get("maximum_debit"),
                        post_per_day=request.data.get("post_per_day"),
                    )
                    # Set the is_restricted flag to true.
                    partner_account.is_restricted = True
                    partner_account.save()

                    # Register Admin activity.
                    ActivityModel.objects.create(
                        user=request.user,
                        title="Restrict Admin.",
                        description=f"Partner, {partner.firstname} has been restricted by {request.user.full_name}.",
                    )

                    reason = (request.data.get("reason"),)
                    UserNotification.objects.create(
                        user=partner,
                        title="Restrict Account.",
                        message=f"Your account has been restricted for this reason: {reason}.",
                    )

                    return Response(
                        {
                            "status": "success",
                            "message": "Partner account restricted successfully.",
                            "data": {
                                "restricetd_account_id": partner_account.id,
                                "user_detail": serializer.data,
                            },
                        },
                        status=status.HTTP_200_OK,
                    )
                else:
                    return Response(
                        data={"status": "fail", "error": "Incorrect pin"},
                        status=status.HTTP_401_UNAUTHORIZED,
                    )

        except User.DoesNotExist:
            return Response(
                {
                    "status": "error",
                    "message": "User does not exist.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )


class AdminViewPartnerServiceList(generics.ListAPIView):
    """AdminViewPartnerServiceList lists all the services belonging to
    Partner whose email is passed in params.
    """

    serializer_class = PartnerServiceSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsNotDisabled, IsPartnerAdminOrSuperAdmin)
    pagination_class = PaginationStyle

    def get(self, request):
        email = request.query_params.get("partner_email")

        # Check if email is provided
        if not email:
            return Response(
                data={"status": "fail", "error": "Email parameter is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = User.objects.get(email=email)
        queryset = PartnerServices.objects.filter(user=user).order_by("created_at")
        return queryset

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.serializer_class(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.serializer_class(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


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

        # Filter users who have user_type as 'Partner'
        partners = User.objects.filter(
            Q(accounttype__user_type="Partner") &
            (
                Q(business_name__icontains=search_term) |
                Q(brand_name__icontains=search_term) |
                Q(business_category__icontains=search_term) |
                Q(full_name__icontains=search_term)
            )
        ).distinct()

        serializer = self.get_serializer(partners, many=True)

        if partners.exists():
            data = {
                "status": "success",
                "message": "Partners fetched successfully.",
                "data": serializer.data
            }
            return Response(data=data, status=status.HTTP_200_OK)
        else:
            data = {
                "status": "fail",
                "message": "No partners matching that query found.",
                "data": []
            }
            return Response(data=data, status=status.HTTP_404_NOT_FOUND)
