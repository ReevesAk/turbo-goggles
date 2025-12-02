import logging
from django.core.cache import cache
from django.contrib.auth.hashers import check_password
from django.db.models import Prefetch

# In project imports.
from .serializers import ListWalletUsersSerializer, ChangeWalletStatusSerializer

# Third party imports.
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication

from accounts.models import UserNotification, TxModel
from roles.models import ActivityModel
from banking.models import WalletModel
from banking.serializers import WalletStatusSerializer
from permissions import IsNotDisabled, IsWalletAdminOrSuperAdmin
from security import encrypt, decrypt

logger = logging.getLogger(__name__)


class GetallWalletUsers(generics.ListAPIView):
    """
    Retrieves all wallet users with their last 5 transactions.
    """

    serializer_class = ListWalletUsersSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [
        IsAuthenticated,
        IsNotDisabled,
        IsWalletAdminOrSuperAdmin,
    ]

    def get_queryset(self):
        """
        Prefetch last 5 transactions per user efficiently.
        No N+1 queries.
        """
        last_5_transactions = Prefetch(
            "user__txmodel_set",
            queryset=TxModel.objects.order_by("-date")[:5],
            to_attr="last_five_tx",
        )

        return (
            WalletModel.objects.select_related("user")
            .prefetch_related("user__kyc")
            .prefetch_related(last_5_transactions)
            .order_by("created_at")
        )

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
            # Cache for 5 minutes
            return self.get_paginated_response(encrypt(data))

        serialized_users = self.get_serializer(queryset, many=True)
        data = {
            "status": "success",
            "message": "All Wallet owners retrieved successfully.",
            "num_of_wallet_owners": queryset.count(),
            "wallet_owners": serialized_users.data,
        }

        # Cache for 5 minutes
        cache.set(cache_key, data, timeout=300)
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


class ChangeWalletStatusView(generics.RetrieveAPIView):
    """
    ChangeWalletStatusView handles the POST request to change the status of a wallet.
    """

    serializer_class = ChangeWalletStatusSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [
        IsAuthenticated,
        IsNotDisabled,
        IsWalletAdminOrSuperAdmin,
    ]

    def post(self, request, *args, **kwargs):
        decrypted_payload = decrypt(request.data)
        payload = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_payload.items()
        }
        account_number = payload.get("account_number")
        new_status = payload.get("status")
        pin = payload.get("pin")

        try:
            wallet = WalletModel.objects.get(account_number=account_number)
        except WalletModel.DoesNotExist:
            response_data = {
                "status": "fail",
                "message": "Wallet with that account number does not exist.",
            }
            return Response(
                data=encrypt(response_data),
                status=status.HTTP_404_NOT_FOUND,
            )

        if not check_password(password=pin, encoded=request.user.admin_pin):
            response_data = {
                "status": "fail",
                "message": "Incorrect pin!.",
            }
            return Response(
                data=encrypt(response_data),
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if wallet.status == new_status:
            logger.info(
                f"User wallet, {wallet.acct_name} with account number: {wallet.account_number} is already {new_status}."
            )
            response_data = {
                "status": "fail",
                "message": f"Wallet is already {new_status}.",
            }
            return Response(
                data=encrypt(response_data),
                status=status.HTTP_400_BAD_REQUEST,
            )
        logger.info(
            f"User wallet, {wallet.acct_name} with account number: {wallet.account_number} has changed to {new_status}."
        )

        UserNotification.objects.create(
            user=wallet.user,
            title="Wallet Status Change",
            message=f"Your wallet is now {new_status}!.",
        )

        ActivityModel.objects.create(
            user=request.user,
            title="Wallet Status Change",
            description=f"User wallet, {wallet.acct_name} with account number: {wallet.account_number} has changed to {new_status}.",
        )

        wallet.status = new_status
        wallet.save()

        serializer = self.get_serializer(wallet)
        response_data = {
            "status": "success",
            "message": f"Wallet status changed successfully to {new_status}.",
            "data": serializer.data,
        }

        return Response(
            data=encrypt(response_data),
            status=status.HTTP_200_OK,
        )
