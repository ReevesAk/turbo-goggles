import requests
import logging
from decouple import config

from permissions import IsPartnerOrMember

# Third party imports.
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from rest_framework_simplejwt.authentication import JWTAuthentication

# In-projects imports.
from .serializers import (
    CreateCardSerializers,
    FundCardSerializers,
)
from .models import Cards, CustomerData, Wallet
from .helpers import Pin

base_url = config("MAPLERAD_BASE_URL")
secret_key = config("MAPLERAD_SECRET_KEY")
headers = {
    "accept": "application/json",
    "content-Type": "application/json",
    "Authorization": "Bearer " + secret_key,
}


class CreateCard(generics.CreateAPIView):
    
    """
    CreateCard handles the POST request of creating a USD card request.
    """

    serializer_class = CreateCardSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsPartnerOrMember)

    def post(self, request):
        authenticated_user = request.user

        if authenticated_user:
            customer = CustomerData.objects.get(user=authenticated_user)
            id = customer.customer_id

        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid(raise_exception=True):
            resource = "issuing"
            payload = {
                "customer_id": id,
                "currency": "USD",
                "type": "VIRTUAL",
                "auto_approve": True,
                "brand": request.data.get("brand")
            }
            pin = request.data.get("pin")
            wallet = Wallet.objects.get(user=authenticated_user)
            is_pin_correct = Pin.verify(
                user=authenticated_user,
                pin=pin,
                hashed_pin=wallet.pin
            )
            if is_pin_correct:
                try:
                    response = requests.post(
                        url=base_url + resource,
                        json=payload,
                        header=headers,
                    )
                    if response.status_code == 200:
                        new_card = Cards.objects.create(
                            user=customer,
                            customer="USD",
                            type="VIRTUAL",
                            auto_approve=True,
                            id=response.json()["data"]["card_id"],
                            brand=request.data.get("brand")
                        )
                        new_card.save()
                        resp = {
                            "message": "Card creation request in progress, you will be notified when it is approved.",
                            "data": response.json()
                        }
                        return Response(data=resp, status=status.HTTP_200_OK)
                    else:
                        return Response(data=response.json(), status=response.status_code)

                except requests.exceptions.RequestException as e:
                    logging.error(f"Create a USD card API request error: {str(e)}")
                    return Response(
                        {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )
            else:
                return Response(
                data={"message": "Incorrect pin"},
                status=status.HTTP_401_UNAUTHORIZED,
            )


class FundCard(generics.GenericAPIView):
    """
    FundCard handles the POST request of funding a USD card from a customers' account.
    """
    serializer_class = FundCardSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsPartnerOrMember)

    def post(self, request):
        authenticated_user = request.user

        if authenticated_user:
            customer = CustomerData.objects.get(user=authenticated_user)
            card = Cards.objects.get(user=customer)
            id = card.card_id

        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid(raise_exception=True):
            resource = f"issuing/{id}/fund"
            payload = {
                "amount": request.data.get["amount"],
            }

            # Authenticate wallet.
            pin = request.data.get("pin")
            wallet = Wallet.objects.get(user=authenticated_user)
            is_pin_correct = Pin.verify(
                user=authenticated_user,
                pin=pin,
                hashed_pin=wallet.pin
            )
            if is_pin_correct:
                try:
                    response = requests.post(
                        url=base_url + resource,
                        json=payload,
                        header=headers,
                    )
                    if response.status_code == 200:
                        card = Cards.objects.get(user=customer)
                        card.amount = request.data.get["amount"]
                        card.save()
                        resp = {
                            "message": "Card funded succesfully.",
                            "data": response.json()
                        }
                        return Response(data=resp, status=status.HTTP_200_OK)
                    else:
                        return Response(data=response.json(), status=response.status_code)

                except requests.exceptions.RequestException as e:
                    logging.error(f"Create a USD card API request error: {str(e)}")
                    return Response(
                        {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )
            else:
                return Response(
                data={"message": "Incorrect pin"},
                status=status.HTTP_401_UNAUTHORIZED,
            )
