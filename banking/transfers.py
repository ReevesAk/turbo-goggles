import requests
import logging
from decouple import config

from exceptions import Customexceptions
from permissions import hasWallet

# Third party imports.
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from rest_framework_simplejwt.authentication import JWTAuthentication
from drf_spectacular.utils import extend_schema


# In-projects imports.
from .serializers import (
    TransferWithinNigeriaSerializers,
    TransferWithinPicadailysSerializers,
    InternationalTransfersSerializers,
    VerifyTransferSerializer,
    FundWithCardSerializer,
)
from accounts.models import UserNotification
from .helpers import Pin
from .payments import UseCard
from .models import PayWithCard, Wallet


base_url = config("MAPLERAD_BASE_URL")
secret_key = config("MAPLERAD_SECRET_KEY")
headers = {
    "accept": "application/json",
    "content-Type": "application/json",
    "Authorization": "Bearer " + secret_key,
}


class FundWalletWithCard(generics.GenericAPIView):
    """
    FundWalletWithCard handles the POST request of funding your
    picadailys Naira account with card.
    """

    serializer_class = FundWithCardSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, hasWallet)

    def post(self, request):
        user_data = request.data
        authenticated_user = request.user

        serializer = self.serializer_class(data=user_data)
        if serializer.is_valid(raise_exception=True):
            pin = request.data.get("pin")
            amount = request.data.get("amount")

            verification = Pin.verify(user=authenticated_user, pin=pin)
            if verification:
                initialize_response = UseCard.initialize_payment(
                    amount=amount,
                    customerName=authenticated_user.firstname
                    + authenticated_user.last_name,
                    customerEmail=authenticated_user.email,
                    paymentDescription="Fund wallet with card",
                )
                if initialize_response.status_code == 200:
                    resp = initialize_response.json()["responseBody"]
                    init_pay = PayWithCard.objects.create(
                        user=authenticated_user,
                        transactionReference=resp["transactionReference"],
                        paymentReference=resp["paymentReference"],
                        customerName=authenticated_user.firstname
                        + authenticated_user.last_name,
                        customerEmail=authenticated_user.email,
                        redirectUrl=resp["checkoutUrl"],
                    )
                    charge_from_card_resp = UseCard.charge(
                        transactionReference=init_pay.transactionReference,
                        number=request.data.get("number"),
                        expiryMonth=request.data.get("expiry_month"),
                        expiryYear=request.data.get("expiry_year"),
                        pin=request.data.get("card_pin"),
                        cvv=request.data.get("cvv"),
                    )
                    if charge_from_card_resp.status_code == 200:
                        resp = initialize_response.json()["responseBody"]
                        validate_card = UseCard.validate_otp(
                            init_pay.transactionReference,
                            tokenId=request.data.get("tokenId"),
                            token=request.data.get("token"),
                        )
                        user_wallet = Wallet.objects.get(user=authenticated_user)
                        if validate_card.status_code == 200:
                            local_transfer_response = Transfer.local(
                                amount=amount,
                                bank_code="251",
                                reason="Fund wallet with card",
                                account_number=user_wallet.account_number,
                            )
                            if local_transfer_response.status_code == 200:
                                response = {
                                    "status": "success",
                                    "message": f"Wallet has been funded with {amount} successfilly.",
                                    "data": local_transfer_response.json(),
                                }
                                return Response(
                                    data=response, status=status.HTTP_200_OK
                                )
                        else:
                            return Response(
                                data=validate_card.json(),
                                status=validate_card.status_code,
                            )
                    else:
                        return Response(
                            data=charge_from_card_resp.json(),
                            status=charge_from_card_resp.status_code,
                        )
                else:
                    return Response(
                        data=initialize_response.json(),
                        status=initialize_response.status_code,
                    )


