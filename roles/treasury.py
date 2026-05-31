import logging

from django.core.cache import cache
from django.contrib.auth.hashers import check_password
from django.db.models import Prefetch

from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication

from accounts.models import UserNotification, TxModel
from roles.models import ActivityModel
from treasury.models import TreasuryAccount
from treasury.serializers import (
    ListTreasuryAccountsSerializer,
    ChangeTreasuryAccountStatusSerializer,
    TreasuryAccountStatusSerializer,
)
from permissions import IsNotDisabled, IsWalletAdminOrSuperAdmin
from security import encrypt, decrypt

logger = logging.getLogger(__name__)


class GetAllTreasuryAccounts(generics.ListAPIView):
    """
    List all treasury account holders.
    Equivalent to GetallWalletUsers in roles/wallets.py.
    """

    serializer_class = ListTreasuryAccountsSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, IsNotDisabled, IsWalletAdminOrSuperAdmin]

    def get_queryset(self):
        last_5_tx = Prefetch(
            "user__txmodel_set",
            queryset=TxModel.objects.order_by("-date")[:5],
            to_attr="last_five_tx",
        )
        return (
            TreasuryAccount.objects.select_related("user")
            .prefetch_related(last_5_tx)
            .order_by("created_at")
        )

    def list(self, request, *args, **kwargs):
        cache_key = "treasury_accounts_list"
        cached = cache.get(cache_key)
        if cached:
            return Response(encrypt(cached), status=status.HTTP_200_OK)

        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)

        if page is not None:
            serialized = self.get_serializer(page, many=True)
            data = {
                "status": "success",
                "message": "All treasury accounts retrieved.",
                "count": queryset.count(),
                "accounts": serialized.data,
            }
            return self.get_paginated_response(encrypt(data))

        serialized = self.get_serializer(queryset, many=True)
        data = {
            "status": "success",
            "message": "All treasury accounts retrieved.",
            "count": queryset.count(),
            "accounts": serialized.data,
        }
        cache.set(cache_key, data, timeout=300)
        return Response(encrypt(data), status=status.HTTP_200_OK)


class TreasuryAccountSearch(generics.ListAPIView):
    """
    Search treasury accounts by account number or name.
    Equivalent to WalletSearch in roles/wallets.py.
    """

    serializer_class = TreasuryAccountStatusSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, IsNotDisabled, IsWalletAdminOrSuperAdmin]

    def get(self, request, *args, **kwargs):
        keyword = kwargs.get("search_term", "")

        if keyword.isdigit():
            accounts = TreasuryAccount.objects.filter(account_number__icontains=keyword)
        else:
            accounts = TreasuryAccount.objects.filter(acct_name__icontains=keyword)

        serializer = self.get_serializer(accounts, many=True)
        response_data = {
            "status": "success" if accounts.exists() else "fail",
            "message": (
                "Results found."
                if accounts.exists()
                else "No accounts matching that query."
            ),
            "data": serializer.data,
        }

        return Response(
            data=encrypt(response_data),
            status=(
                status.HTTP_200_OK if accounts.exists() else status.HTTP_404_NOT_FOUND
            ),
        )


class ChangeTreasuryAccountStatusView(generics.RetrieveAPIView):
    """
    Activate or suspend a treasury account.
    Equivalent to ChangeWalletStatusView in roles/wallets.py.
    """

    serializer_class = ChangeTreasuryAccountStatusSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, IsNotDisabled, IsWalletAdminOrSuperAdmin]

    def post(self, request, *args, **kwargs):
        decrypted_payload = decrypt(request.data)
        payload = {
            k: v.strip() if isinstance(v, str) else v
            for k, v in decrypted_payload.items()
        }

        account_number = payload.get("account_number")
        new_status = payload.get("status")
        pin = payload.get("pin")

        try:
            account = TreasuryAccount.objects.get(account_number=account_number)
        except TreasuryAccount.DoesNotExist:
            return Response(
                data=encrypt({"status": "fail", "message": "Account not found."}),
                status=status.HTTP_404_NOT_FOUND,
            )

        if not check_password(password=pin, encoded=request.user.admin_pin):
            return Response(
                data=encrypt({"status": "fail", "message": "Incorrect PIN."}),
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if account.status == new_status:
            return Response(
                data=encrypt(
                    {"status": "fail", "message": f"Account is already {new_status}."}
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        UserNotification.objects.create(
            user=account.user,
            title="Account Status Change",
            message=f"Your account is now {new_status}.",
        )
        ActivityModel.objects.create(
            user=request.user,
            title="Account Status Change",
            description=f"Treasury account {account_number} ({account.acct_name}) changed to {new_status}.",
        )

        account.status = new_status
        account.save(update_fields=["status"])

        serializer = self.get_serializer(account)
        return Response(
            data=encrypt(
                {
                    "status": "success",
                    "message": f"Account status changed to {new_status}.",
                    "data": serializer.data,
                }
            ),
            status=status.HTTP_200_OK,
        )
