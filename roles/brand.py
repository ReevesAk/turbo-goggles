from django.contrib.auth.hashers import check_password

# In project imports.
from .serializers import RestrictBrandAdSerializers, ListBrandAdSerializer
from .models import RestrictBrandAdAccount

# Third party imports.
from rest_framework import generics, status, exceptions
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.pagination import PageNumberPagination

from accounts.models import User, AccountType
from commons import CamelCaseJSONRenderer
from permissions import (
    IsSuperAdmin,
    IsNotDisabled,
    IsBrandAdAdmin,
    IsAdAdminOrSuperAdmin,
)


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
    renderer_classes = [CamelCaseJSONRenderer]

    def post(self, request, *args, **kwargs):
        user_id = kwargs.get("brand_id")

        try:
            brand_ad = User.objects.get(id=user_id)

            account_types = AccountType.objects.filter(user=brand_ad)
            # Check if any AccountType has "BrandAd" in user_type
            is_brandAd = any(acct.user_type == "BrandAd" for acct in account_types)

            if not is_brandAd:
                raise exceptions.ValidationError(
                    "User as not regsitered as a brand ad."
                )

            serializer = self.get_serializer(data=request.data)
            if serializer.is_valid(raise_exception=True):
                pin = serializer.validated_data.get("pin")
                if check_password(password=pin, encoded=request.user.admin_pin):
                    brand_account = RestrictBrandAdAccount.objects.create(
                        user=brand_ad,
                        reason=request.data.get("reason"),
                        minimum_debit=request.data.get("minimum_debit"),
                        maximum_debit=request.data.get("maximum_debit"),
                        post_per_day=request.data.get("post_per_day"),
                    )
                    # Set the is_restricted flag to true.
                    brand_account.is_restricted = True
                    brand_account.save()

                    return Response(
                        {
                            "status": "success",
                            "message": "BrandAd account restricted successfully.",
                            "data": {
                                "restricetd_account_id": brand_account.id,
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
    renderer_classes = [CamelCaseJSONRenderer]

    def get_queryset(self):
        partners = User.objects.filter(accounttype__user_type="BrandAd").distinct()
        return partners

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)

        if page is not None:
            serialized_users = self.get_serializer(page, many=True)
            return Response(
                data={
                    "status": "success",
                    "message": "All brand advert users retrieved successfully.",
                    "No of BrandAd Users": queryset.count(),
                    "BrandAd user object": serialized_users.data,
                },
                status=status.HTTP_200_OK,
            )
