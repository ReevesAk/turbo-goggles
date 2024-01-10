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
from .serializers import TransferWithinNigeriaSerializers
from .helpers import Pin

base_url = config("MAPLERAD_BASE_URL")
secret_key = config("MAPLERAD_SECRET_KEY")
headers = {
    "accept": "application/json",
    "content-Type": "application/json",
    "Authorization": "Bearer " + secret_key,
}


class TransferWithinNG(generics.GenericAPIView):
    """
    TransferWithinNG handles the POST request of transfering money from your
    maplerad Naira account to other financial institutions within Nigeria.
    """

    serializer_class = TransferWithinNigeriaSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsPartnerOrMember)

    def post(self, request):
        user_data = request.data
        authenticated_user = request.user

        serializer = self.serializer_class(data=user_data)
        if serializer.is_valid(raise_exception=True):
            resource = "transfers"
            payload = {
                "bank_code": user_data["bankcode"],
                "account_number": user_data["acct_number"],
                "amount": user_data["amount"],
                "reason": user_data["reason"],
            }

            pin = request.data.get("pin")

            verification = Pin.verify(user=authenticated_user, pin=pin)
            if verification:
                serializer.save()
                try:
                    response = requests.post(
                        url=base_url + resource, json=payload, headers=headers
                    )

                    if response.status_code == 200:
                        response_data = {
                            "message": "Transfer succesful",
                            "data": response.json(),
                        }

                        return Response(data=response_data, status=status.HTTP_200_OK)
                    else:
                        return Response(response.json(), status=response.status_code)
                except requests.exceptions.RequestException as e:
                    logging.error(f"Transfer API request error: {str(e)}")
                    return Response(
                        {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )
