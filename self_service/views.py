from permissions import IsUserOrMember, IsSuperAdmin

# Third party imports
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.exceptions import NotFound
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.pagination import PageNumberPagination

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
from banking.helpers import Pin
from banking.controllers import Account
from banking.models import AccountCreation
from commons import Biometrics
from roles.models import ActivityModel


SERVICES = (
    ("restaurant", "restaurant"),
    ("gym", "gym"),
    ("cinema", "cinema"),
    ("courier", "courier"),
    ("consumable", "consumable"),
    ("land_travel", "land_travel"),
    ("hotel", "hotel"),
)


class PaginationStyle(PageNumberPagination):
    page_size = 10


class TableBooking(generics.CreateAPIView):
    serializer_class = RestaurantBookingSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated & (IsUserOrMember | IsSuperAdmin)]

    def create(self, request, *args, **kwargs):
        serializer = RestaurantBookingSerializers(data=request.data)
        if serializer.is_valid(raise_exception=True):
            try:
                authenticated_user = request.user
                user_data = {
                    key: value.strip() if isinstance(value, str) else value
                    for key, value in request.data.items()
                }
                pin = user_data("pin")

                biometrics = request.data.get("use_biometrics")

                try:
                    account = AccountCreation.objects.get(user=authenticated_user)
                except AccountCreation.DoesNotExist:
                    return Response(
                        data={"status": "fail", "error": "Account not found for user"},
                        status=status.HTTP_404_NOT_FOUND,
                    )

                if biometrics:
                    verification = Biometrics.authenticate(
                        authenticated_user.phone_number
                    )
                else:
                    if account and account.pin is not None:
                        verification = Pin.verify(
                            user=authenticated_user, pin=pin, hashed_pin=account.pin
                        )
                    else:
                        return Response(
                            data={
                                "status": "fail",
                                "error": "Account or PIN not found for user",
                            },
                            status=status.HTTP_404_NOT_FOUND,
                        )

                if not verification:
                    return Response(
                        data={"status": "fail", "error": "Invalid credentials"},
                        status=status.HTTP_401_UNAUTHORIZED,
                    )

                # Inititate a debit on a users' account.
                amount = request.data.get("amount")
                payment_option = user_data("payment_option")
                user_details = AccountCreation.objects.get(user=authenticated_user)
                match payment_option:
                    case "WALLET":
                        debit_response = Account.Debit(
                            debitAccount=user_details.account_number,
                            amount=amount,
                            reason="Debit restaurant table booking",
                            transactionReference="",
                        )
                        if debit_response == 200:
                            current_user = request.user
                            UserNotification.objects.create(
                                user=current_user,
                                title="Table Booking.",
                                message=f"Payment of {amount} for restaurant table booking\
                                    was successful.",
                            )

                            ActivityModel.objects.create(
                                user=current_user,
                                title="Table Booking.",
                                description=f"{current_user.first_name} {current_user.last_name} made a payment of {amount} for restaurant table booking.",
                            )

                            # send transactional email.
                            # TODO

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
                        pass
            except Exception as err:
                return Response({"error": str(err)}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class TableBookingList(generics.ListAPIView):
    """TableBookingList lists all restaurant bookings."""

    serializer_class = RestaurantBookingSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated & (IsUserOrMember | IsSuperAdmin)]
    pagination_class = PaginationStyle

    def get_queryset(self):
        user = self.request.user
        queryset = RestaurantBooking.objects.filter(user=user)
        return queryset

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.serializer_class(page, many=True)
            return self.get_paginated_response(serializer.data)

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
                user_data = {
                    key: value.strip() if isinstance(value, str) else value
                    for key, value in request.data.items()
                }
                pin = request.data.get("pin")
                biometrics = request.data.get("use_biometrics")

                try:
                    account = AccountCreation.objects.get(user=authenticated_user)
                except AccountCreation.DoesNotExist:
                    return Response(
                        data={"status": "fail", "error": "Account not found for user"},
                        status=status.HTTP_404_NOT_FOUND,
                    )

                if biometrics:
                    verification = Biometrics.authenticate(
                        authenticated_user.phone_number
                    )
                else:
                    if account and account.pin is not None:
                        verification = Pin.verify(
                            user=authenticated_user, pin=pin, hashed_pin=account.pin
                        )
                    else:
                        return Response(
                            data={
                                "status": "fail",
                                "error": "Account or PIN not found for user",
                            },
                            status=status.HTTP_404_NOT_FOUND,
                        )

                if not verification:
                    return Response(
                        data={"status": "fail", "error": "Invalid credentials"},
                        status=status.HTTP_401_UNAUTHORIZED,
                    )

                # Inititate a debit on users' account.
                amount = request.data.get("amount")
                payment_option = user_data("payment_option")
                user_details = AccountCreation.objects.get(user=authenticated_user)
                match payment_option:
                    case "WALLET":
                        debit_response = Account.Debit(
                            debitAccount=user_details.account_number,
                            amount=amount,
                            reason="Debit for gym subscription.",
                            transactionReference="",
                        )
                        if debit_response == 200:
                            UserNotification.objects.create(
                                user=authenticated_user,
                                title="Gym Booking.",
                                message=f"Payment of {amount} for gym booking\
                                    was successful.",
                            )

                            ActivityModel.objects.create(
                                user=authenticated_user,
                                title="Gym Booking.",
                                description=f"{authenticated_user.first_name} {authenticated_user.last_name} made a payment of {amount} for gym subscription.",
                            )
                            # send transactional email.
                            # TODO

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
                        pass
            except Exception as err:
                return Response({"error": str(err)}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class GymBookingList(generics.ListAPIView):
    """GymBookingList lists all gym bookings."""

    serializer_class = GymSubcriptionSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated & (IsUserOrMember | IsSuperAdmin)]
    pagination_class = PaginationStyle

    def get_queryset(self):
        user = self.request.user
        queryset = GymSubcription.objects.filter(user=user)
        return queryset

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.serializer_class(page, many=True)
            return self.get_paginated_response(serializer.data)

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
                user_data = {
                    key: value.strip() if isinstance(value, str) else value
                    for key, value in request.data.items()
                }
                pin = user_data("pin")
                biometrics = request.data.get("use_biometrics")

                try:
                    account = AccountCreation.objects.get(user=authenticated_user)
                except AccountCreation.DoesNotExist:
                    return Response(
                        data={"status": "fail", "error": "Account not found for user"},
                        status=status.HTTP_404_NOT_FOUND,
                    )

                if biometrics:
                    verification = Biometrics.authenticate(
                        authenticated_user.phone_number
                    )
                else:
                    if account and account.pin is not None:
                        verification = Pin.verify(
                            user=authenticated_user, pin=pin, hashed_pin=account.pin
                        )
                    else:
                        return Response(
                            data={
                                "status": "fail",
                                "error": "Account or PIN not found for user",
                            },
                            status=status.HTTP_404_NOT_FOUND,
                        )

                if not verification:
                    return Response(
                        data={"status": "fail", "error": "Invalid credentials"},
                        status=status.HTTP_401_UNAUTHORIZED,
                    )

                # Inititate a debit on a users' account.
                amount = request.data.get("amount")
                payment_option = user_data("payment_option")
                user_details = AccountCreation.objects.get(user=authenticated_user)
                match payment_option:
                    case "WALLET":
                        debit_response = Account.Debit(
                            debitAccount=user_details.account_number,
                            amount=amount,
                            reason="Debit for cinema seats booking.",
                            transactionReference="",
                        )
                        if debit_response == 200:
                            UserNotification.objects.create(
                                user=authenticated_user,
                                title="Cinema Booking.",
                                message=f"Payment of {amount} for cinema seats booking\
                                    was successful.",
                            )

                            ActivityModel.objects.create(
                                user=authenticated_user,
                                title="Cinema Booking.",
                                description=f"{authenticated_user.first_name} {authenticated_user.last_name} made a payment of {amount} for cinema seats booking.",
                            )

                            # send transactional email.
                            # TODO

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
                        pass
            except Exception as err:
                return Response({"error": str(err)}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class CinemaBookingList(generics.ListAPIView):
    """CinemaBookingList lists all cinema bookings."""

    serializer_class = CinemaBookingSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated & (IsUserOrMember | IsSuperAdmin)]
    pagination_class = PaginationStyle

    def get_queryset(self):
        user = self.request.user
        queryset = CinemaBooking.objects.filter(user=user)
        return queryset

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.serializer_class(page, many=True)
            return self.get_paginated_response(serializer.data)

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
                user_data = {
                    key: value.strip() if isinstance(value, str) else value
                    for key, value in request.data.items()
                }
                pin = user_data("pin")
                biometrics = request.data.get("use_biometrics")

                try:
                    account = AccountCreation.objects.get(user=authenticated_user)
                except AccountCreation.DoesNotExist:
                    return Response(
                        data={"status": "fail", "error": "Account not found for user"},
                        status=status.HTTP_404_NOT_FOUND,
                    )

                if biometrics:
                    verification = Biometrics.authenticate(
                        authenticated_user.phone_number
                    )
                else:
                    if account and account.pin is not None:
                        verification = Pin.verify(
                            user=authenticated_user, pin=pin, hashed_pin=account.pin
                        )
                    else:
                        return Response(
                            data={
                                "status": "fail",
                                "error": "Account or PIN not found for user",
                            },
                            status=status.HTTP_404_NOT_FOUND,
                        )

                if not verification:
                    return Response(
                        data={"status": "fail", "error": "Invalid credentials"},
                        status=status.HTTP_401_UNAUTHORIZED,
                    )

                # Inititate a debit on a users' account.
                amount = request.data.get("price_per_kg")
                payment_option = request.data.get("payment_option")
                user_detail = AccountCreation.objects.get(user=authenticated_user)
                match payment_option:
                    case "WALLET":
                        debit_response = Account.Debit(
                            debitAccount=user_detail.account_number,
                            amount=amount,
                            reason="Debit for booking courier service.",
                            transactionReference="",
                        )
                        if debit_response == 200:
                            UserNotification.objects.create(
                                user=authenticated_user,
                                title="Courier Service Booking.",
                                message=f"Payment of {amount} for courier service booking\
                                    was successful.",
                            )

                            ActivityModel.objects.create(
                                user=authenticated_user,
                                title="Courier Service Booking.",
                                description=f"{authenticated_user.first_name} {authenticated_user.last_name} made a payment of {amount} for courier Service booking.",
                            )

                            # send transactional email.
                            # TODO

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
                        pass
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

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.serializer_class(page, many=True)
            return self.get_paginated_response(serializer.data)

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
        payload = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in request.data.items()
        }
        serializer = self.get_serializer(data=payload)
        authenticated_user = request.user
        if serializer.is_valid(raise_exception=True):
            serializer.save()  # Save booking details.

            price = request.data.get("price")

            UserNotification.objects.create(
                user=authenticated_user,
                title="Consumables booking.",
                message=f"Booking of {price} for consumable service booking\
                    was successful.",
            )

            ActivityModel.objects.create(
                user=authenticated_user,
                title="Consumables booking.",
                description=f"{authenticated_user.first_name} {authenticated_user.last_name} booked for a consumable service of {price}.",
            )

            # send transactional email.
            # TODO

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
    pagination_class = PaginationStyle

    def get_queryset(self):
        user = self.request.user
        queryset = ConsumableService.objects.filter(user=user)
        return queryset

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.serializer_class(page, many=True)
            return self.get_paginated_response(serializer.data)

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
    BookLandTrip is a POST request route for booking a land trip, one way or round trip.
    """

    serializer_class = LandTravelsSerilaizers
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated & (IsUserOrMember | IsSuperAdmin)]

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid(raise_exception=True):
            try:
                authenticated_user = request.user
                payload = {
                    key: value.strip() if isinstance(value, str) else value
                    for key, value in request.data.items()
                }

                trip_date = payload["trip_date"]
                return_date = payload["return_date"]
                departure_state = payload["departure_state"]
                terminal = payload["terminal"]
                destination = payload["destination"]
                no_of_adults = payload["no_of_adults"]
                no_of_children = payload["no_of_children"]
                trip_type = payload["trip_type"]
                trip_pattern = payload["trip_pattern"]

                # Create the LandTravels object
                land_travel = LandTravels.objects.create(
                    user=authenticated_user,
                    departure_state=departure_state,
                    terminal=terminal,
                    trip_date=trip_date,
                    return_date=return_date,
                    destination=destination,
                    no_of_adults=no_of_adults,
                    no_of_children=no_of_children,
                    trip_type=trip_type,
                    trip_pattern=trip_pattern,
                )

                data = {
                    "trip_date": trip_date,
                    "return_date": return_date,
                    "departure_state": departure_state,
                    "terminal": terminal,
                    "destination": destination,
                    "no_of_adults": no_of_adults,
                    "no_of_children": no_of_children,
                    "trip_type": trip_type,
                    "trip_pattern": trip_pattern,
                }

                if trip_pattern == "One Way":
                    purchase = PurchaseModel.objects.create(
                        user=authenticated_user,
                        service_type="Land Travels Service.",
                        service_id=land_travel.id,
                        amount=0,
                    )
                    tx_status = TransactionStatus.objects.create(
                        status="Success",
                        details="One way trip booked successfully.",
                    )
                    tag = ProductTagmanager.generate(service_type="LTS-")
                    land_travel.purchase = purchase
                    land_travel.product_tag = tag
                    land_travel.transaction_status = tx_status
                    land_travel.save()

                    UserNotification.objects.create(
                        user=authenticated_user,
                        title="Land Travels Service.",
                        message=f"Booking of onw way trip from {departure_state} to {destination} was successful.",
                    )

                    ActivityModel.objects.create(
                        user=authenticated_user,
                        title="Consumables booking.",
                        description=f"{authenticated_user.first_name} {authenticated_user.last_name} made a onw way trip booking from {departure_state} to {destination}.",
                    )

                    response = {
                        "status": "success",
                        "message": f"You have successfully booked a one way trip from {departure_state} to {destination}.",
                        "data": {
                            "booking data": data,
                            "product_tag": tag,
                        },
                    }
                    return Response(data=response, status=status.HTTP_201_CREATED)

                elif trip_pattern == "Round Trip":
                    purchase = PurchaseModel.objects.create(
                        user=authenticated_user,
                        service_type="Land Travels Service.",
                        service_id=land_travel.id,
                        amount="",
                    )
                    tx_status = TransactionStatus.objects.create(
                        status="Success",
                        details="Round trip booked successfully.",
                    )
                    tag = ProductTagmanager.generate(service_type="LTS-")
                    land_travel.purchase = purchase
                    land_travel.product_tag = tag
                    land_travel.transaction_status = tx_status
                    land_travel.save()

                    UserNotification.objects.create(
                        user=authenticated_user,
                        title="Land Travels Service.",
                        message=f"Booking of round trip from {departure_state} to {destination} and back\
                            was successful.",
                    )

                    ActivityModel.objects.create(
                        user=authenticated_user,
                        title="Land Travels Service.",
                        description=f"{authenticated_user.first_name} {authenticated_user.last_name} made a round trip bbooking from {departure_state} to {destination} and back.",
                    )

                    response = {
                        "status": "success!",
                        "message": f"You have successfully booked a round trip from {departure_state} to {destination} and back.",
                        "data": {
                            "booking data": data,
                            "product_tag": tag,
                        },
                    }
                    return Response(data=response, status=status.HTTP_201_CREATED)

                else:
                    raise NotFound("Invalid selection")

            except Exception as err:
                return Response(
                    data={"error": str(err)}, status=status.HTTP_400_BAD_REQUEST
                )
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
    pagination_class = PaginationStyle

    def get_queryset(self):
        user = self.request.user
        queryset = LandTravels.objects.filter(user=user)
        return queryset

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.serializer_class(page, many=True)
            return self.get_paginated_response(serializer.data)

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
        serializer = HotelSerializers(data=request.data)
        if serializer.is_valid(raise_exception=True):
            try:
                authenticated_user = request.user
                user_data = {
                    key: value.strip() if isinstance(value, str) else value
                    for key, value in request.data.items()
                }
                pin = user_data("pin")
                biometrics = request.data.get("use_biometrics")

                try:
                    account = AccountCreation.objects.get(user=authenticated_user)
                except AccountCreation.DoesNotExist:
                    return Response(
                        data={"status": "fail", "error": "Account not found for user"},
                        status=status.HTTP_404_NOT_FOUND,
                    )

                if biometrics:
                    verification = Biometrics.authenticate(
                        authenticated_user.phone_number
                    )
                else:
                    if account and account.pin is not None:
                        verification = Pin.verify(
                            user=authenticated_user, pin=pin, hashed_pin=account.pin
                        )
                    else:
                        return Response(
                            data={
                                "status": "fail",
                                "error": "Account or PIN not found for user",
                            },
                            status=status.HTTP_404_NOT_FOUND,
                        )

                if not verification:
                    return Response(
                        data={"status": "fail", "error": "Invalid credentials"},
                        status=status.HTTP_401_UNAUTHORIZED,
                    )

                # Inititate a debit on a users' account.
                amount = request.data.get("amount")
                payment_option = request.data.get("payment_option")
                user_detail = AccountCreation.objects.get(user=authenticated_user)
                match payment_option:
                    case "WALLET":
                        debit_response = Account.Debit(
                            debitAccount=user_detail.account_number,
                            amount=amount,
                            reason="Debit for hotel booking.",
                            transactionReference="",
                        )
                        if debit_response == 200:
                            UserNotification.objects.create(
                                user=authenticated_user,
                                title="Hotel Booking.",
                                message=f"Payment of {amount} for hotel booking\
                                    was successful.",
                            )

                            ActivityModel.objects.create(
                                user=authenticated_user,
                                title="Hotel Booking.",
                                description=f"{authenticated_user.first_name} {authenticated_user.last_name} made a payment of {amount} for hotel booking.",
                            )

                            # send transactional email.
                            # TODO

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
                                "status": "fail",
                                "details": debit_response.json(),
                            }
                            return Response(
                                data=response_data,
                                status=status.HTTP_400_BAD_REQUEST,
                            )
                    case "CARD":
                        pass
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
    `review`: The review is a written appraisal of the product consumed.
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

                UserNotification.objects.create(
                    user=user,
                    title="Service Rating.",
                    message=f"Your service rating of {service} has been recorded.",
                )

                ActivityModel.objects.create(
                    user=user,
                    title="Service Rating.",
                    description=f"{user.first_name} {user.last_name} rated {service}.",
                )

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
