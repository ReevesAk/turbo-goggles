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


# class GetQuotation(generics.GenericAPIView):
#     serializer_class = ExchangeSerializer
#     authentication_classes = [JWTAuthentication]
#     permission_classes = (IsAuthenticated,)

#     @extend_schema(
#         description="Exchange view",
#         responses={200: {"description": "Forex"}},
#     )
#     def Post(self, request):
#         authenticated_user = request.user

#         serializer = self.serializer_class(data=request.data)
#         if serializer.is_valid(raise_exception=True):
#             quote_resp = Forex.generate_quote()
#             if quote_resp.status_code == 200:
#                 fx_rate = quote_resp.json()["data"]["rate"]
#                 quotation_ref = quote_resp.json()["data"]["rate"]["reference"]

#                 dollars = 1
#                 naira_value = dollars / fx_rate

#                 user_fx = ForexModel.objects.create(
#                     user=authenticated_user,
#                     source_currency="NGN",
#                     target_currency="USD",
#                     rate=fx_rate,
#                     reference=quotation_ref,
#                     amount=request.get("amount")
#                 )
#             fx_resp = Forex.exchange(reference=quotation_ref)
#             if fx resp
