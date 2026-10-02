# Third party imports.
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from rest_framework.pagination import PageNumberPagination

# In-projects imports.
from accounts.models import TxModel
from vas.models import ValueAddedServices
from vas.token_cache import get_electricity_token, get_electricity_tokens

from banking.serializers import TxModelSerializer
from vas.serializers import BillPaymentSerializer
from security import encrypt


def build_receipt(user, tx_reference):
    """Serialize a TxModel exactly as the transaction history/detail
    endpoints do, so a purchase/transfer success response can carry a
    shareable receipt without a follow-up request. Bill payments get the
    cached electricity token, same as RetrieveTransaction. Returns None if
    the row isn't there (guest purchases, or a failed TxModel write) -
    callers treat the receipt as best-effort and still return success."""
    if not user or not tx_reference:
        return None
    tx = (
        TxModel.objects.filter(user=user, tx_reference=tx_reference)
        .prefetch_related("transfers")
        .first()
    )
    if not tx:
        return None
    data = TxModelSerializer(tx).data
    if tx.tx_type == "Bill Payment":
        data["token"] = get_electricity_token(tx_reference)[0]
    return data


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

    def _inject_tokens(self, rows, serialized):
        """Add the cached electricity token onto each 'Bill Payment' row of
        an already-serialized page. One Redis get_many for the whole page;
        rows the cache has dropped (or non-bill-payments) get token=None.
        Purely additive - every other field is left exactly as serialized."""
        refs = [r.tx_reference for r in rows if r.tx_type == "Bill Payment"]
        token_map = get_electricity_tokens(refs) if refs else {}
        for row, item in zip(rows, serialized):
            if row.tx_type == "Bill Payment":
                item["token"] = token_map.get(row.tx_reference)
        return serialized

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset().order_by("-date")

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.serializer_class(page, many=True)
            data = self._inject_tokens(page, serializer.data)
            return self.get_paginated_response(encrypt(data))

        rows = list(queryset)
        serializer = self.serializer_class(rows, many=True)
        data = self._inject_tokens(rows, serializer.data)
        return Response(data=encrypt(data), status=status.HTTP_200_OK)


class RetrieveTransaction(generics.GenericAPIView):
    serializer_class = TxModelSerializer
    permission_classes = (IsAuthenticated,)

    def get(self, request, tx_reference):
        user = request.user

        try:
            tx = TxModel.objects.filter(user=user, tx_reference=tx_reference).first()
            if tx:
                data = TxModelSerializer(tx).data
                # TxModel has no token field, and the electricity token is
                # no longer persisted on ValueAddedServices - it lives in a
                # TTL cache keyed by tx_reference (see vas/token_cache.py).
                # Returns None once that entry has expired; the SMS/email
                # the customer got at purchase time is the source of truth.
                if tx.tx_type == "Bill Payment":
                    data["token"] = get_electricity_token(tx_reference)[0]
                return Response(
                    data=encrypt(
                        {
                            "status": "success",
                            "message": f"Transaction for {tx_reference} found!",
                            "data": data,
                        }
                    ),
                    status=status.HTTP_200_OK,
                )

            vas = ValueAddedServices.objects.filter(
                user=user, tx_reference=tx_reference
            ).first()
            if vas:
                data = dict(BillPaymentSerializer(vas).data)
                # token is no longer a stored column - pull it from the TTL
                # cache, same as the TxModel branch above.
                data["token"] = get_electricity_token(tx_reference)[0]
                return Response(
                    data=encrypt(
                        {
                            "status": "success",
                            "message": f"Transaction for {tx_reference} found!",
                            "data": data,
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
