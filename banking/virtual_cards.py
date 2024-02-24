import requests
import logging
from decouple import config

from sms import Message
from permissions import IsPartnerUserOrMember
from mail import send_email

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
    FreezeCardSerializers,
    UnfreezeCardSerializers,
)
from accounts.models import  UserNotification
from .models import Cards, CustomerData, Wallet
from .helpers import Pin
from .controllers import VirtualCard

base_url = config("MAPLERAD_BASE_URL")
secret_key = config("MAPLERAD_SECRET_KEY")
headers = {
    "accept": "application/json",
    "content-Type": "application/json",
    "Authorization": "Bearer " + secret_key,
}

picadailys_email = config("EMAIL_HOST_USER")
app_password = config("EMAIL_HOST_PASSWORD")



class CreateCard(generics.CreateAPIView):

    """
    CreateCard handles the POST request of creating a USD card request.
    """

    serializer_class = CreateCardSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsPartnerUserOrMember)

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
                "brand": request.data.get("brand"),
            }
            pin = request.data.get("pin")
            wallet = Wallet.objects.get(user=authenticated_user)
            is_pin_correct = Pin.verify(
                user=authenticated_user, pin=pin, hashed_pin=wallet.pin
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
                            brand=request.data.get("brand"),
                        )
                        new_card.save()

                        UserNotification.objects.create(
                            user=authenticated_user,
                            title="Card Creation.",
                            messsage="You have successfully created a virtual dollar card."
                        )
                        send_email(
                            subject="Card Creation.",
                            body="You have successfully created a virtual dollar card.",
                            sender=picadailys_email,
                            recipients=authenticated_user.email,
                            password=app_password,
                        )
                        recipient = authenticated_user.phone_number[1:]
                        Message.send_msg(
                            msg="Congratulations, you have successfully created a virtual dollar card.",
                            to=recipient
                        )
                        resp = {
                            "message": "Card creation request in progress, you will be notified when it is approved.",
                            "data": response.json(),
                        }
                        return Response(data=resp, status=status.HTTP_200_OK)
                    else:
                        return Response(
                            data=response.json(), status=response.status_code
                        )

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


class PayWithCard(generics.GenericAPIView):
    """
    PayWithCard handles the POST request of withdrawing or paying for a
    service using a card. These includes funding a USD card from a
    customers'account before withdrawing/paying for a service.
    """

    serializer_class = FundCardSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsPartnerUserOrMember)

    def post(self, request):
        authenticated_user = request.user

        if authenticated_user:
            customer = CustomerData.objects.get(user=authenticated_user)
            card = Cards.objects.get(user=customer)
            id = card.card_id

        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid(raise_exception=True):
            # Authenticate wallet.
            pin = request.data.get("pin")
            wallet = Wallet.objects.get(user=authenticated_user)
            is_pin_correct = Pin.verify(
                user=authenticated_user, pin=pin, hashed_pin=wallet.pin
            )
            if is_pin_correct:
                fund_card_response = VirtualCard.fund(
                    id=id, amount=request.data.get["amount"]
                )
                if fund_card_response.status_code == 200:
                    card = Cards.objects.get(user=customer)
                    card.amount = request.data.get["amount"]
                    card.save()

                    resource = f"issuing/{id}/withdraw"
                    payload = {"amount": request.data.get["amount"]}
                    try:
                        withdraw_response = requests.post(
                            url=base_url + resource,
                            json=payload,
                            header=headers,
                        )
                        if withdraw_response.status_code == 200:
                            resp = {
                                "message": "Transaction successful",
                                "data": withdraw_response.json(),
                            }
                            return Response(data=resp, status=status.HTTP_200_OK)
                        else:
                            return Response(
                                data=withdraw_response.json(),
                                status=status.HTTP_400_BAD_REQUEST,
                            )

                    except requests.exceptions.RequestException as e:
                        logging.error(
                            f"Withdraw from a USD card API request error: {str(e)}"
                        )
                        return Response(
                            {"error": str(e)},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        )

                else:
                    return Response(
                        data=fund_card_response.json(),
                        status=fund_card_response.status_code,
                    )
            else:
                return Response(
                    data={"message": "Incorrect pin"},
                    status=status.HTTP_401_UNAUTHORIZED,
                )


class FreezeCard(generics.GenericAPIView):
    """
    FreezeCard handles the POST request of freezing a card created on
    the platform. When a card is frozen no transaction
    (funding/withdrawal) will be allowed.
    """

    serializer_class = FreezeCardSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsPartnerUserOrMember)

    def post(self, request):
        authenticated_user = request.user

        if authenticated_user:
            customer = CustomerData.objects.get(user=authenticated_user)
            card = Cards.objects.get(user=customer)
            id = card.card_id

            try:
                freeze_card = VirtualCard.Freeze(id=id)
                freeze_card_status_code = freeze_card.status_code

                if freeze_card_status_code == 200:
                    UserNotification.objects.create(
                        user=authenticated_user,
                        title="Freeze Card.",
                        messsage="Your request to freeze your virtual card is successful."
                    )
                    send_email(
                        subject="Freeze Card.",
                        body="Your request to freeze your virtual card is successful.",
                        sender=picadailys_email,
                        recipients=authenticated_user.email,
                        password=app_password,
                    )
                    recipient = authenticated_user.phone_number[1:]
                    Message.send_msg(
                        msg="This is to inform you that your request to freeze your virtual card is successful.\
                            You can unfreeze it at anytime. ",
                        to=recipient
                    )
                    resp = {
                        "message": "Card frozen successfully.",
                        "data": freeze_card.json(),
                    }
                    return Response(data=resp, status=status.HTTP_200_OK)
                else:
                    return Response(
                        data=freeze_card.json(), status=freeze_card_status_code
                    )

            except requests.exceptions.RequestException as e:
                logging.error(f"Error while freezing a USD card: {str(e)}")
                return Response(
                    {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )


class UnfreezeCard(generics.GenericAPIView):
    """
    UnfreezeCard handles the POST request of enabling a previously frozen a card
    created on the platform. When a card is enabled all transactions
    (funding/withdrawal) will be allowed.
    """

    serializer_class = UnfreezeCardSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsPartnerUserOrMember)

    def post(self, request):
        authenticated_user = request.user

        if authenticated_user:
            customer = CustomerData.objects.get(user=authenticated_user)
            card = Cards.objects.get(user=customer)
            id = card.card_id

            try:
                unfreeze_card = VirtualCard.Unfreeze(id=id)
                unfreeze_card_status_code = unfreeze_card.status_code

                if unfreeze_card_status_code == 200:

                    UserNotification.objects.create(
                        user=authenticated_user,
                        title="Unfreeze Creation.",
                        messsage="Your request to unfreeze your virtual card is successful."
                    )
                    send_email(
                        subject="Unfreeze Card.",
                        body="Your request to unfreeze your virtual card is successful.",
                        sender=picadailys_email,
                        recipients=authenticated_user.email,
                        password=app_password,
                    )
                    recipient = authenticated_user.phone_number[1:]
                    Message.send_msg(
                        msg="This is to inform you that your request to unfreeze your virtual card is successful.",
                        to=recipient
                    )
                    resp = {
                        "message": "Card unfrozen successfully.",
                        "data": unfreeze_card.json(),
                    }
                    return Response(data=resp, status=status.HTTP_200_OK)
                else:
                    return Response(
                        data=unfreeze_card.json(), status=unfreeze_card_status_code
                    )

            except requests.exceptions.RequestException as e:
                logging.error(f"Error while unfreezing a USD card: {str(e)}")
                return Response(
                    {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
