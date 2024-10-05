# Third party imports.
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from rest_framework_simplejwt.authentication import JWTAuthentication

from drf_spectacular.utils import extend_schema

from .controllers import Forex

from .serializers import (
    QuotationSerializer,
)


class GetQuotation(generics.GenericAPIView):
    serializer_class = QuotationSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        description="Get quotation view",
        responses={200: {"description": "Get naira to dollar rate"}},
    )
    def get(self, request):
        fx_resp = Forex.generate_quote()
        if fx_resp.status_code == 200:
            fx_rate = fx_resp.json()["data"]["rate"]

            dollars = 1
            naira_value = dollars / fx_rate

            response = {
                "status": "success",
                "message": "Dollar to Naira market value retrieved successfully!.",
                "naira value": naira_value,
            }
            return Response(data=response, status=status.HTTP_200_OK)
        else:
            resp = {
                "status": "fail",
                "message": "Request failed, please try again!.",
                "data": fx_resp.json(),
            }
            return Response(data=resp, status=status.HTTP_404_NOT_FOUND)
