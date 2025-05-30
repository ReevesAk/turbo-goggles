import logging

from django.http import HttpResponse
from django.views import View

from rest_framework.response import Response
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework import status

from .models import FundWithCard
from .serializers import VerifyCardDepositSerializers, WebhookSerializer
from accounts.models import UserNotification
from roles.models import ActivityModel
from security import encrypt, decrypt
from permissions import IsAuthenticatedOrGuestWithValidId

logger = logging.getLogger(__name__)


class CardDepositPaystackWebhook(generics.CreateAPIView):
    def post(self, request, *args, **kwargs):
        # Validate the incoming data using the serializer
        serializer = WebhookSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)  # Raise an error if validation fails

        webhook_data = serializer.validated_data  # Get validated data

        # Handle different events
        event_type = webhook_data.get("event")
        if event_type == "charge.success":
            return self.handle_charge_success(webhook_data)
        elif event_type == "hook":
            return self.handle_hook_event(webhook_data)
        else:
            logger.error(f"Unhandled event type: {event_type}")
            return Response(
                data={"status": "event not handled"}, status=status.HTTP_400_BAD_REQUEST
            )

    def handle_charge_success(self, webhook_data):
        transaction_id = webhook_data["data"]["id"]
        reference = webhook_data["data"]["reference"]
        email = webhook_data["data"]["customer"]["email"]
        tx_status = webhook_data["data"]["status"]
        amount = webhook_data["data"]["amount"]  # Convert kobo to naira

        user_obj = FundWithCard.objects.filter(txn_reference=reference).first()
        if user_obj:
            user_obj.status = tx_status
            user_obj.email = email
            user_obj.amount = amount
            user_obj.save()

            logger.info(
                f"Transaction {transaction_id} was successful. Updated user: {email}"
            )
            return Response(data={"status": "success"}, status=status.HTTP_200_OK)
        else:
            logger.warning(f"No FundWithCard entry found for reference: {reference}")
            return Response(
                data={"status": "not found"}, status=status.HTTP_404_NOT_FOUND
            )

    def handle_hook_event(self, webhook_data):
        logger.info("Hook event received.")
        return Response(
            data={"status": "hook event processed"}, status=status.HTTP_200_OK
        )


class VerifyCardPaymentTransaction(generics.CreateAPIView):
    """
    VerifyCardPaymentTransaction is the GET request handler that validates
    the supplied single transaction reference and returns the current
    status of the transaction.
    """

    serializer_class = VerifyCardDepositSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticatedOrGuestWithValidId]

    def get(self, request, *args, **kwargs):
        user_data = decrypt(request.data)
        user = request.user
        guest_id = request.headers.get("X-Guest-ID")
        tx_ref = user_data.get("txn_reference")

        if user:
            user_obj = FundWithCard.objects.filter(
                txn_reference=tx_ref, user=request.user
            ).first()
        if user_obj:
            if user_obj.status == "success":
                resp = {
                    "status": "success",
                    "message": "Transaction was successful.",
                    "transaction": {
                        "txn_reference": user_obj.txn_reference,
                        "amount": user_obj.amount,
                        "email": user_obj.email,
                        "status": user_obj.status,
                    },
                }
                encrypted_resp = encrypt(resp)
                if user:
                    UserNotification.objects.create(
                        user=user,
                        title="Card Payment",
                        message=f"Your card payment of {user_obj.amount}, was successful.",
                    )

                    ActivityModel.objects.create(
                        user=user,
                        title="Card Payment",
                        description=f"{user.first_name} {user.last_name} has successfully paid {user_obj.amount} from their card.",
                    )
                elif guest_id:
                    ActivityModel.objects.create(
                        user=guest_id,
                        title="Card Payment",
                        description=f"Guest user: {guest_id} has successfully paid {user_obj.amount} from their card.",
                    )

                return Response(data=encrypted_resp, status=status.HTTP_200_OK)
            else:
                resp = {
                    "status": "fail",
                    "message": f"Transaction is not successful. Current status: {user_obj.status}.",
                    "transaction": {
                        "txn_reference": user_obj.txn_reference,
                        "amount": user_obj.amount,
                        "email": user_obj.email,
                        "status": user_obj.status,
                    },
                }
                if user:
                    UserNotification.objects.create(
                        user=user,
                        title="Card Payment",
                        message=f"Your card payment of {user_obj.amount}, was unsuccessful.",
                    )

                    ActivityModel.objects.create(
                        user=user,
                        title="Card Payment",
                        description=f"Card payment of {user_obj.amount} by {user.first_name} {user.last_name} was unsuccessful.",
                    )
                elif guest_id:
                    ActivityModel.objects.create(
                        user=guest_id,
                        title="Card Payment",
                        description=f"Card payment of {user_obj.amount} by guest user: {guest_id} was unsuccessful.",
                    )
                encrypted_resp = encrypt(resp)
                return Response(data=encrypted_resp, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response(
                data={
                    "status": "fail",
                    "message": "No transaction found for this reference.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )


class RedirectingPageView(View):
    def get(self, request, *args, **kwargs):
        return HttpResponse("Redirecting...")
