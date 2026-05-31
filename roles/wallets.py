import logging
import requests


from django.core.cache import cache
from django.contrib.auth.hashers import check_password
from django.db.models import Prefetch
from django.db.models import OuterRef, Subquery
from django.shortcuts import get_object_or_404

# In project imports.
from .serializers import (
    ListWalletUsersSerializer,
    ChangeWalletStatusSerializer,
    WalletKYCSerializer,
    Tier3WalletUpgradeSerializers,
)

# Third party imports.
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.parsers import MultiPartParser, FormParser

from accounts.models import UserNotification, TxModel
from roles.models import ActivityModel
from banking.models import WalletModel, AddressVerificationModel, UserKYC
from banking.controllers import Wallet
from banking.serializers import WalletStatusSerializer
from permissions import IsNotDisabled, IsWalletAdminOrSuperAdmin
from security import encrypt, decrypt

from drf_spectacular.utils import extend_schema

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


class UserKYCListView(generics.ListAPIView):
    serializer_class = WalletKYCSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [
        IsAuthenticated,
        IsNotDisabled,
        IsWalletAdminOrSuperAdmin,
    ]

    def get(self, request):
        # build a subquery to fetch the most recent verification status for the
        # wallet's user. the wallet model has a FK to `user`, so we reference
        # ``user`` on the subquery.
        latest_address_verification = (
            AddressVerificationModel.objects.filter(
                user=OuterRef("user"),
            )
            .order_by("-created_at")
            .values("status")
        )

        # base queryset: wallets whose owner has at least one address
        # verification record
        queryset = (
            WalletModel.objects.filter(user__isnull=False)
            # use the related_name from AddressVerificationModel
            .filter(user__address_verifications__isnull=False)
            .distinct()
            .annotate(
                address_verification_status=Subquery(latest_address_verification[:1])
            )
        )

        serializer = WalletKYCSerializer(queryset, many=True)
        return Response(
            encrypt(serializer.data),
            status=status.HTTP_200_OK,
        )


@extend_schema(
    request={
        "multipart/form-data": {
            "type": "object",
            "properties": {
                "pin": {"type": "string"},
                "bvn": {"type": "string"},
                "nin": {"type": "string"},
                "proofOfAddressVerification": {"type": "string", "format": "binary"},
            },
        }
    }
)
class UpgradeToTier3Wallet(generics.GenericAPIView):
    """UpgradeToTier3Wallet Handles the POST request of sending a Tier 3 wallet upgrade."""

    serializer_class = Tier3WalletUpgradeSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = [
        IsAuthenticated,
        IsNotDisabled,
        IsWalletAdminOrSuperAdmin,
    ]
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request, *args, **kwargs):
        current_admin = request.user
        payload = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in request.data.items()
        }
        serializer = self.get_serializer(data=payload)

        if not serializer.is_valid():
            return Response(
                data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST
            )

        try:
            user_kyc = get_object_or_404(UserKYC, bvn=payload.get("bvn"))
        except UserKYC.DoesNotExist:
            return Response(
                data=encrypt({"error": "User with this BVN does not exist."}),
                status=status.HTTP_404_NOT_FOUND,
            )

        if not check_password(payload.get("pin"), current_admin.admin_pin):
            return Response(
                data=encrypt({"status": "fail", "message": "Invalid PIN."}),
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # Fetch the wallet for the user associated with this KYC record
        try:
            wallet = WalletModel.objects.get(user=user_kyc.user)
        except WalletModel.DoesNotExist:
            return Response(
                data=encrypt({"error": "Wallet for this user does not exist."}),
                status=status.HTTP_404_NOT_FOUND,
            )

        if wallet.tier_level >= 2:
            return Response(
                data=encrypt(
                    {
                        "status": "success",
                        "message": "Wallet is already at Tier 2.",
                    }
                ),
                status=status.HTTP_202_ACCEPTED,
            )

        # Perform the upgrade logic here
        try:
            upgrade_response = Wallet.UpgradefromTier2ToTier3(
                accountNumber=wallet.account_number,
                bvn=payload.get("bvn"),
                nin=payload.get("nin"),
                proofOfAddressVerification=payload.get("proofOfAddressVerification"),
            )
            response_data = upgrade_response.json()
            if upgrade_response.status_code != 200:
                logging.error(f"Wallet upgrade to tier 3 failed: {response_data}")
                return Response(
                    data=encrypt(response_data),
                    status=upgrade_response.status_code,
                )

            account = WalletModel.objects.get(account_number=wallet.account_number)
            address_verification = AddressVerificationModel.objects.get(
                user=account.user,
            )
            address_verification.status = "Approved"
            address_verification.save()

            return Response(
                data=encrypt(
                    {
                        "status": "success",
                        "message": "Wallet upgrade request to Tier 3 sent successfully.",
                    }
                ),
                status=status.HTTP_200_OK,
            )
        except requests.exceptions.RequestException as e:
            logging.error(f"Wallet upgrade to tier 3 API request error: {str(e)}")
            return Response(
                data=encrypt({"error": str(e)}),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
