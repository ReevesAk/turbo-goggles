# Third party imports.
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.pagination import PageNumberPagination

# In-projects imports.
from accounts.models import TxModel

from banking.serializers import TxModelSerializer


class PaginationStyle(PageNumberPagination):
    page_size = 20


class AllTransactions(generics.ListAPIView):
    queryset = TxModel.objects.all()
    serializer_class = TxModelSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated)

    def get_queryset(self):
        transactions = TxModel.objects.all()
        return transactions

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.serializer_class(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.serializer_class(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
