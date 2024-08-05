import requests
import logging
from django.core.exceptions import ValidationError

# In project imports.
from .serializers import (
    ListPartnerUsersSerializer
)
from .views import PaginationStyle

# Third party imports.
from rest_framework import generics, status, exceptions
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication

from accounts.models import User
from commons import Message, CamelCaseJSONRenderer
from permissions import IsSuperAdmin, IsNotDisabled


class GetAllPartnersUsers(generics.ListAPIView):
    """
    GetAllAdminUsers is the GET request to retrieve the count
    of all admin users.
    """

    queryset = User.objects.all()
    serializer_class = ListPartnerUsersSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsSuperAdmin, IsNotDisabled)
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
