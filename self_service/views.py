from permissions import IsUserOrMember, IsSuperAdmin

# Third party imports
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication

from .serializers import RestaurantBookingSerilaizers, GymSubcriptionSerilaizers
from .models import GymSubcription, RestaurantBooking
from wallets.controllers import Pin, Debit, Credit


class TableBooking(generics.CreateAPIView):
    serializer_class = RestaurantBookingSerilaizers
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated & (IsUserOrMember | IsSuperAdmin)]

    def create(self, request, *args, **kwargs):
        serializer = RestaurantBookingSerilaizers(data=request.data)
        if serializer.is_valid(raise_exception=True):
            try:
                authenticated_user = request.user
                pin = request.data.get("pin")

                is_verified = Pin.verify_pin(user=authenticated_user, pin=pin)
                if is_verified:
                    # Inititate a debit on a users' account.
                    amount = request.data.get("amount")
                    debit_response = Debit.debit_customer(
                        amount=amount, description="Debit restaurant table booking"
                    )
                    if debit_response == 200:
                        serializer.save()
                        response_data = {
                            "status": "Success!",
                            "message": "Restaurant booking paid successfully",
                        }

                        return Response(data=response_data, status=status.HTTP_200_OK)
                    else:
                        # initiate a credit refund to the customer after failed transaction.
                        resp = Credit.credit_customer(
                            first_name=authenticated_user.firstName,
                            lastname=authenticated_user.lastName,
                            accNo=authenticated_user.accountNumber,
                            bankCode="103",
                            amount=amount,
                        )
                        response_data = {
                            "status": "Success!",
                            "messsage": "A refund will be issued.",
                            "details": resp,
                        }

                        return Response(data=response_data, status=status.HTTP_200_OK)

            except Exception as err:
                return Response({"error": str(err)}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class TableBookingList(generics.ListAPIView):
    """TableBookingList lists all restaurant bookings."""

    serializer_class = RestaurantBookingSerilaizers
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated & (IsUserOrMember | IsSuperAdmin)]

    def get_queryset(self):
        user = self.request.user
        queryset = RestaurantBooking.objects.filter(user=user)
        return queryset

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.serializer_class(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class GymBooking(generics.CreateAPIView):
    serializer_class = GymSubcriptionSerilaizers
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated & (IsUserOrMember | IsSuperAdmin)]

    def create(self, request, *args, **kwargs):
        serializer = GymSubcriptionSerilaizers(data=request.data)
        if serializer.is_valid(raise_exception=True):
            try:
                authenticated_user = request.user
                pin = request.data.get("pin")

                is_verified = Pin.verify_pin(user=authenticated_user, pin=pin)
                if is_verified:
                    # Inititate a debit on users' account.
                    amount = request.data.get("amount")
                    debit_response = Debit.debit_customer(
                        amount=amount, description="Debit gym booking"
                    )
                    if debit_response == 200:
                        serializer.save()
                        response_data = {
                            "status": "Success!",
                            "message": "Gym booking paid successfully",
                        }

                        return Response(data=response_data, status=status.HTTP_200_OK)
                    else:
                        # initiate a credit refund to the customer after failed transaction.
                        resp = Credit.credit_customer(
                            first_name=authenticated_user.firstName,
                            lastname=authenticated_user.lastName,
                            accNo=authenticated_user.accountNumber,
                            bankCode="103",
                            amount=amount,
                        )
                        response_data = {
                            "status": "Success!",
                            "messsage": "A refund will be issued.",
                            "details": resp,
                        }

                        return Response(data=response_data, status=status.HTTP_200_OK)

            except Exception as err:
                return Response({"error": str(err)}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class GymBookingList(generics.ListAPIView):
    """GymBookingList lists all gym bookings."""

    serializer_class = GymSubcriptionSerilaizers
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated & (IsUserOrMember | IsSuperAdmin)]

    def get_queryset(self):
        user = self.request.user
        queryset = GymSubcription.objects.filter(user=user)
        return queryset

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.serializer_class(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
