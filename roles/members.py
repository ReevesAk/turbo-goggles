import logging

from django.contrib.auth.hashers import check_password
from django.core.cache import cache

# In project imports.
from .serializers import MemberSerializer

# Third party imports.
from rest_framework import status, generics
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication

from accounts.models import User
from permissions import IsNotDisabled, IsPartnerAdminOrSuperAdmin

from security import encrypt, decrypt

logger = logging.getLogger(__name__)


class AllMembersView(generics.ListAPIView):
    serializer_class = MemberSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [
        JWTAuthentication,
        IsNotDisabled,
        IsPartnerAdminOrSuperAdmin,
    ]

    def get_queryset(self):
        members = (
            User.objects.filter(
                account_types__user_type="Member", walletmodel__isnull=False
            )
            .select_related("walletmodel")
            .distinct()
        )
        return members

    def list(self, request, *args, **kwargs):
        cache_key = "all_members"
        cached_response = cache.get(cache_key)

        if cached_response:
            logger.info("Returning cached members list")
            return Response(data=encrypt(cached_response), status=status.HTTP_200_OK)

        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)

        if page is not None:
            serialized_users = self.get_serializer(page, many=True)

            response_data = {
                "status": "success",
                "message": "All members retrieved successfully",
                "No of Members": queryset.count(),
                "Members object": serialized_users.data,
            }
        else:
            response_data = {
                "status": "success",
                "message": "No member found.",
                "No of Members": 0,
                "Members object": [],
            }

        cache.set(cache_key, response_data, timeout=300)  # 5 minutes

        return Response(data=encrypt(response_data), status=status.HTTP_200_OK)
