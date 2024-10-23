from django.template.loader import render_to_string
from commons import Message

# In project imports.
from .serializers import ListWalletUsersSerializer
from .views import PaginationStyle

# Third party imports.
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication

from banking.models import AccountCreation
from commons import CamelCaseJSONRenderer
from permissions import IsSuperAdmin, IsNotDisabled, IsWalletAdmin

from .models import ActivityModel


class GetallWalletUsers(generics.ListAPIView):
    """
    GetallWalletUsers is the GET request to retrieve the count
    of all wallet owners.
    """

    queryset = AccountCreation.objects.all().order_by("created_at")
    serializer_class = ListWalletUsersSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [
        IsAuthenticated,
        IsNotDisabled & (IsSuperAdmin | IsWalletAdmin),
    ]
    pagination_class = PaginationStyle
    renderer_classes = [CamelCaseJSONRenderer]

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)

        if page is not None:
            serialized_users = self.get_serializer(page, many=True)
            return self.get_paginated_response(
                {
                    "status": "success",
                    "message": "All Wallet owners retrieved successfully.",
                    "num_of_wallet_owners": queryset.count(),
                    "wallet_owners": serialized_users.data,
                }
            )

        # In case pagination is not used
        serialized_users = self.get_serializer(queryset, many=True)
        count = queryset.count()
        data = serialized_users.data
        body = f"This is to inform you that {count} users have opened an account with Picadailys and these are their details: {data}."
        print("I dey work")

        email_content = render_to_string(
            "email_template.html",
            {
                "email": "OGafekemor@picadailys.com",
                "picadailys_phone": "08134649680",
                "message_body": body,
            },
        )

        Message.send_email(
            content=email_content,
            email="akwareeves@gmail.com",
            subject="Testing Subject.",
        )

        return Response(
            {
                "status": "success",
                "message": "All Wallet owners retrieved successfully.",
                "num_of_wallet_owners": queryset.count(),
                "wallet_owners": serialized_users.data,
            },
            status=status.HTTP_200_OK,
        )
