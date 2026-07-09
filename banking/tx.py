# Third party imports.
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from rest_framework.pagination import PageNumberPagination

# In-projects imports.
from accounts.models import TxModel
from vas.models import ValueAddedServices

from banking.serializers import TxModelSerializer
from vas.serializers import BillPaymentSerializer
from security import encrypt


class PaginationStyle(PageNumberPagination):
    page_size = 20


class AllTransactions(generics.ListAPIView):
    queryset = TxModel.objects.all()
    serializer_class = TxModelSerializer
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        transactions = TxModel.objects.filter(user=self.request.user).prefetch_related(
            "transfers"
        )
        return transactions

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset().order_by("-date")

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.serializer_class(page, many=True)
            return self.get_paginated_response(encrypt(serializer.data))

        serializer = self.serializer_class(queryset, many=True)
        return Response(data=encrypt(serializer.data), status=status.HTTP_200_OK)


class RetrieveTransaction(generics.GenericAPIView):
    serializer_class = TxModelSerializer
    permission_classes = (IsAuthenticated,)

    def get(self, request, tx_reference):
        user = request.user

        try:
            tx = TxModel.objects.filter(user=user, tx_reference=tx_reference).first()
            if tx:
                serializer = TxModelSerializer(tx)
                return Response(
                    data=encrypt(
                        {
                            "status": "success",
                            "message": f"Transaction for {tx_reference} found!",
                            "data": serializer.data,
                        }
                    ),
                    status=status.HTTP_200_OK,
                )

            vas = ValueAddedServices.objects.filter(
                user=user, tx_reference=tx_reference
            ).first()
            if vas:
                serializer = BillPaymentSerializer(vas)
                return Response(
                    data=encrypt(
                        {
                            "status": "success",
                            "message": f"Transaction for {tx_reference} found!",
                            "data": serializer.data,
                        }
                    ),
                    status=status.HTTP_200_OK,
                )

            return Response(
                data=encrypt({"status": "fail", "detail": "Transaction not found."}),
                status=status.HTTP_404_NOT_FOUND,
            )

        except Exception as e:
            return Response(
                data=encrypt({"error": str(e)}), status=status.HTTP_400_BAD_REQUEST
            )
