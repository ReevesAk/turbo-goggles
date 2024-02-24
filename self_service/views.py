from permissions import IsUserOrMember, IsSuperAdmin
from decouple import config
from mail import send_email

# Third party imports
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication

from .serializers import (
    RestaurantBookingSerilaizers,
    GymSubcriptionSerilaizers,
    CinemaBookingSerilaizers
)
from .models import GymSubcription, RestaurantBooking, CinemaBooking
from accounts.models import UserNotification
from wallets.controllers import Pin
from banking.controllers import Account
from banking.payments import UseCard
from banking.models import PayWithCard

picadailys_email = config("EMAIL_HOST_USER")
app_password = config("EMAIL_HOST_PASSWORD")


class TableBooking(generics.CreateAPIView):
    serializer_class = RestaurantBookingSerilaizers
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated & (IsUserOrMember | IsSuperAdmin)]

    def create(self, request, *args, **kwargs):
        serializer = RestaurantBookingSerilaizers(data=request.data)
        if serializer.is_valid(raise_exception=True):
            try:
                authenticated_user = request.user
                user_data = request.data
                pin = request.data.get("pin")

                is_verified = Pin.verify_pin(user=authenticated_user, pin=pin)
                if is_verified:
                    # Inititate a debit on a users' account.
                    amount = request.data.get("amount")
                    payment_option = request.data.get("payment_option")
                    match payment_option:
                        case "WALLET":
                            debit_response = Account.Debit(
                                amount=amount, description="Debit restaurant table booking."
                            )
                            if debit_response == 200:
                                UserNotification.objects.create(
                                    user=request.user,
                                    title="Brand Account.",
                                    messsage=f"Payment of {amount} for restaurant table booking\
                                        was successful."
                                )
                                send_email(
                                    subject="Debit Transaction.",
                                    body=f"Payment of {amount} for restaurant table booking\
                                        was successful.",
                                    sender=picadailys_email,
                                    recipients=authenticated_user.email,
                                    password=app_password,
                                )
                                serializer.save()
                                response_data = {
                                    "status": "Success!",
                                    "message": "Restaurant booking paid successfully.",
                                    "data": serializer.data
                                }

                                return Response(data=response_data, status=status.HTTP_200_OK)
                            else:
                                # initiate a credit refund to the customer after failed transaction.
                                resp = Account.Credit(
                                    first_name=authenticated_user.firstName,
                                    lastname=authenticated_user.lastName,
                                    accNo=authenticated_user.accountNumber,
                                    bankCode="103",
                                    amount=amount,
                                )
                                UserNotification.objects.create(
                                    user=request.user,
                                    title="Brand Account.",
                                    messsage=f"Acccount credited with {amount} for restaurant table booking."
                                )
                                send_email(
                                    subject="Credit Transaction.",
                                    body=f"Acccount credited with {amount} for restaurant table booking.",
                                    sender=picadailys_email,
                                    recipients=authenticated_user.email,
                                    password=app_password,
                                )
                                response_data = {
                                    "status": "Success!",
                                    "messsage": "A refund will be issued.",
                                    "details": resp,
                                }
                                

                                return Response(data=response_data, status=status.HTTP_200_OK)
                        case "CARD":
                            initialize_response = UseCard.initialize_payment(
                                amount=request.data.get("amount"),
                                customerName=authenticated_user.firstname + authenticated_user.last_name,
                                customerEmail=authenticated_user.email,
                                paymentDescription="Debit restaurant table booking"
                            )
                            if initialize_response.status_code == 200:
                                resp = initialize_response.json()["responseBody"]
                                init_pay = PayWithCard.objects.create(
                                    user=authenticated_user,
                                    transactionReference=resp["transactionReference"],
                                    paymentReference=resp["paymentReference"],
                                    customerName=authenticated_user.firstname + authenticated_user.last_name,
                                    customerEmail=authenticated_user.email,
                                    redirectUrl=resp["checkoutUrl"]
                                )
                                charge_from_card_resp = UseCard.charge(
                                    transactionReference=init_pay.transactionReference,
                                    number=request.data.get("number"),
                                    expiryMonth=request.data.get("expiryMonth"),
                                    expiryYear=request.data.get("expiryYear"),
                                    pin=request.data.get("card_pin"),
                                    cvv=request.data.get("cvv")
                                )
                                if charge_from_card_resp.status_code == 200:
                                    resp = initialize_response.json()["responseBody"]
                                    validate_card = UseCard.validate_otp(
                                        init_pay.transactionReference,
                                        tokenId=request.data.get("tokenId"),
                                        token=request.data.get("token")
                                    )
                                    if validate_card.status_code == 200:
                                        serializer = self.serializer_class(data=user_data)
                                        if serializer.is_valid(raise_exception=True):
                                            UserNotification.objects.create(
                                                user=request.user,
                                                title="Brand Account.",
                                                messsage=f"Payment of {amount} for restaurant table booking\
                                                    was successful."
                                            )
                                            serializer.save()
                                            response_data = {
                                                "status": "Success!",
                                                "message": "Debit restaurant table booking.",
                                            }

                                            return Response(data=response_data, status=status.HTTP_200_OK)

                                        else:
                                            return Response(
                                                data=serializer.errors, status=status.HTTP_400_BAD_REQUEST
                                            )
                                    else:
                                        return Response(
                                            data=debit_response.json(), status=debit_response.status_code
                                        )
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


class TableBookingDetail(generics.RetrieveAPIView):
    """
    TableBookingDetail retrieves a specific cinema booking for the authenticated user.
    """

    serializer_class = RestaurantBookingSerilaizers
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated & (IsUserOrMember | IsSuperAdmin)]

    def get_object(self):
        booking_id = self.kwargs.get('id')
        user = self.request.user

        try:
            # Check if booking exists and belongs to the user
            booking = RestaurantBooking.objects.get(pk=booking_id, user=user)
        except RestaurantBooking.DoesNotExist:
            return Response(
                {'error': 'Booking not found or does not belong to you.'},
                status=status.HTTP_404_NOT_FOUND
            )

        return booking

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)


class GymBooking(generics.CreateAPIView):
    serializer_class = GymSubcriptionSerilaizers
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated & (IsUserOrMember | IsSuperAdmin)]

    def create(self, request, *args, **kwargs):
        serializer = GymSubcriptionSerilaizers(data=request.data)
        if serializer.is_valid(raise_exception=True):
            try:
                authenticated_user = request.user
                user_data = request.data
                pin = request.data.get("pin")

                is_verified = Pin.verify_pin(user=authenticated_user, pin=pin)
                if is_verified:
                    # Inititate a debit on users' account.
                    amount = request.data.get("amount")
                    payment_option = request.data.get("payment_option")
                    match payment_option:
                        case "WALLET":
                            debit_response = Account.Debit(
                                amount=amount, description="Debit for gym booking."
                            )
                            if debit_response == 200:
                                UserNotification.objects.create(
                                    user=request.user,
                                    title="Brand Account.",
                                    messsage=f"Payment of {amount} for gym booking\
                                        was successful."
                                )
                                send_email(
                                    subject="Credit Transaction.",
                                    body=f"Payment of {amount} for gym booking\
                                        was successful.",
                                    sender=picadailys_email,
                                    recipients=authenticated_user.email,
                                    password=app_password,
                                )
                                serializer.save()
                                response_data = {
                                    "status": "Success!",
                                    "message": "Gym booking paid successfully",
                                }

                                return Response(data=response_data, status=status.HTTP_200_OK)
                            else:
                                # initiate a credit refund to the customer after failed transaction.
                                resp = Account.Credit(
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
                        case "CARD":
                            initialize_response = UseCard.initialize_payment(
                                amount=request.data.get("amount"),
                                customerName=authenticated_user.firstname + authenticated_user.last_name,
                                customerEmail=authenticated_user.email,
                                paymentDescription="Debit for gym booking."
                            )
                            if initialize_response.status_code == 200:
                                resp = initialize_response.json()["responseBody"]
                                init_pay = PayWithCard.objects.create(
                                    user=authenticated_user,
                                    transactionReference=resp["transactionReference"],
                                    paymentReference=resp["paymentReference"],
                                    customerName=authenticated_user.firstname + authenticated_user.last_name,
                                    customerEmail=authenticated_user.email,
                                    redirectUrl=resp["checkoutUrl"]
                                )
                                charge_from_card_resp = UseCard.charge(
                                    transactionReference=init_pay.transactionReference,
                                    number=request.data.get("number"),
                                    expiryMonth=request.data.get("expiryMonth"),
                                    expiryYear=request.data.get("expiryYear"),
                                    pin=request.data.get("card_pin"),
                                    cvv=request.data.get("cvv")
                                )
                                if charge_from_card_resp.status_code == 200:
                                    resp = initialize_response.json()["responseBody"]
                                    validate_card = UseCard.validate_otp(
                                        init_pay.transactionReference,
                                        tokenId=request.data.get("tokenId"),
                                        token=request.data.get("token")
                                    )
                                    if validate_card.status_code == 200:
                                        serializer = self.serializer_class(data=user_data)
                                        if serializer.is_valid(raise_exception=True):
                                            UserNotification.objects.create(
                                                user=request.user,
                                                title="Brand Account.",
                                                messsage=f"Payment of {amount} for gym booking\
                                                    was successful."
                                            )
                                            send_email(
                                                subject="Credit Transaction.",
                                                body=f"Payment of {amount} for gym booking\
                                                    was successful.",
                                                sender=picadailys_email,
                                                recipients=authenticated_user.email,
                                                password=app_password,
                                            )
                                            serializer.save()
                                            response_data = {
                                                "status": "Success!",
                                                "message": "Gym booking paid successfully",
                                            }

                                            return Response(data=response_data, status=status.HTTP_200_OK)

                                        else:
                                            return Response(
                                                data=serializer.errors, status=status.HTTP_400_BAD_REQUEST
                                            )
                                    else:
                                        return Response(
                                            data=debit_response.json(), status=debit_response.status_code
                                        )
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


class GymBookingDetail(generics.RetrieveAPIView):
    """
    GymBookingDetail retrieves a specific cinema booking for the authenticated user.
    """

    serializer_class = GymSubcriptionSerilaizers
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated & (IsUserOrMember | IsSuperAdmin)]

    def get_object(self):
        booking_id = self.kwargs.get('id')
        user = self.request.user

        try:
            # Check if booking exists and belongs to the user
            booking = GymSubcription.objects.get(pk=booking_id, user=user)
        except GymSubcription.DoesNotExist:
            return Response(
                {'error': 'Booking not found or does not belong to you.'},
                status=status.HTTP_404_NOT_FOUND
            )

        return booking

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)


class CinemaBooking(generics.CreateAPIView):
    serializer_class = CinemaBookingSerilaizers
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated & (IsUserOrMember | IsSuperAdmin)]

    def create(self, request, *args, **kwargs):
        serializer = CinemaBookingSerilaizers(data=request.data)
        if serializer.is_valid(raise_exception=True):
            try:
                authenticated_user = request.user
                user_data = request.data
                pin = request.data.get("pin")

                is_verified = Pin.verify_pin(user=authenticated_user, pin=pin)
                if is_verified:
                    # Inititate a debit on a users' account.
                    amount = request.data.get("amount")
                    payment_option = request.data.get("payment_option")
                    match payment_option:
                        case "WALLET":
                            debit_response = Account.Debit(
                                amount=amount, description="Debit for cinema seats booking."
                            )
                            if debit_response == 200:
                                UserNotification.objects.create(
                                    user=request.user,
                                    title="Brand Account.",
                                    messsage=f"Payment of {amount} for cinema seats booking\
                                        was successful."
                                )
                                send_email(
                                    subject="Credit Transaction.",
                                    body=f"Payment of {amount} for cinema seats booking\
                                        was successful.",
                                    sender=picadailys_email,
                                    recipients=authenticated_user.email,
                                    password=app_password,
                                )
                                serializer.save()
                                response_data = {
                                    "status": "Success!",
                                    "message": "Cinema seats booking paid successfully.",
                                    "data": serializer.data
                                }

                                return Response(data=response_data, status=status.HTTP_200_OK)
                            else:
                                # initiate a credit refund to the customer after failed transaction.
                                resp = Account.Credit(
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
                        case "CARD":
                            initialize_response = UseCard.initialize_payment(
                                amount=request.data.get("amount"),
                                customerName=authenticated_user.firstname + authenticated_user.last_name,
                                customerEmail=authenticated_user.email,
                                paymentDescription="Debit for cinema seats booking."
                            )
                            if initialize_response.status_code == 200:
                                resp = initialize_response.json()["responseBody"]
                                init_pay = PayWithCard.objects.create(
                                    user=authenticated_user,
                                    transactionReference=resp["transactionReference"],
                                    paymentReference=resp["paymentReference"],
                                    customerName=authenticated_user.firstname + authenticated_user.last_name,
                                    customerEmail=authenticated_user.email,
                                    redirectUrl=resp["checkoutUrl"]
                                )
                                charge_from_card_resp = UseCard.charge(
                                    transactionReference=init_pay.transactionReference,
                                    number=request.data.get("number"),
                                    expiryMonth=request.data.get("expiryMonth"),
                                    expiryYear=request.data.get("expiryYear"),
                                    pin=request.data.get("card_pin"),
                                    cvv=request.data.get("cvv")
                                )
                                if charge_from_card_resp.status_code == 200:
                                    resp = initialize_response.json()["responseBody"]
                                    validate_card = UseCard.validate_otp(
                                        init_pay.transactionReference,
                                        tokenId=request.data.get("tokenId"),
                                        token=request.data.get("token")
                                    )
                                    if validate_card.status_code == 200:
                                        serializer = self.serializer_class(data=user_data)
                                        if serializer.is_valid(raise_exception=True):
                                            UserNotification.objects.create(
                                                user=request.user,
                                                title="Brand Account.",
                                                messsage=f"Payment of {amount} for cinema seats booking\
                                                    was successful."
                                            )
                                            send_email(
                                                subject="Credit Transaction.",
                                                body=f"Payment of {amount} for cinema seats booking\
                                                    was successful.",
                                                sender=picadailys_email,
                                                recipients=authenticated_user.email,
                                                password=app_password,
                                            )
                                            serializer.save()
                                            response_data = {
                                                "status": "Success!",
                                                "message": "Debit for cinema seats booking.",
                                            }

                                            return Response(data=response_data, status=status.HTTP_200_OK)

                                        else:
                                            return Response(
                                                data=serializer.errors, status=status.HTTP_400_BAD_REQUEST
                                            )
                                    else:
                                        return Response(
                                            data=debit_response.json(), status=debit_response.status_code
                                        )
            except Exception as err:
                return Response({"error": str(err)}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class CinemaBookingList(generics.ListAPIView):
    """CinemaBookingList lists all cinema bookings."""

    serializer_class = CinemaBookingSerilaizers
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated & (IsUserOrMember | IsSuperAdmin)]

    def get_queryset(self):
        user = self.request.user
        queryset = CinemaBooking.objects.filter(user=user)
        return queryset

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.serializer_class(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class CinemaBookingDetail(generics.RetrieveAPIView):
    """
    CinemaBookingDetail retrieves a specific cinema booking for the authenticated user.
    """

    serializer_class = CinemaBookingSerilaizers
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated & (IsUserOrMember | IsSuperAdmin)]

    def get_object(self):
        booking_id = self.kwargs.get('id')
        user = self.request.user

        try:
            # Check if booking exists and belongs to the user
            booking = CinemaBooking.objects.get(pk=booking_id, user=user)
        except CinemaBooking.DoesNotExist:
            return Response(
                {'error': 'Booking not found or does not belong to you.'},
                status=status.HTTP_404_NOT_FOUND
            )

        return booking

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)
