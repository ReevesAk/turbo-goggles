import requests
import logging
from decouple import config

from permissions import IsPartnerUserOrMember

# Third party imports.
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from rest_framework_simplejwt.authentication import JWTAuthentication

# In-projects imports.
from .serializers import (
    TransferWithinNigeriaSerializers,
    TransferWithinPicadailysSerializers,
    InternationalTransfersSerializers,
)
from .helpers import Pin
from .controllers import Transfer

base_url = config("MAPLERAD_BASE_URL")
secret_key = config("MAPLERAD_SECRET_KEY")
headers = {
    "accept": "application/json",
    "content-Type": "application/json",
    "Authorization": "Bearer " + secret_key,
}


class TransferWithinPicadailys(generics.GenericAPIView):
    """
    TransferWithinPicadailys handles the POST request of transfering money from your
    picadailys Naira account to another picadailys account.
    """

    serializer_class = TransferWithinPicadailysSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsPartnerUserOrMember)

    def post(self, request):
        user_data = request.data
        authenticated_user = request.user

        serializer = self.serializer_class(data=user_data)
        if serializer.is_valid(raise_exception=True):
            pin = request.data.get("pin")

            verification = Pin.verify(user=authenticated_user, pin=pin)
            if verification:
                serializer.save()
                try:
                    picadailys_transfer_response = Transfer.picadailys(
                        amount=request.data.get("amount"),
                        reason=request.data.get("reason"),
                        account_number=request.data.get("acct_number"),
                    )

                    if picadailys_transfer_response.status_code == 200:
                        response_data = {
                            "status": "success",
                            "message": "Transfer succesful",
                            "data": picadailys_transfer_response.json(),
                        }

                        return Response(data=response_data, status=status.HTTP_200_OK)
                    else:
                        return Response(data=picadailys_transfer_response.json(), status=picadailys_transfer_response.status_code)
                except requests.exceptions.RequestException as e:
                    logging.error(f"Transfer API request error: {str(e)}")
                    return Response(
                        {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )
            else:
                return Response(data="Incorrect Pin", status=status.HTTP_401_UNAUTHORIZED)
        else:
            return Response(data=serializer.error, status=status.HTTP_400_BAD_REQUEST)


class TransferWithinNG(generics.GenericAPIView):
    """
    TransferWithinNG handles the POST request of transfering money from your
    maplerad Naira account to other financial institutions within Nigeria.
    """

    serializer_class = TransferWithinNigeriaSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsPartnerUserOrMember)

    def post(self, request):
        user_data = request.data
        authenticated_user = request.user

        serializer = self.serializer_class(data=user_data)
        if serializer.is_valid(raise_exception=True):
            pin = request.data.get("pin")

            verification = Pin.verify(user=authenticated_user, pin=pin)
            if verification:
                serializer.save()
                try:
                    local_transfer_response = Transfer.local(
                        amount=request.data.get("amount"),
                        bank_code=request.data.get("bankcode"),
                        reason=request.data.get("reason"),
                        account_number=request.data.get("acct_number"),
                    )

                    if local_transfer_response.status_code == 200:
                        response_data = {
                            "status": "success",
                            "message": "Transfer succesful",
                            "data": local_transfer_response.json(),
                        }

                        return Response(data=response_data, status=status.HTTP_200_OK)
                    else:
                        return Response(data=local_transfer_response.json(), status=local_transfer_response.status_code)
                except requests.exceptions.RequestException as e:
                    logging.error(f"Transfer API request error: {str(e)}")
                    return Response(
                        {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )
            else:
                return Response(data="Incorrect Pin", status=status.HTTP_401_UNAUTHORIZED)
        else:
            return Response(data=serializer.error, status=status.HTTP_400_BAD_REQUEST)


class InternationalTransfer(generics.GenericAPIView):
    """
    InternationalTransfer handles the POST request of outbound transfer of money from your
    maplerad Dollar account to other financial institutions outside of Nigeria.
    """

    serializer_class = InternationalTransfersSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsPartnerUserOrMember)

    def post(self, request):
        user_data = request.data
        authenticated_user = request.user

        serializer = self.serializer_class(data=user_data)
        if serializer.is_valid(raise_exception=True):
            pin = request.data.get("pin")

            verification = Pin.verify(user=authenticated_user, pin=pin)
            if verification:
                serializer.save()
                try:
                    intl_transfer_response = Transfer.internatonal(
                        sfirst_name=authenticated_user.first_name,
                        slast_name=authenticated_user.last_name,
                        dob=authenticated_user.date_of_birth,
                        phone_number=authenticated_user.phone_number,
                        address=authenticated_user.address,
                        state=authenticated_user.state,
                        city=authenticated_user.city,
                        amount=request.data.get("amount"),
                        account_number=request.data.get("acct_number"),
                        bank_code=request.data.get("bankcode"),
                        reason=request.data.get("reason"),
                        postal_code=request.data.get("postal_code"),
                        id_type=request.data.get("id_type"),
                        id_number=request.data.get("number"),
                        issued_at=request.data.get("issued_at"),
                        issued_date=request.data.get("issued_date"),
                        expiration_date=request.data.get("expiration_date"),
                        cpfirst_name=request.data.get("receiver_first_name"),
                        cplast_name=request.data.get("receiver_last_name"),
                        cpphone_number=request.data.get("receiver_phone_number"),
                        cpaddress=request.data.get("receiver_address"),
                    )

                    if intl_transfer_response.status_code == 200:
                        response_data = {
                            "status": "success",
                            "message": "Transfer succesful",
                            "data": intl_transfer_response.json(),
                        }

                        return Response(data=response_data, status=status.HTTP_200_OK)
                    else:
                        return Response(data=intl_transfer_response.json(), status=intl_transfer_response.status_code)
                except requests.exceptions.RequestException as e:
                    logging.error(f"International transfer API request error: {str(e)}")
                    return Response(
                        {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )
        else:
            return Response(data=serializer.error, status=status.HTTP_400_BAD_REQUEST)
