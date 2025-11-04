import logging
import requests

from django.core.cache import cache

# In project imports.
from .serializers import ListWalletUsersSerializer
from .models import ActivityModel

# Third party imports.
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.parsers import MultiPartParser, JSONParser

from accounts.models import User, UserNotification
from banking.models import WalletModel, UserKYC
from banking.serializers import WalletStatusSerializer
from banking.controllers import Wallet, KYC
from permissions import IsNotDisabled, IsWalletAdminOrSuperAdmin
from security import encrypt


class GetallWalletUsers(generics.ListAPIView):
    """
    GetallWalletUsers is the GET request to retrieve the count
    of all wallet owners.
    """

    queryset = WalletModel.objects.all().order_by("created_at")
    serializer_class = ListWalletUsersSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [
        IsAuthenticated,
        IsNotDisabled,
        IsWalletAdminOrSuperAdmin,
    ]

    def list(self, request, *args, **kwargs):
        cache_key = "wallet_users_list"
        cached_response = cache.get(cache_key)

        if cached_response:
            return Response(encrypt(cached_response), status=status.HTTP_200_OK)

        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)

        if page is not None:
            serialized_users = self.get_serializer(page, many=True)
            data = {
                "status": "success",
                "message": "All Wallet owners retrieved successfully.",
                "num_of_wallet_owners": queryset.count(),
                "wallet_owners": serialized_users.data,
            }
            # Save to cache (short TTL)  # ✅ cache for 5 minutes
            return self.get_paginated_response(encrypt(data))

        serialized_users = self.get_serializer(queryset, many=True)
        data = {
            "status": "success",
            "message": "All Wallet owners retrieved successfully.",
            "num_of_wallet_owners": queryset.count(),
            "wallet_owners": serialized_users.data,
        }

        # Save to cache (short TTL)
        cache.set(cache_key, data, timeout=300)  # 5 minutes
        return Response(encrypt(data), status=status.HTTP_200_OK)


class WalletSearch(generics.ListAPIView):
    """
    WalletSearch handles the GET request of searching
    for results that matches the query.
    """

    serializer_class = WalletStatusSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [
        IsAuthenticated,
        IsNotDisabled,
        IsWalletAdminOrSuperAdmin,
    ]

    def get(self, request, *args, **kwargs):
        keyword = kwargs.get("search_term")

        if keyword.isdigit():
            accounts = WalletModel.objects.filter(account_number__icontains=keyword)
        # Otherwise, search by account name
        else:
            accounts = WalletModel.objects.filter(acct_name__icontains=keyword)

        serializer = self.get_serializer(accounts, many=True)
        response_data = {
            "status": "success" if accounts else "fail",
            "message": (
                "Wallet user fetched successfully."
                if accounts
                else "No user matching that query found."
            ),
            "data": serializer.data,
        }

        return Response(
            data=encrypt(response_data),
            status=status.HTTP_200_OK if accounts else status.HTTP_404_NOT_FOUND,
        )