class TransferWithinPicadailys(generics.GenericAPIView):
    """
    TransferWithinPicadailys handles the POST request of transfering money from your
    picadailys Naira account to another picadailys account.
    """

    serializer_class = TransferWithinPicadailysSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, hasWallet)

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
                        amount = request.data.get("amount")
                        account_number = request.data.get("acct_number")

                        UserNotification.objects.create(
                            user=authenticated_user,
                            title="Transfer.",
                            message=f"Your trnasfer of {amount} to {account_number} is successful.",
                        )
                        response_data = {
                            "status": "success",
                            "message": "Transfer succesful",
                            "data": picadailys_transfer_response.json(),
                        }

                        return Response(data=response_data, status=status.HTTP_200_OK)
                    else:
                        return Response(
                            data=picadailys_transfer_response.json(),
                            status=picadailys_transfer_response.status_code,
                        )
                except requests.exceptions.RequestException as e:
                    logging.error(f"Transfer API request error: {str(e)}")
                    return Response(
                        {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )
            else:
                return Response(
                    data="Incorrect Pin", status=status.HTTP_401_UNAUTHORIZED
                )
        else:
            return Response(data=serializer.error, status=status.HTTP_400_BAD_REQUEST)


class TransferWithinNG(generics.GenericAPIView):
    """
    TransferWithinNG handles the POST request of transfering money from your
    maplerad Naira account to other financial institutions within Nigeria.
    """

    serializer_class = TransferWithinNigeriaSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, hasWallet)

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
                        amount = request.data.get("amount")
                        account_number = request.data.get("acct_number")

                        UserNotification.objects.create(
                            user=authenticated_user,
                            title="Transfer.",
                            message=f"Your trnasfer of {amount} to {account_number} is successful.",
                        )
                        response_data = {
                            "status": "success",
                            "message": "Transfer succesful",
                            "data": local_transfer_response.json(),
                        }

                        return Response(data=response_data, status=status.HTTP_200_OK)
                    else:
                        return Response(
                            data=local_transfer_response.json(),
                            status=local_transfer_response.status_code,
                        )
                except requests.exceptions.RequestException as e:
                    logging.error(f"Transfer API request error: {str(e)}")
                    return Response(
                        {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )
            else:
                return Response(
                    data="Incorrect Pin", status=status.HTTP_401_UNAUTHORIZED
                )
        else:
            return Response(data=serializer.error, status=status.HTTP_400_BAD_REQUEST)


class InternationalTransfer(generics.GenericAPIView):
    """
    InternationalTransfer handles the POST request of outbound transfer of money from your
    maplerad Dollar account to other financial institutions outside of Nigeria.
    """

    serializer_class = InternationalTransfersSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, hasWallet)

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
                        amount = request.data.get("amount")
                        account_number = request.data.get("acct_number")

                        UserNotification.objects.create(
                            user=authenticated_user,
                            title="Transfer.",
                            message=f"Your trnasfer of {amount} to {account_number} is successful.",
                        )
                        response_data = {
                            "status": "success",
                            "message": "Transfer succesful",
                            "data": intl_transfer_response.json(),
                        }

                        return Response(data=response_data, status=status.HTTP_200_OK)
                    else:
                        return Response(
                            data=intl_transfer_response.json(),
                            status=intl_transfer_response.status_code,
                        )
                except requests.exceptions.RequestException as e:
                    logging.error(f"International transfer API request error: {str(e)}")
                    return Response(
                        {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )
        else:
            return Response(data=serializer.error, status=status.HTTP_400_BAD_REQUEST)


class VerifyTransfer(generics.GenericAPIView):
    """
    VerifyTransfer handles the GET request of checking transaction details.
    """

    serializer_class = VerifyTransferSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, hasWallet)

    @extend_schema(
        description="Get transfer details",
        responses={200: {"description": "Get trnasaction detail of a transfer"}},
    )
    def get(self, request, *args, **kwargs):
        authenticated_user = request.user

        tx_id = kwargs.get("transfer_id")

        if tx_id:
            pin = request.data.get("pin")

            verification = Pin.verify(user=authenticated_user, pin=pin)
            if verification:
                try:
                    verify_transfer_response = Transfer.verify(transfer_id=tx_id)
                    if verify_transfer_response.status_code == 200:
                        resp = {
                            "status": "success",
                            "message": "Transaction was successful",
                            "data": verify_transfer_response.json(),
                        }
                        return Response(data=resp, status=status.HTTP_200_OK)
                    else:
                        return Response(
                            data=verify_transfer_response.json(),
                            status=verify_transfer_response.status_code,
                        )
                except requests.exceptions.RequestException as e:
                    logging.error(f"Verify transfer API request error: {str(e)}")
                    raise Customexceptions.server_error(item_error=tx_id)
        else:
            raise Customexceptions.not_found(item_not_found=tx_id)
