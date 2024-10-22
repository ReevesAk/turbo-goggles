from django.contrib.auth.hashers import check_password

# In project imports.
from .serializers import (
    ListPartnerUsersSerializer,
    RestrictPartnersSerializers,
)
from .views import PaginationStyle
from .models import RestrictPartnerAccount

# Third party imports.
from rest_framework import generics, status, exceptions
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication

from accounts.models import User, AccountType
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
