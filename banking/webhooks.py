import logging
from rest_framework.response import Response
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework import status

from .models import FundWithCard
from .serializers import VerifyCardDepositSerializers, WebhookSerializer
from accounts.models import UserNotification
from roles.models import ActivityModel

logger = logging.getLogger(__name__)


class CardDepositPaystackWebhook(generics.CreateAPIView):
    def post(self, request, *args, **kwargs):
        # Validate the incoming data using the serializer
        serializer = WebhookSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)  # This will raise an error if validation fails

        webhook_data = serializer.validated_data
        if webhook_data.get("event") == "charge.success":
            transaction_id = webhook_data["data"]["id"]
            reference = webhook_data["data"]["reference"]
            email = webhook_data["data"]["customer"]["email"]
            tx_status = webhook_data["data"]["status"]
            amount = webhook_data["data"]["amount"] / 100

            user_obj = FundWithCard.objects.filter(txn_reference=reference).first()
            if user_obj:
                # Update the fields with data from the webhook
                user_obj.status = tx_status
                user_obj.email = email
                user_obj.amount = amount
                user_obj.save()

                logger.info(
                    f"Transaction {transaction_id} was successful. Updated user: {user_obj.user.email}"
                )
            else:
                logger.warning(
                    f"No FundWithCard entry found for reference: {reference}"
                )
                return Response(
                    data={"status": "not found"}, status=status.HTTP_404_NOT_FOUND
                )

        logger.error("Event not handled")
        return Response(
            data={"status": "event not handled"}, status=status.HTTP_400_BAD_REQUEST
        )


class VerifyCardPaymentTransaction(generics.CreateAPIView):
    """
    VerifyCardPaymentTransaction is the GET request handler that validating
    the supplied single transaction reference and returns the current
    status of the transaction.
    """

    serializer_class = VerifyCardDepositSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user_data = request.data
        user = request.user
        tx_ref = user_data.get("txn_reference")

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
                UserNotification.objects.create(
                    user=user,
                    title="Card Payment",
                    message=f"Your card payment of {user_obj.amount}, was successful.",
                )

                ActivityModel.objects.create(
                    user=user,
                    title="Card Payment",
                    description=f"{user.first_name} {user.last_name} has successfully paid {user_obj.amount} from his card.",
                )

                return Response(data=resp, status=status.HTTP_200_OK)
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
                return Response(data=resp, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response(
                data={
                    "status": "fail",
                    "message": "No transaction found for this reference.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )
