from permissions import IsUserOrMember, IsSuperAdmin
from decouple import config
from mail import send_email

# Third party imports
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication

from .serializers import (
    RestaurantBookingSerializers,
    GymSubcriptionSerializers,
    CinemaBookingSerializers,
    CourierBookingSerializers,
    ConsumableSerializers,
    LandTravelsSerilaizers,
    HotelSerializers,
    CustomerRatingSerializer,
    GetTransactionSerializer,
)
from .models import (
    GymSubcription,
    RestaurantBooking,
    CinemaBooking,
    CourierService,
    ConsumableService,
    LandTravels,
    Hotels,
    TransactionStatus,
)
from .helpers import ProductTagmanager
from accounts.models import UserNotification, PurchaseModel
from wallets.controllers import Pin
from banking.controllers import Account
from banking.payments import UseCard
from banking.models import PayWithCard

picadailys_email = config("EMAIL_HOST_USER")
app_password = config("EMAIL_HOST_PASSWORD")

SERVICES = (
    ("restaurant", "restaurant"),
    ("gym", "gym"),
    ("cinema", "cinema"),
    ("courier", "courier"),
    ("consumable", "consumable"),
    ("land_travel", "land_travel"),
    ("hotel", "hotel"),
)


class TableBooking(generics.CreateAPIView):
    serializer_class = RestaurantBookingSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated & (IsUserOrMember | IsSuperAdmin)]

    def create(self, request, *args, **kwargs):
        serializer = RestaurantBookingSerializers(data=request.data)
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
                                amount=amount,
                                description="Debit restaurant table booking.",
                            )
                            if debit_response == 200:
                                UserNotification.objects.create(
                                    user=request.user,
                                    title="Brand Account.",
                                    message=f"Payment of {amount} for restaurant table booking\
                                        was successful.",
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
                                purchase = PurchaseModel.objects.create(
                                    user=authenticated_user,
                                    service_type="Restaurant Booking",
                                    service_id=serializer.data["id"],
                                    amount=amount,
                                )
                                tx_status = TransactionStatus.objects.create(
                                    status="Success",
                                    details="Restaurant booking paid successfully.",
                                )
                                tag = ProductTagmanager.generate(service_type="RST-")
                                current_user = RestaurantBooking.objects.get(
                                    user=authenticated_user
                                )
                                current_user.purchase = purchase
                                current_user.product_tag = tag
                                current_user.transaction_status = tx_status
                                current_user.save()

                                response_data = {
                                    "status": "Success!",
                                    "message": "Restaurant booking paid successfully.",
                                    "data": {
                                        "booking data": serializer.data,
                                        "payment method": payment_option,
                                        "product_tag": tag,
                                    },
                                }

                                return Response(
                                    data=response_data, status=status.HTTP_200_OK
                                )
                            else:
                                tx_status = TransactionStatus.objects.create(
                                    status="Fail",
                                    details="Restaurant booking failed.",
                                )
                                response_data = {
                                    "status": "fail!",
                                    "details": debit_response.json(),
                                }
                                return Response(
                                    data=response_data, status=status.HTTP_200_OK
                                )

                        case "CARD":
                            initialize_response = UseCard.initialize_payment(
                                amount=request.data.get("amount"),
                                customerName=authenticated_user.firstname
                                + authenticated_user.last_name,
                                customerEmail=authenticated_user.email,
                                paymentDescription="Debit restaurant table booking",
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
                                    expiryMonth=request.data.get("expiryMonth"),
                                    expiryYear=request.data.get("expiryYear"),
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
                                    if validate_card.status_code == 200:
                                        serializer = self.serializer_class(
                                            data=user_data
                                        )
                                        if serializer.is_valid(raise_exception=True):
                                            UserNotification.objects.create(
                                                user=request.user,
                                                title="Brand Account.",
                                                message=f"Payment of {amount} for restaurant table booking\
                                                    was successful.",
                                            )
                                            serializer.save()
                                            purchase = PurchaseModel.objects.create(
                                                user=authenticated_user,
                                                service_type="Restaurant Booking.",
                                                service_id=serializer.data["id"],
                                                amount=amount,
                                            )
                                            tx_status = TransactionStatus.objects.create(
                                                status="Success",
                                                details="Restaurant booking paid successfully.",
                                            )
                                            tag = ProductTagmanager.generate(
                                                service_type="RST-"
                                            )
                                            current_user = (
                                                RestaurantBooking.objects.get(
                                                    user=authenticated_user
                                                )
                                            )
                                            current_user.purchase = purchase
                                            current_user.product_tag = tag
                                            current_user.transaction_status = tx_status
                                            current_user.save()

                                            response_data = {
                                                "status": "Success!",
                                                "message": "Restaurant booking paid successfully.",
                                                "data": {
                                                    "booking data": serializer.data,
                                                    "payment method": payment_option,
                                                    "product_tag": tag,
                                                },
                                            }

                                            return Response(
                                                data=response_data,
                                                status=status.HTTP_200_OK,
                                            )

                                        else:
                                            return Response(
                                                data=serializer.errors,
                                                status=status.HTTP_400_BAD_REQUEST,
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
            except Exception as err:
                return Response({"error": str(err)}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class TableBookingList(generics.ListAPIView):
    """TableBookingList lists all restaurant bookings."""

    serializer_class = RestaurantBookingSerializers
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
    TableBookingDetail retrieves a specific restaurant table booking for the authenticated user.
    """

    serializer_class = RestaurantBookingSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated & (IsUserOrMember | IsSuperAdmin)]

    def get_object(self):
        booking_id = self.kwargs.get("id")
        user = self.request.user

        try:
            # Check if booking exists and belongs to the user
            booking = RestaurantBooking.objects.get(pk=booking_id, user=user)
        except RestaurantBooking.DoesNotExist:
            return Response(
                {"error": "Booking not found or does not belong to you."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return booking

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)


class GymBooking(generics.CreateAPIView):
    serializer_class = GymSubcriptionSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated & (IsUserOrMember | IsSuperAdmin)]

    def create(self, request, *args, **kwargs):
        serializer = GymSubcriptionSerializers(data=request.data)
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
                                    message=f"Payment of {amount} for gym booking\
                                        was successful.",
                                )
                                send_email(
                                    subject="Debit Transaction.",
                                    body=f"Payment of {amount} for gym booking\
                                        was successful.",
                                    sender=picadailys_email,
                                    recipients=authenticated_user.email,
                                    password=app_password,
                                )
                                serializer.save()
                                purchase = PurchaseModel.objects.create(
                                    user=authenticated_user,
                                    service_type="Gym Subscription",
                                    service_id=serializer.data["id"],
                                    amount=amount,
                                )
                                tx_status = TransactionStatus.objects.create(
                                    status="Success",
                                    details="Gym Subscription paid successfully.",
                                )
                                tag = ProductTagmanager.generate(service_type="GYM-")
                                current_user = GymSubcription.objects.get(
                                    user=authenticated_user
                                )
                                current_user.purchase = purchase
                                current_user.product_tag = tag
                                current_user.transaction_status = tx_status
                                current_user.save()

                                response_data = {
                                    "status": "Success!",
                                    "message": "Gym booking paid successfully",
                                    "data": {
                                        "booking data": serializer.data,
                                        "payment method": payment_option,
                                        "product_tag": tag,
                                    },
                                }

                                return Response(
                                    data=response_data, status=status.HTTP_200_OK
                                )
                            else:
                                response_data = {
                                    "status": "fail!",
                                    "details": debit_response.json(),
                                }
                                return Response(
                                    data=response_data, status=status.HTTP_200_OK
                                )

                        case "CARD":
                            initialize_response = UseCard.initialize_payment(
                                amount=request.data.get("amount"),
                                customerName=authenticated_user.firstname
                                + authenticated_user.last_name,
                                customerEmail=authenticated_user.email,
                                paymentDescription="Debit for gym booking.",
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
                                    expiryMonth=request.data.get("expiryMonth"),
                                    expiryYear=request.data.get("expiryYear"),
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
                                    if validate_card.status_code == 200:
                                        serializer = self.serializer_class(
                                            data=user_data
                                        )
                                        if serializer.is_valid(raise_exception=True):
                                            UserNotification.objects.create(
                                                user=request.user,
                                                title="Brand Account.",
                                                message=f"Payment of {amount} for gym booking\
                                                    was successful.",
                                            )
                                            send_email(
                                                subject="Debit Transaction.",
                                                body=f"Payment of {amount} for gym booking\
                                                    was successful.",
                                                sender=picadailys_email,
                                                recipients=authenticated_user.email,
                                                password=app_password,
                                            )
                                            serializer.save()
                                            purchase = PurchaseModel.objects.create(
                                                user=authenticated_user,
                                                service_type="Gym Subscription.",
                                                service_id=serializer.data["id"],
                                                amount=amount,
                                            )
                                            tx_status = TransactionStatus.objects.create(
                                                status="Success",
                                                details="Gym Subscription paid successfully.",
                                            )
                                            tag = ProductTagmanager.generate(
                                                service_type="GYM-"
                                            )
                                            current_user = GymSubcription.objects.get(
                                                user=authenticated_user
                                            )
                                            current_user.purchase = purchase
                                            current_user.product_tag = tag
                                            current_user.transaction_status = tx_status
                                            current_user.save()

                                            response_data = {
                                                "status": "Success!",
                                                "message": "Gym booking paid successfully",
                                                "data": {
                                                    "booking data": serializer.data,
                                                    "payment method": payment_option,
                                                    "product_tag": tag,
                                                },
                                            }
                                            return Response(
                                                data=response_data,
                                                status=status.HTTP_200_OK,
                                            )

                                        else:
                                            return Response(
                                                data=serializer.errors,
                                                status=status.HTTP_400_BAD_REQUEST,
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
            except Exception as err:
                return Response({"error": str(err)}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class GymBookingList(generics.ListAPIView):
    """GymBookingList lists all gym bookings."""

    serializer_class = GymSubcriptionSerializers
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

    serializer_class = GymSubcriptionSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated & (IsUserOrMember | IsSuperAdmin)]

    def get_object(self):
        booking_id = self.kwargs.get("id")
        user = self.request.user

        try:
            # Check if booking exists and belongs to the user
            booking = GymSubcription.objects.get(pk=booking_id, user=user)
        except GymSubcription.DoesNotExist:
            return Response(
                {"error": "Booking not found or does not belong to you."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return booking

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)


class CinemaBookingView(generics.CreateAPIView):
    serializer_class = CinemaBookingSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated & (IsUserOrMember | IsSuperAdmin)]

    def create(self, request, *args, **kwargs):
        serializer = CinemaBookingSerializers(data=request.data)
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
                                amount=amount,
                                description="Debit for cinema seats booking.",
                            )
                            if debit_response == 200:
                                UserNotification.objects.create(
                                    user=request.user,
                                    title="Brand Account.",
                                    message=f"Payment of {amount} for cinema seats booking\
                                        was successful.",
                                )
                                send_email(
                                    subject="Debit Transaction.",
                                    body=f"Payment of {amount} for cinema seats booking\
                                        was successful.",
                                    sender=picadailys_email,
                                    recipients=authenticated_user.email,
                                    password=app_password,
                                )
                                serializer.save()
                                purchase = PurchaseModel.objects.create(
                                    user=authenticated_user,
                                    service_type="Cinema Booking.",
                                    service_id=serializer.data["id"],
                                    amount=amount,
                                )
                                tx_status = TransactionStatus.objects.create(
                                    status="Success",
                                    details="Cinema seats paid successfully.",
                                )
                                tag = ProductTagmanager.generate(service_type="CIN-")
                                current_user = CinemaBooking.objects.get(
                                    user=authenticated_user
                                )
                                current_user.purchase = purchase
                                current_user.product_tag = tag
                                current_user.transaction_status = tx_status
                                current_user.save()

                                response_data = {
                                    "status": "Success!",
                                    "message": "Cinema seats booking paid successfully.",
                                    "data": {
                                        "booking data": serializer.data,
                                        "payment method": payment_option,
                                        "product_tag": tag,
                                    },
                                }

                                return Response(
                                    data=response_data, status=status.HTTP_200_OK
                                )
                            else:
                                response_data = {
                                    "status": "fail!",
                                    "details": debit_response.json(),
                                }
                                return Response(
                                    data=response_data, status=status.HTTP_200_OK
                                )

                        case "CARD":
                            initialize_response = UseCard.initialize_payment(
                                amount=request.data.get("amount"),
                                customerName=authenticated_user.firstname
                                + authenticated_user.last_name,
                                customerEmail=authenticated_user.email,
                                paymentDescription="Debit for cinema seats booking.",
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
                                    expiryMonth=request.data.get("expiryMonth"),
                                    expiryYear=request.data.get("expiryYear"),
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
                                    if validate_card.status_code == 200:
                                        serializer = self.serializer_class(
                                            data=user_data
                                        )
                                        if serializer.is_valid(raise_exception=True):
                                            UserNotification.objects.create(
                                                user=request.user,
                                                title="Debit Transaction.",
                                                message=f"Payment of {amount} for cinema seats booking\
                                                    was successful.",
                                            )
                                            send_email(
                                                subject="Debit Transaction.",
                                                body=f"Payment of {amount} for cinema seats booking\
                                                    was successful.",
                                                sender=picadailys_email,
                                                recipients=authenticated_user.email,
                                                password=app_password,
                                            )
                                            serializer.save()
                                            purchase = PurchaseModel.objects.create(
                                                user=authenticated_user,
                                                service_type="Cinema Booking.",
                                                service_id=serializer.data["id"],
                                                amount=amount,
                                            )
                                            tx_status = TransactionStatus.objects.create(
                                                status="Success",
                                                details="Cinema seats paid successfully.",
                                            )
                                            tag = ProductTagmanager.generate(
                                                service_type="CIN-"
                                            )
                                            current_user = CinemaBooking.objects.get(
                                                user=authenticated_user
                                            )
                                            current_user.purchase = purchase
                                            current_user.product_tag = tag
                                            current_user.transaction_status = tx_status
                                            current_user.save()

                                            response_data = {
                                                "status": "Success!",
                                                "message": "Cinema seats booking paid successfully.",
                                                "data": {
                                                    "booking data": serializer.data,
                                                    "payment method": payment_option,
                                                    "product_tag": tag,
                                                },
                                            }

                                            return Response(
                                                data=response_data,
                                                status=status.HTTP_200_OK,
                                            )

                                        else:
                                            return Response(
                                                data=serializer.errors,
                                                status=status.HTTP_400_BAD_REQUEST,
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
            except Exception as err:
                return Response({"error": str(err)}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class CinemaBookingList(generics.ListAPIView):
    """CinemaBookingList lists all cinema bookings."""

    serializer_class = CinemaBookingSerializers
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

    serializer_class = CinemaBookingSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated & (IsUserOrMember | IsSuperAdmin)]

    def get_object(self):
        booking_id = self.kwargs.get("id")
        user = self.request.user

        try:
            # Check if booking exists and belongs to the user
            booking = CinemaBooking.objects.get(pk=booking_id, user=user)
        except CinemaBooking.DoesNotExist:
            return Response(
                {"error": "Booking not found or does not belong to you."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return booking

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)


class BookCourierSercvice(generics.CreateAPIView):
    serializer_class = CourierBookingSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated & (IsUserOrMember | IsSuperAdmin)]

    def create(self, request, *args, **kwargs):
        serializer = CourierBookingSerializers(data=request.data)
        if serializer.is_valid(raise_exception=True):
            try:
                authenticated_user = request.user
                user_data = request.data
                pin = request.data.get("pin")

                is_verified = Pin.verify_pin(user=authenticated_user, pin=pin)
                if is_verified:
                    # Inititate a debit on a users' account.
                    amount = request.data.get("price_per_kg")
                    payment_option = request.data.get("payment_option")
                    match payment_option:
                        case "WALLET":
                            debit_response = Account.Debit(
                                amount=amount,
                                description="Debit for booking courier service.",
                            )
                            if debit_response == 200:
                                UserNotification.objects.create(
                                    user=request.user,
                                    title="Courier Service Booking.",
                                    message=f"Payment of {amount} for courier service booking\
                                        was successful.",
                                )
                                send_email(
                                    subject="Debit Transaction.",
                                    body=f"Payment of {amount} for courier service booking\
                                        was successful.",
                                    sender=picadailys_email,
                                    recipients=authenticated_user.email,
                                    password=app_password,
                                )
                                serializer.save()
                                purchase = PurchaseModel.objects.create(
                                    user=authenticated_user,
                                    service_type="Courier Service.",
                                    service_id=serializer.data["id"],
                                    amount=amount,
                                )
                                tx_status = TransactionStatus.objects.create(
                                    status="Success",
                                    details="Cinema seats paid successfully.",
                                )
                                tag = ProductTagmanager.generate(service_type="COU-")
                                current_user = CourierService.objects.get(
                                    user=authenticated_user
                                )
                                current_user.purchase = purchase
                                current_user.product_tag = tag
                                current_user.transaction_status = tx_status
                                current_user.save()

                                response_data = {
                                    "status": "Success!",
                                    "message": "Courier service booking paid successfully.",
                                    "data": {
                                        "booking data": serializer.data,
                                        "payment method": payment_option,
                                        "product_tag": tag,
                                    },
                                }

                                return Response(
                                    data=response_data, status=status.HTTP_200_OK
                                )
                            else:
                                response_data = {
                                    "status": "fail!",
                                    "details": debit_response.json(),
                                }
                                return Response(
                                    data=response_data, status=status.HTTP_200_OK
                                )

                        case "CARD":
                            initialize_response = UseCard.initialize_payment(
                                amount=request.data.get("amount"),
                                customerName=authenticated_user.firstname
                                + authenticated_user.last_name,
                                customerEmail=authenticated_user.email,
                                paymentDescription="Debit for booking courier service.",
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
                                    expiryMonth=request.data.get("expiryMonth"),
                                    expiryYear=request.data.get("expiryYear"),
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
                                    if validate_card.status_code == 200:
                                        serializer = self.serializer_class(
                                            data=user_data
                                        )
                                        if serializer.is_valid(raise_exception=True):
                                            UserNotification.objects.create(
                                                user=request.user,
                                                title="Debit Transaction.",
                                                message=f"Payment of {amount} for courier service booking\
                                                    was successful.",
                                            )
                                            send_email(
                                                subject="Debit Transaction.",
                                                body=f"Payment of {amount} for courier  service booking\
                                                    was successful.",
                                                sender=picadailys_email,
                                                recipients=authenticated_user.email,
                                                password=app_password,
                                            )
                                            serializer.save()
                                            purchase = PurchaseModel.objects.create(
                                                user=authenticated_user,
                                                service_type="Courier Service.",
                                                service_id=serializer.data["id"],
                                                amount=amount,
                                            )
                                            tx_status = TransactionStatus.objects.create(
                                                status="Success",
                                                details="Courier service booking paid successfully.",
                                            )
                                            tag = ProductTagmanager.generate(
                                                service_type="COU-"
                                            )
                                            current_user = CourierService.objects.get(
                                                user=authenticated_user
                                            )
                                            current_user.purchase = purchase
                                            current_user.product_tag = tag
                                            current_user.transaction_status = tx_status
                                            current_user.save()

                                            response_data = {
                                                "status": "Success!",
                                                "message": "Courier service booking paid successfully.",
                                                "data": {
                                                    "booking data": serializer.data,
                                                    "payment method": payment_option,
                                                    "product_tag": tag,
                                                },
                                            }
                                            return Response(
                                                data=response_data,
                                                status=status.HTTP_200_OK,
                                            )

                                        else:
                                            return Response(
                                                data=serializer.errors,
                                                status=status.HTTP_400_BAD_REQUEST,
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
            except Exception as err:
                return Response({"error": str(err)}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class CourierBookingList(generics.ListAPIView):
    """CourierBookingList lists all courier bookings."""

    serializer_class = CourierBookingSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated & (IsUserOrMember | IsSuperAdmin)]

    def get_queryset(self):
        user = self.request.user
        queryset = CourierService.objects.filter(user=user)
        return queryset

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.serializer_class(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class CourierBookingDetail(generics.RetrieveAPIView):
    """
    CourierBookingDetail retrieves a specific courier booking for
    the authenticated user.
    """

    serializer_class = CourierBookingSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated & (IsUserOrMember | IsSuperAdmin)]

    def get_object(self):
        booking_id = self.kwargs.get("id")
        user = self.request.user

        try:
            # Check if booking exists and belongs to the user
            booking = CourierService.objects.get(pk=booking_id, user=user)
        except CourierService.DoesNotExist:
            return Response(
                {"error": "Booking not found or does not belong to you."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return booking

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)


class BookConsumableSercvice(generics.CreateAPIView):
    serializer_class = CourierBookingSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated & (IsUserOrMember | IsSuperAdmin)]
    queryset = ConsumableService.objects.all()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid(raise_exception=True):
            serializer.save()  # Save booking details.

            price = request.data.get("price")

            UserNotification.objects.create(
                user=request.user,
                title="Debit Transaction.",
                message=f"Booking of {price} for consumable service booking\
                    was successful.",
            )
            send_email(
                subject="Product bbooking.",
                body=f"Booking of {price} for your consumable  service booking\
                    was successful.",
                sender=picadailys_email,
                recipients=request.data.get("contact"),
                password=app_password,
            )
            serializer.save()
            purchase = PurchaseModel.objects.create(
                user=request.user,
                service_type="Consumable Service.",
                service_id=serializer.data["id"],
                amount=price,
            )
            tx_status = TransactionStatus.objects.create(
                status="Success",
                details="Coonsumable service booked successfully.",
            )
            tag = ProductTagmanager.generate(service_type="FMCG-")
            current_user = ConsumableService.objects.get(user=request.user)
            current_user.purchase = purchase
            current_user.product_tag = tag
            current_user.transaction_status = tx_status
            current_user.save()

            response_data = {
                "status": "success",
                "message": "Service booked successfully!",
                "data": {
                    "booking data": serializer.data,
                    "product_tag": tag,
                },
            }
            return Response(data=response_data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ConsumableBookingList(generics.ListAPIView):
    """ConsumableBookingList lists all consumable bookings."""

    serializer_class = ConsumableSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated & (IsUserOrMember | IsSuperAdmin)]

    def get_queryset(self):
        user = self.request.user
        queryset = ConsumableService.objects.filter(user=user)
        return queryset

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.serializer_class(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class ConsumableBookingDetail(generics.RetrieveAPIView):
    """
    ConsumableBookingDetail retrieves a specific consumable booking for
    the authenticated user.
    """

    serializer_class = ConsumableSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated & (IsUserOrMember | IsSuperAdmin)]

    def get_object(self):
        booking_id = self.kwargs.get("id")
        user = self.request.user

        try:
            # Check if booking exists and belongs to the user
            booking = ConsumableService.objects.get(pk=booking_id, user=user)
        except ConsumableService.DoesNotExist:
            return Response(
                {"error": "Booking not found or does not belong to you."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return booking

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)


class BookLandTrip(generics.GenericAPIView):
    """
    BookLandTrip is an POST request route for booking a land trip, one way or round trip.
    """

    serializer_class = LandTravelsSerilaizers
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated & (IsUserOrMember | IsSuperAdmin)]

    def post(self, request):
        serializer = CourierBookingSerializers(data=request.data)
        if serializer.is_valid(raise_exception=True):
            try:
                authenticated_user = request.user
                trip_pattern = request.data.get("trip_pattern")
                payload = request.data

                trip_date = (payload["trip_date"],)
                departure_state = (payload["departure_state"],)
                terminal = (payload["terminal"],)
                destination = (payload["destination"],)
                no_of_adults = (payload["no_of_adults"],)
                no_of_children = (payload["no_of_children"],)
                trip_type = (payload["trip_type"],)
                trip_pattern = payload["trip_pattern"]

                LandTravels.objects.create(
                    user=authenticated_user,
                    trip_date=trip_date,
                    departure_state=departure_state,
                    terminal=terminal,
                    destination=destination,
                    no_of_adults=no_of_adults,
                    no_of_children=no_of_children,
                    trip_type=trip_type,
                    trip_pattern=trip_pattern,
                )

                data = {
                    "trip_date": request.data.get("trip_date"),
                    "departure_state": request.data.get("departure_state"),
                    "terminal": request.data.get("terminal"),
                    "destination": request.data.get("destination"),
                    "no_of_children": request.data.get("no_of_children"),
                    "trip_type": request.data.get("trip_type"),
                    "trip_pattern": request.data.get("trip_pattern"),
                }

                match trip_pattern:
                    case "One Way":
                        purchase = PurchaseModel.objects.create(
                            user=authenticated_user,
                            service_type="Land Travels Service.",
                            service_id=serializer.data["id"],
                            amount="",
                        )
                        tx_status = TransactionStatus.objects.create(
                            status="Success",
                            details="One way trip booked booked successfully.",
                        )
                        tag = ProductTagmanager.generate(service_type="LTS-")
                        current_user = LandTravels.objects.get(user=request.user)
                        current_user.purchase = purchase
                        current_user.product_tag = tag
                        current_user.transaction_status = tx_status
                        current_user.save()

                        response = {
                            "status": "success!",
                            "message": f"You have successfully booked a one way trip from {departure_state} to {destination}.",
                            "data": {
                                "booking data": data,
                                "product_tag": tag,
                            },
                        }
                        return Response(data=response, status=status.HTTP_201_CREATED)
                    case "Round Trip":
                        purchase = PurchaseModel.objects.create(
                            user=authenticated_user,
                            service_type="Land Travels Service.",
                            service_id=serializer.data["id"],
                            amount="",
                        )
                        tx_status = TransactionStatus.objects.create(
                            status="Success",
                            details="Round trip booked successfully.",
                        )
                        tag = ProductTagmanager.generate(service_type="LTS-")
                        current_user = LandTravels.objects.get(user=request.user)
                        current_user.purchase = purchase
                        current_user.product_tag = tag
                        current_user.transaction_status = tx_status
                        current_user.save()

                        response = {
                            "status": "success!",
                            "message": f"You have successfully booked a round trip from {departure_state} to {destination} and {destination} to {departure_state}.",
                            "data": {
                                "booking data": data,
                                "product_tag": tag,
                            },
                        }
                        return Response(data=response, status=status.HTTP_201_CREATED)

            except Exception as err:
                return Response({"error": str(err)}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LandTripBookingDetail(generics.RetrieveAPIView):
    """
    LandTripBookingDetail retrieves a specific land trip booking for
    the authenticated user.
    """

    serializer_class = LandTravelsSerilaizers
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated & (IsUserOrMember | IsSuperAdmin)]

    def get_object(self):
        booking_id = self.kwargs.get("id")
        user = self.request.user

        try:
            # Check if booking exists and belongs to the user
            booking = LandTravels.objects.get(id=booking_id, user=user)
        except LandTravels.DoesNotExist:
            return Response(
                {"error": "Booking not found or does not belong to you."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return booking

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)


class LandTripBookingList(generics.ListAPIView):
    """LandTripBookingList lists all land travel bookings."""

    serializer_class = LandTravelsSerilaizers
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated & (IsUserOrMember | IsSuperAdmin)]

    def get_queryset(self):
        user = self.request.user
        queryset = LandTravels.objects.filter(user=user)
        return queryset

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.serializer_class(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class BookHotel(generics.GenericAPIView):
    """
    BookHotel is a POST request route for booking a hotel.
    """

    serializer_class = HotelSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated & (IsUserOrMember | IsSuperAdmin)]

    def post(self, request):
        serializer = CourierBookingSerializers(data=request.data)
        if serializer.is_valid(raise_exception=True):
            try:
                authenticated_user = request.user
                user_data = request.data
                pin = request.data.get("pin")

                is_verified = Pin.verify_pin(user=authenticated_user, pin=pin)
                if is_verified:
                    # Inititate a debit on a users' account.
                    amount = request.data.get("price_per_kg")
                    payment_option = request.data.get("payment_option")
                    match payment_option:
                        case "WALLET":
                            debit_response = Account.Debit(
                                amount=amount,
                                description="Debit for hotel booking.",
                            )
                            if debit_response == 200:
                                UserNotification.objects.create(
                                    user=request.user,
                                    title="Hotel Booking.",
                                    message=f"Payment of {amount} for hotel booking\
                                        was successful.",
                                )
                                send_email(
                                    subject="Debit Transaction.",
                                    body=f"Payment of {amount} for hotel booking\
                                        was successful.",
                                    sender=picadailys_email,
                                    recipients=authenticated_user.email,
                                    password=app_password,
                                )
                                serializer.save()
                                purchase = PurchaseModel.objects.create(
                                    user=authenticated_user,
                                    service_type="Hotel Service.",
                                    service_id=serializer.data["id"],
                                    amount=amount,
                                )
                                tx_status = TransactionStatus.objects.create(
                                    status="Success",
                                    details="Hotel service booking paid successfully.",
                                )
                                tag = ProductTagmanager.generate(service_type="LTS-")
                                current_user = Hotels.objects.get(user=request.user)
                                current_user.purchase = purchase
                                current_user.product_tag = tag
                                current_user.transaction_status = tx_status
                                current_user.save()

                                response_data = {
                                    "status": "Success!",
                                    "message": "Hotel service booking paid successfully.",
                                    "data": {
                                        "booking data": serializer.data,
                                        "product_tag": tag,
                                    },
                                }

                                return Response(
                                    data=response_data, status=status.HTTP_200_OK
                                )
                            else:
                                response_data = {
                                    "status": "fail!",
                                    "details": debit_response.json(),
                                }
                                return Response(
                                    data=response_data, status=status.HTTP_200_OK
                                )
                        case "CARD":
                            initialize_response = UseCard.initialize_payment(
                                amount=request.data.get("amount"),
                                customerName=authenticated_user.firstname
                                + authenticated_user.last_name,
                                customerEmail=authenticated_user.email,
                                paymentDescription="Debit for hotel booking.",
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
                                    expiryMonth=request.data.get("expiryMonth"),
                                    expiryYear=request.data.get("expiryYear"),
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
                                    if validate_card.status_code == 200:
                                        serializer = self.serializer_class(
                                            data=user_data
                                        )
                                        if serializer.is_valid(raise_exception=True):
                                            UserNotification.objects.create(
                                                user=request.user,
                                                title="Debit Transaction.",
                                                message=f"Payment of {amount} for hotel booking\
                                                    was successful.",
                                            )
                                            send_email(
                                                subject="Debit Transaction.",
                                                body=f"Payment of {amount} for hotel booking\
                                                    was successful.",
                                                sender=picadailys_email,
                                                recipients=authenticated_user.email,
                                                password=app_password,
                                            )
                                            serializer.save()
                                            purchase = PurchaseModel.objects.create(
                                                user=authenticated_user,
                                                service_type="Hotel Service.",
                                                service_id=serializer.data["id"],
                                                amount=amount,
                                            )
                                            tx_status = TransactionStatus.objects.create(
                                                status="Success",
                                                details="Hotel service booking paid successfully.",
                                            )
                                            tag = ProductTagmanager.generate(
                                                service_type="LTS-"
                                            )
                                            current_user = Hotels.objects.get(
                                                user=request.user
                                            )
                                            current_user.purchase = purchase
                                            current_user.product_tag = tag
                                            current_user.transaction_status = tx_status
                                            current_user.save()

                                            response_data = {
                                                "status": "Success!",
                                                "message": "Hotel service booking paid successfully.",
                                                "data": {
                                                    "booking data": serializer.data,
                                                    "product_tag": tag,
                                                },
                                            }

                                            return Response(
                                                data=response_data,
                                                status=status.HTTP_200_OK,
                                            )

                                        else:
                                            return Response(
                                                data=serializer.errors,
                                                status=status.HTTP_400_BAD_REQUEST,
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
            except Exception as err:
                return Response({"error": str(err)}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ServiceRating(generics.GenericAPIView):
    """
    ServiceRating is the POST request that allows a customer to rate a
    service on self-service.

    - `service_type`: This represents the servive type the customer is rating.
    - Example of service types: \n
        `restaurant`\n
        `gym`\n
        `cinema`\n
        `courier`\n
        `consumable`\n
        `land_travel`\n
        `hotel`\n
    `rating`: This comes in numbers 1-5 depending on the quality of the service provided.\n
    `review`: The review is a written appraisal of the product comnsumed.
    """

    serializer_class = CustomerRatingSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated & (IsUserOrMember | IsSuperAdmin)]
    lookup_field = "id"

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid(raise_exception=True):
            user = request.user
            service_id = kwargs.get("id")
            service_type = kwargs.get("service_type")

            service_models = {
                "restaurant": RestaurantBooking,
                "gym": GymSubcription,
                "cinema": CinemaBooking,
                "courier": CourierService,
                "consumable": ConsumableService,
                "land_travel": LandTravels,
                "hotel": Hotels,
            }

            service_model = service_models.get(service_type)

            if service_model is None:
                return Response(
                    {"error": "Invalid service type."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            try:
                # Get the service instance
                service = service_model.objects.get(id=service_id)

                # Check if the user has already rated this service
                if user in service.rated_by.all():
                    return Response(
                        {"error": "You have already rated this service."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                # Add user to the list of users who rated this service
                service.rated_by.add(user)

                # Save the rating linked to the service
                serializer.save(service=service)

                return Response(
                    {"success": "Service rating added successfully."},
                    status=status.HTTP_201_CREATED,
                )
            except service_model.DoesNotExist:
                return Response(
                    {"error": "Service not found."}, status=status.HTTP_404_NOT_FOUND
                )
        else:
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class GetTransaction(generics.RetrieveAPIView):
    """
    GetTransaction is the GET request route used
    to retrieve a transaction using product tag.
    """

    serializer_class = GetTransactionSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated & (IsUserOrMember | IsSuperAdmin)]

    def get_queryset(self, request):
        payment_tag = request.data["payment_tag"]
        prefix_length = 3

        # Extract the prefix from the payment tag
        prefix = payment_tag[:prefix_length]

        # Define a dictionary mapping prefixes to model filters
        model_filters = {
            "RST": RestaurantBooking.objects.filter(payment_tag=payment_tag),
            "GYM": GymSubcription.objects.filter(payment_tag__startswith=prefix),
            "CIN": CinemaBooking.objects.filter(payment_tag__startswith=prefix),
            "COU": CourierService.objects.filter(payment_tag__startswith=prefix),
            "FMCG": ConsumableService.objects.filter(payment_tag__startswith=prefix),
            "LTS": LandTravels.objects.filter(payment_tag__startswith=prefix),
            "HOT": Hotels.objects.filter(payment_tag__startswith=prefix),
        }

        if prefix in model_filters:
            self.queryset = model_filters[prefix]
        else:
            self.queryset = None

        return self.queryset

    def get_serializer_class(self):
        prefix = self.request.path_info.split("/")[2].lower()

        # Define a dictionary mapping prefixes to serializer classes
        serializer_classes = {
            "RST": RestaurantBookingSerializers,
            "GYM": GymSubcriptionSerializers,
            "CIN": CinemaBookingSerializers,
            "COU": CourierBookingSerializers,
            "FMCG": ConsumableSerializers,
            "LTS": LandTravelsSerilaizers,
            "HOT": HotelSerializers,
        }

        return serializer_classes.get(prefix)

    def get(self, request, *args, **kwargs):
        response = super().get(request, *args, **kwargs)
        if not response.data:
            return Response(
                data={"error": "Transaction not found."},
                status=status.HTTP_400_BAD_REQUEST,
            )
