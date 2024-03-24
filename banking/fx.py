import requests
import logging

from permissions import hasWallet

# Third party imports.
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from rest_framework_simplejwt.authentication import JWTAuthentication

from drf_spectacular.utils import extend_schema

from .controllers import Forex, Account, VirtualCard
from .models import CustomerData
from .helpers import Pin

from .serializers import (
    QuotationSerializer,
    NGNToUSDConversionSerializer,
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


class ConvertToDollar(generics.GenericAPIView):
    """
    ConvertToDollar is the POST request method that converts a customer's
    naira and funds funds the card with the equivalent.
    """

    serializer_class = NGNToUSDConversionSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, hasWallet)

    def post(self, request):
        authenticated_user = request.user

        pin = request.data.get("pin")
        amount = request.data.get("amount")

        customer = CustomerData.objects.get(user=authenticated_user)
        verification = Pin.verify(user=authenticated_user, pin=pin)
        if verification:
            try:
                fund_repsonse = VirtualCard.fund(id=customer.customer_id, amount=amount)
                if fund_repsonse.status_code == 200:
                    fx_resp = Forex.generate_quote()
                    if fx_resp.status_code == 200:
                        fx_rate = fx_resp.json()["data"]["rate"]

                        dollars = 3
                        naira_value = dollars / fx_rate

                        # Inititate a debit on the customer's account for card creation.
                        Account.Debit(
                            amount=naira_value, reason="Charge for currency conversion."
                        )
                    resp = {
                        "status": "success!",
                        "message": "Transaction successful",
                        "data": fund_repsonse.json(),
                    }
                    return Response(data=resp, status=status.HTTP_200_OK)
                else:
                    response = {
                        "status": "fail!",
                        "message": "Transaction failed",
                        "data": fund_repsonse.json(),
                    }
                    return Response(
                        data=response,
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            except requests.exceptions.RequestException as e:
                logging.error(
                    f"Conversion from Naira to Dollar API request error: {str(e)}"
                )
                return Response(
                    {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
