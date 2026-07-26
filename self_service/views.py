import logging

from permissions import IsSuperAdmin, IsMemberOrPartner

# Third party imports
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.exceptions import NotFound
from rest_framework.pagination import PageNumberPagination

import rest_framework.serializers as s
from drf_spectacular.utils import extend_schema, inline_serializer


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
from accounts.models import UserNotification, PurchaseModel, TxModel
from partners.commission_service import PartnerCommissionService
from banking.helpers import Pin
from banking.controllers import Wallet
from banking.models import WalletModel
from commons import Biometrics, Pay
from roles.models import ActivityModel
from security import encrypt, decrypt

logger = logging.getLogger(__name__)

SERVICES = (
    ("restaurant", "restaurant"),
    ("gym", "gym"),
    ("cinema", "cinema"),
    ("courier", "courier"),
    ("consumable", "consumable"),
    ("land_travel", "land_travel"),
    ("hotel", "hotel"),
)


def partner_booking_rejection(user, partner_service):
    """
    Partner accounts may only book self-service items tied to another
    partner's PartnerServices listing (the Partner Ecosystem) - a Partner
    booking a non-partner-linked item doesn't fit that model. Returns an
    error Response if the booking should be rejected, else None.
    """
    if user.active_role == "Partner" and not partner_service:
        return Response(
            data=encrypt(
                {
                    "status": "fail",
                    "error": "Partners can only book services listed by another partner.",
                }
            ),
            status=status.HTTP_403_FORBIDDEN,
        )
    return None


class PaginationStyle(PageNumberPagination):
    page_size = 10


@extend_schema(
    summary="Book a restaurant table",
    tags=["Self-Service"],
    description="Creates a restaurant table booking for the authenticated user and processes payment via wallet or card. Requires wallet PIN or biometric verification.",
    request=RestaurantBookingSerializers,
    responses={
        200: inline_serializer(
            "TableBookingResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "data": s.DictField(),
            },
        ),
        400: inline_serializer(
            "TableBookingError",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        401: inline_serializer(
            "TableBookingUnauthorized",
            fields={"status": s.CharField(), "error": s.CharField()},
        ),
        404: inline_serializer(
            "TableBookingNotFound",
            fields={"status": s.CharField(), "error": s.CharField()},
        ),
    },
)
class TableBooking(generics.CreateAPIView):
    serializer_class = RestaurantBookingSerializers
    permission_classes = [IsAuthenticated & (IsMemberOrPartner | IsSuperAdmin)]

    def create(self, request, *args, **kwargs):
        serializer = RestaurantBookingSerializers(data=request.data)
        if serializer.is_valid(raise_exception=True):
            rejection = partner_booking_rejection(
                request.user, serializer.validated_data.get("partner_service")
            )
            if rejection:
                return rejection
            try:
                authenticated_user = request.user
                decrypted_payload = decrypt(request.user)
                user_data = {
                    key: value.strip() if isinstance(value, str) else value
                    for key, value in decrypted_payload.items()
                }
                pin = user_data("pin")
                biometrics = user_data.get("use_biometrics")
                use_points = user_data.get("use_points")

                try:
                    account = WalletModel.objects.get(
                        user=authenticated_user, walletType="INDIVIDUAL"
                    )
                except WalletModel.DoesNotExist:
                    return Response(
                        data=encrypt(
                            {"status": "fail", "error": "Wallet not found for user"}
                        ),
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
                            data=encrypt(
                                {
                                    "status": "fail",
                                    "error": "Account or PIN not found for user",
                                }
                            ),
                            status=status.HTTP_404_NOT_FOUND,
                        )

                if not verification:
                    return Response(
                        data=encrypt(
                            {"status": "fail", "error": "Invalid credentials"}
                        ),
                        status=status.HTTP_401_UNAUTHORIZED,
                    )

                # Inititate a debit on a users' account.
                amount = user_data.get("amount")
                payment_option = user_data("payment_option")
                match payment_option:
                    case "WALLET":
                        amount = int(amount)
                        pts_amt = 0

                        if use_points:
                            _, pts_amt = Pay.with_pts(
                                user=authenticated_user, amount=amount
                            )

                        # Determine wallet debit amount
                        if use_points and pts_amt >= amount:
                            wallet_debit_amount = 0
                        elif use_points and pts_amt < amount:
                            wallet_debit_amount = amount - pts_amt
                        else:
                            wallet_debit_amount = amount

                        if wallet_debit_amount > 0:
                            debit_response = Wallet.Debit(
                                debitAccount=account.account_number,
                                amount=amount,
                                reason="Debit restaurant table booking",
                                transactionReference="",
                            )

                            if debit_response.status_code == 200:
                                UserNotification.objects.create(
                                    user=authenticated_user,
                                    title="Table Booking.",
                                    message=f"Payment of {amount} for restaurant table booking\
                                        was successful.",
                                )

                                ActivityModel.objects.create(
                                    user=authenticated_user,
                                    title="Table Booking.",
                                    description=f"{authenticated_user.first_name} {authenticated_user.last_name} made a payment of {amount} for restaurant table booking.",
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
                                tx = TxModel.objects.create(
                                    user=authenticated_user,
                                    tx_type="Food",
                                    amount=amount,
                                    status="SUCCESS",
                                    description="Restaurant booking paid successfully.",
                                )
                                tag = ProductTagmanager.generate(service_type="RST-")
                                current_user = RestaurantBooking.objects.get(
                                    user=authenticated_user
                                )
                                current_user.purchase = purchase
                                current_user.product_tag = tag
                                current_user.transaction_status = tx_status
                                current_user.tx = tx
                                current_user.save()
                                PartnerCommissionService.record_purchase(
                                    user=authenticated_user,
                                    partner_service=current_user.partner_service,
                                    tx=tx,
                                    amount=amount,
                                )

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
                                    data=encrypt(response_data),
                                    status=status.HTTP_200_OK,
                                )
                            else:
                                tx_status = TransactionStatus.objects.create(
                                    status="Fail",
                                    details="Restaurant booking failed.",
                                )
                                TxModel.objects.create(
                                    user=authenticated_user,
                                    tx_type="Food",
                                    amount=amount,
                                    status="FAILED",
                                    description="Restaurant booking failed.",
                                )
                                response_data = {
                                    "status": "fail!",
                                    "details": debit_response.json(),
                                }
                                return Response(
                                    data=encrypt(response_data),
                                    status=status.HTTP_200_OK,
                                )

                    case "CARD":
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
                        tx = TxModel.objects.create(
                            user=authenticated_user,
                            tx_type="Food",
                            amount=amount,
                            status="SUCCESS",
                            description="Restaurant booking paid successfully.",
                        )
                        tag = ProductTagmanager.generate(service_type="RST-")
                        current_user = RestaurantBooking.objects.get(
                            user=authenticated_user
                        )
                        current_user.purchase = purchase
                        current_user.product_tag = tag
                        current_user.transaction_status = tx_status
                        current_user.tx = tx
                        current_user.save()
                        PartnerCommissionService.record_purchase(
                            user=authenticated_user,
                            partner_service=current_user.partner_service,
                            tx=tx,
                            amount=amount,
                        )

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
                            data=encrypt(response_data), status=status.HTTP_200_OK
                        )
            except Exception as err:
                logger.error("Self-service booking failed: %s", str(err), exc_info=True)
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "message": "Booking failed. Please try again.",
                        }
                    ),
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
        else:
            return Response(
                data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST
            )


@extend_schema(
    summary="List all restaurant bookings for the user",
    tags=["Self-Service"],
    description="Returns a paginated list of all restaurant table bookings made by the currently authenticated user.",
    responses={
        200: inline_serializer(
            "TableBookingListResponse",
            fields={
                "count": s.IntegerField(),
                "next": s.CharField(allow_null=True),
                "previous": s.CharField(allow_null=True),
                "results": s.ListField(),
            },
        ),
    },
)
class TableBookingList(generics.ListAPIView):
    """TableBookingList lists all restaurant bookings."""

    serializer_class = RestaurantBookingSerializers
    permission_classes = [IsAuthenticated & (IsMemberOrPartner | IsSuperAdmin)]
    pagination_class = PaginationStyle

    def get_queryset(self):
        user = self.request.user
        queryset = RestaurantBooking.objects.filter(user=user)
        return queryset

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()

        # Handle pagination manually so we can encrypt the whole response
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)

            paginated_data = {
                "count": self.paginator.page.paginator.count,
                "next": self.paginator.get_next_link(),
                "previous": self.paginator.get_previous_link(),
                "results": serializer.data,
            }

            encrypted = encrypt(paginated_data)
            return Response(data=encrypted, status=status.HTTP_200_OK)

        # Non-paginated response (rare case)
        serializer = self.get_serializer(queryset, many=True)
        encrypted = encrypt(serializer.data)
        return Response(data=encrypted, status=status.HTTP_200_OK)


@extend_schema(
    summary="Get details of a specific restaurant booking",
    tags=["Self-Service"],
    description="Retrieves a single restaurant table booking by ID. Returns 404 if the booking doesn't exist or doesn't belong to the authenticated user.",
    responses={
        200: RestaurantBookingSerializers,
        404: inline_serializer(
            "TableBookingDetailNotFound", fields={"error": s.CharField()}
        ),
    },
)
class TableBookingDetail(generics.RetrieveAPIView):
    """
    TableBookingDetail retrieves a specific restaurant table booking for the authenticated user.
    """

    serializer_class = RestaurantBookingSerializers
    permission_classes = [IsAuthenticated & (IsMemberOrPartner | IsSuperAdmin)]

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
        return Response(data=encrypt(serializer.data), status=status.HTTP_200_OK)


@extend_schema(
    summary="Book a gym subscription",
    tags=["Self-Service"],
    description="Creates a gym subscription booking for the authenticated user and processes payment via wallet or card. Requires wallet PIN or biometric verification.",
    request=GymSubcriptionSerializers,
    responses={
        200: inline_serializer(
            "GymBookingResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "data": s.DictField(),
            },
        ),
        400: inline_serializer(
            "GymBookingError",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        401: inline_serializer(
            "GymBookingUnauthorized",
            fields={"status": s.CharField(), "error": s.CharField()},
        ),
        404: inline_serializer(
            "GymBookingNotFound",
            fields={"status": s.CharField(), "error": s.CharField()},
        ),
    },
)
class GymBooking(generics.CreateAPIView):
    serializer_class = GymSubcriptionSerializers
    permission_classes = [IsAuthenticated & (IsMemberOrPartner | IsSuperAdmin)]

    def create(self, request, *args, **kwargs):
        serializer = GymSubcriptionSerializers(data=request.data)
        if serializer.is_valid(raise_exception=True):
            rejection = partner_booking_rejection(
                request.user, serializer.validated_data.get("partner_service")
            )
            if rejection:
                return rejection
            try:
                authenticated_user = request.user
                decrypted_payload = decrypt(request.data)
                user_data = {
                    key: value.strip() if isinstance(value, str) else value
                    for key, value in decrypted_payload.items()
                }
                pin = user_data.get("pin")
                biometrics = user_data.get("use_biometrics")
                use_points = user_data.get("use_points")

                try:
                    account = Wallet.objects.get(user=authenticated_user)
                except WalletModel.DoesNotExist:
                    return Response(
                        data=encrypt(
                            {"status": "fail", "error": "Account not found for user"}
                        ),
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
                            data=encrypt(
                                {
                                    "status": "fail",
                                    "error": "Account or PIN not found for user",
                                }
                            ),
                            status=status.HTTP_404_NOT_FOUND,
                        )

                if not verification:
                    return Response(
                        data=encrypt(
                            {"status": "fail", "error": "Invalid credentials"}
                        ),
                        status=status.HTTP_401_UNAUTHORIZED,
                    )

                # Inititate a debit on users' account.
                amount = user_data.get("amount")
                payment_option = user_data("payment_option")
                match payment_option:
                    case "WALLET":
                        amount = int(amount)
                        pts_amt = 0

                        if use_points:
                            _, pts_amt = Pay.with_pts(
                                user=authenticated_user, amount=amount
                            )

                        # Determine wallet debit amount
                        if use_points and pts_amt >= amount:
                            wallet_debit_amount = 0
                        elif use_points and pts_amt < amount:
                            wallet_debit_amount = amount - pts_amt
                        else:
                            wallet_debit_amount = amount

                        if wallet_debit_amount > 0:
                            debit_response = Wallet.Debit(
                                debitAccount=account.account_number,
                                amount=amount,
                                reason="Debit for gym subscription.",
                                transactionReference="",
                            )
                            if debit_response.status_code == 200:
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
                                tx = TxModel.objects.create(
                                    user=authenticated_user,
                                    tx_type="Gym",
                                    amount=amount,
                                    status="SUCCESS",
                                    description="Gym Subscription paid successfully.",
                                )
                                tag = ProductTagmanager.generate(service_type="GYM-")
                                current_user = GymSubcription.objects.get(
                                    user=authenticated_user
                                )
                                current_user.purchase = purchase
                                current_user.product_tag = tag
                                current_user.transaction_status = tx_status
                                current_user.tx = tx
                                current_user.save()
                                PartnerCommissionService.record_purchase(
                                    user=authenticated_user,
                                    partner_service=current_user.partner_service,
                                    tx=tx,
                                    amount=amount,
                                )

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
                                    data=encrypt(response_data),
                                    status=status.HTTP_200_OK,
                                )
                            else:
                                TxModel.objects.create(
                                    user=authenticated_user,
                                    tx_type="Gym",
                                    amount=amount,
                                    status="FAILED",
                                    description="Gym Subscription failed.",
                                )
                                response_data = {
                                    "status": "fail!",
                                    "details": debit_response.json(),
                                }
                                return Response(
                                    data=encrypt(response_data),
                                    status=status.HTTP_200_OK,
                                )

                    case "CARD":
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
                        tx = TxModel.objects.create(
                            user=authenticated_user,
                            tx_type="Gym",
                            amount=amount,
                            status="SUCCESS",
                            description="Gym Subscription paid successfully.",
                        )
                        tag = ProductTagmanager.generate(service_type="GYM-")
                        current_user = GymSubcription.objects.get(
                            user=authenticated_user
                        )
                        current_user.purchase = purchase
                        current_user.product_tag = tag
                        current_user.transaction_status = tx_status
                        current_user.tx = tx
                        current_user.save()
                        PartnerCommissionService.record_purchase(
                            user=authenticated_user,
                            partner_service=current_user.partner_service,
                            tx=tx,
                            amount=amount,
                        )

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
                            data=encrypt(response_data), status=status.HTTP_200_OK
                        )
            except Exception as err:
                logger.error("Self-service booking failed: %s", str(err), exc_info=True)
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "message": "Booking failed. Please try again.",
                        }
                    ),
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
        else:
            return Response(
                data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST
            )


@extend_schema(
    summary="List all gym bookings for the user",
    tags=["Self-Service"],
    description="Returns a paginated list of all gym subscription bookings made by the currently authenticated user.",
    responses={
        200: inline_serializer(
            "GymBookingListResponse",
            fields={
                "count": s.IntegerField(),
                "next": s.CharField(allow_null=True),
                "previous": s.CharField(allow_null=True),
                "results": s.ListField(),
            },
        ),
    },
)
class GymBookingList(generics.ListAPIView):
    """GymBookingList lists all gym bookings."""

    serializer_class = GymSubcriptionSerializers
    permission_classes = [IsAuthenticated & (IsMemberOrPartner | IsSuperAdmin)]
    pagination_class = PaginationStyle

    def get_queryset(self):
        user = self.request.user
        queryset = GymSubcription.objects.filter(user=user)
        return queryset

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()

        # Handle pagination manually so we can encrypt the whole response
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)

            paginated_data = {
                "count": self.paginator.page.paginator.count,
                "next": self.paginator.get_next_link(),
                "previous": self.paginator.get_previous_link(),
                "results": serializer.data,
            }

            encrypted = encrypt(paginated_data)
            return Response(data=encrypted, status=status.HTTP_200_OK)

        # Non-paginated response (rare case)
        serializer = self.get_serializer(queryset, many=True)
        encrypted = encrypt(serializer.data)
        return Response(data=encrypted, status=status.HTTP_200_OK)


@extend_schema(
    summary="Get details of a specific gym booking",
    tags=["Self-Service"],
    description="Retrieves a single gym subscription booking by ID. Returns 404 if the booking doesn't exist or doesn't belong to the authenticated user.",
    responses={
        200: GymSubcriptionSerializers,
        404: inline_serializer(
            "GymBookingDetailNotFound", fields={"error": s.CharField()}
        ),
    },
)
class GymBookingDetail(generics.RetrieveAPIView):
    """
    GymBookingDetail retrieves a specific cinema booking for the authenticated user.
    """

    serializer_class = GymSubcriptionSerializers
    permission_classes = [IsAuthenticated & (IsMemberOrPartner | IsSuperAdmin)]

    def get_object(self):
        booking_id = self.kwargs.get("id")
        user = self.request.user

        try:
            # Check if booking exists and belongs to the user
            booking = GymSubcription.objects.get(pk=booking_id, user=user)
        except GymSubcription.DoesNotExist:
            return Response(
                data=encrypt({"error": "Booking not found or does not belong to you."}),
                status=status.HTTP_404_NOT_FOUND,
            )

        return booking

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(data=encrypt(serializer.data), status=status.HTTP_200_OK)


@extend_schema(
    summary="Book cinema seats",
    tags=["Self-Service"],
    description="Creates a cinema seat booking for the authenticated user and processes payment via wallet or card. Requires wallet PIN or biometric verification.",
    request=CinemaBookingSerializers,
    responses={
        200: inline_serializer(
            "CinemaBookingResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "data": s.DictField(),
            },
        ),
        400: inline_serializer(
            "CinemaBookingError",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        401: inline_serializer(
            "CinemaBookingUnauthorized",
            fields={"status": s.CharField(), "error": s.CharField()},
        ),
        404: inline_serializer(
            "CinemaBookingNotFound",
            fields={"status": s.CharField(), "error": s.CharField()},
        ),
    },
)
class CinemaBookingView(generics.CreateAPIView):
    serializer_class = CinemaBookingSerializers
    permission_classes = [IsAuthenticated & (IsMemberOrPartner | IsSuperAdmin)]

    def create(self, request, *args, **kwargs):
        decrypted_payload = decrypt(request.data)
        serializer = CinemaBookingSerializers(data=decrypted_payload)
        if serializer.is_valid(raise_exception=True):
            rejection = partner_booking_rejection(
                request.user, serializer.validated_data.get("partner_service")
            )
            if rejection:
                return rejection
            try:
                authenticated_user = request.user
                user_data = {
                    key: value.strip() if isinstance(value, str) else value
                    for key, value in decrypted_payload.items()
                }
                pin = user_data("pin")
                biometrics = user_data.get("use_biometrics")
                use_points = user_data.get("use_points")

                try:
                    account = WalletModel.objects.get(
                        user=authenticated_user, walletType="INDIVIDUAL"
                    )
                except WalletModel.DoesNotExist:
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
                            data=encrypt(
                                {
                                    "status": "fail",
                                    "error": "Account or PIN not found for user",
                                }
                            ),
                            status=status.HTTP_404_NOT_FOUND,
                        )

                if not verification:
                    return Response(
                        data=encrypt(
                            {"status": "fail", "error": "Invalid credentials"}
                        ),
                        status=status.HTTP_401_UNAUTHORIZED,
                    )

                # Inititate a debit on a users' account.
                amount = user_data.get("amount")
                payment_option = user_data("payment_option")
                match payment_option:
                    case "WALLET":
                        amount = int(amount)
                        pts_amt = 0

                        if use_points:
                            _, pts_amt = Pay.with_pts(
                                user=authenticated_user, amount=amount
                            )

                        # Determine wallet debit amount
                        if use_points and pts_amt >= amount:
                            wallet_debit_amount = 0
                        elif use_points and pts_amt < amount:
                            wallet_debit_amount = amount - pts_amt
                        else:
                            wallet_debit_amount = amount

                        if wallet_debit_amount > 0:
                            debit_response = Wallet.Debit(
                                debitAccount=account.account_number,
                                amount=amount,
                                reason="Debit for cinema seats booking.",
                                transactionReference="",
                            )
                            if debit_response.status_code == 200:
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
                                tx = TxModel.objects.create(
                                    user=authenticated_user,
                                    tx_type="Cinema",
                                    amount=amount,
                                    status="SUCCESS",
                                    description="Cinema seats paid successfully.",
                                )
                                tag = ProductTagmanager.generate(service_type="CIN-")
                                current_user = CinemaBooking.objects.get(
                                    user=authenticated_user
                                )
                                current_user.purchase = purchase
                                current_user.product_tag = tag
                                current_user.transaction_status = tx_status
                                current_user.tx = tx
                                current_user.save()
                                PartnerCommissionService.record_purchase(
                                    user=authenticated_user,
                                    partner_service=current_user.partner_service,
                                    tx=tx,
                                    amount=amount,
                                )

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
                                    data=encrypt(response_data),
                                    status=status.HTTP_200_OK,
                                )
                            else:
                                TxModel.objects.create(
                                    user=authenticated_user,
                                    tx_type="Cinema",
                                    amount=amount,
                                    status="FAILED",
                                    description="Cinema seats booking failed.",
                                )
                                response_data = {
                                    "status": "fail!",
                                    "details": debit_response.json(),
                                }
                                return Response(
                                    data=encrypt(response_data),
                                    status=status.HTTP_200_OK,
                                )

                    case "CARD":
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
                        tx = TxModel.objects.create(
                            user=authenticated_user,
                            tx_type="Cinema",
                            amount=amount,
                            status="SUCCESS",
                            description="Cinema seats paid successfully.",
                        )
                        tag = ProductTagmanager.generate(service_type="CIN-")
                        current_user = CinemaBooking.objects.get(
                            user=authenticated_user
                        )
                        current_user.purchase = purchase
                        current_user.product_tag = tag
                        current_user.transaction_status = tx_status
                        current_user.tx = tx
                        current_user.save()
                        PartnerCommissionService.record_purchase(
                            user=authenticated_user,
                            partner_service=current_user.partner_service,
                            tx=tx,
                            amount=amount,
                        )

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
                            data=encrypt(response_data), status=status.HTTP_200_OK
                        )
            except Exception as err:
                logger.error("Self-service booking failed: %s", str(err), exc_info=True)
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "message": "Booking failed. Please try again.",
                        }
                    ),
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
        else:
            return Response(
                data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST
            )


@extend_schema(
    summary="List all cinema bookings for the user",
    tags=["Self-Service"],
    description="Returns a paginated list of all cinema seat bookings made by the currently authenticated user.",
    responses={
        200: inline_serializer(
            "CinemaBookingListResponse",
            fields={
                "count": s.IntegerField(),
                "next": s.CharField(allow_null=True),
                "previous": s.CharField(allow_null=True),
                "results": s.ListField(),
            },
        ),
    },
)
class CinemaBookingList(generics.ListAPIView):
    """CinemaBookingList lists all cinema bookings."""

    serializer_class = CinemaBookingSerializers
    permission_classes = [IsAuthenticated, IsMemberOrPartner | IsSuperAdmin]
    pagination_class = PaginationStyle

    def get_queryset(self):
        return CinemaBooking.objects.filter(user=self.request.user).order_by(
            "-id"
        )  # Fix warning & ensure stable pagination

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()

        # Handle pagination manually so we can encrypt the whole response
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)

            paginated_data = {
                "count": self.paginator.page.paginator.count,
                "next": self.paginator.get_next_link(),
                "previous": self.paginator.get_previous_link(),
                "results": serializer.data,
            }

            encrypted = encrypt(paginated_data)
            return Response(data=encrypted, status=status.HTTP_200_OK)

        # Non-paginated response (rare case)
        serializer = self.get_serializer(queryset, many=True)
        encrypted = encrypt(serializer.data)
        return Response(data=encrypted, status=status.HTTP_200_OK)


@extend_schema(
    summary="Get details of a specific cinema booking",
    tags=["Self-Service"],
    description="Retrieves a single cinema seat booking by ID. Returns 404 if the booking doesn't exist or doesn't belong to the authenticated user.",
    responses={
        200: CinemaBookingSerializers,
        404: inline_serializer(
            "CinemaBookingDetailNotFound", fields={"error": s.CharField()}
        ),
    },
)
class CinemaBookingDetail(generics.RetrieveAPIView):
    """
    CinemaBookingDetail retrieves a specific cinema booking for the authenticated user.
    """

    serializer_class = CinemaBookingSerializers
    permission_classes = [IsAuthenticated & (IsMemberOrPartner | IsSuperAdmin)]

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
        return Response(data=encrypt(serializer.data), status=status.HTTP_200_OK)


@extend_schema(
    summary="Book a courier service",
    tags=["Self-Service"],
    description="Creates a courier service booking for the authenticated user and processes payment via wallet or card. Requires wallet PIN or biometric verification.",
    request=CourierBookingSerializers,
    responses={
        200: inline_serializer(
            "BookCourierResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "data": s.DictField(),
            },
        ),
        400: inline_serializer(
            "BookCourierError",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        401: inline_serializer(
            "BookCourierUnauthorized",
            fields={"status": s.CharField(), "error": s.CharField()},
        ),
        404: inline_serializer(
            "BookCourierNotFound",
            fields={"status": s.CharField(), "error": s.CharField()},
        ),
    },
)
class BookCourierSercvice(generics.CreateAPIView):
    serializer_class = CourierBookingSerializers
    permission_classes = [IsAuthenticated & (IsMemberOrPartner | IsSuperAdmin)]

    def create(self, request, *args, **kwargs):
        serializer = CourierBookingSerializers(data=request.data)
        if serializer.is_valid(raise_exception=True):
            rejection = partner_booking_rejection(
                request.user, serializer.validated_data.get("partner_service")
            )
            if rejection:
                return rejection
            try:
                authenticated_user = request.user
                dedicated_payload = decrypt(request.data)
                user_data = {
                    key: value.strip() if isinstance(value, str) else value
                    for key, value in dedicated_payload.items()
                }
                pin = user_data("pin")
                biometrics = user_data.get("use_biometrics")
                use_points = user_data.get("use_points")

                try:
                    account = WalletModel.objects.get(
                        user=authenticated_user, walletType="INDIVIDUAL"
                    )
                except WalletModel.DoesNotExist:
                    return Response(
                        data=encrypt(
                            {"status": "fail", "error": "Account not found for user"}
                        ),
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
                            data=encrypt(
                                {
                                    "status": "fail",
                                    "error": "Account or PIN not found for user",
                                }
                            ),
                            status=status.HTTP_404_NOT_FOUND,
                        )

                if not verification:
                    return Response(
                        data=encrypt(
                            {"status": "fail", "error": "Invalid credentials"}
                        ),
                        status=status.HTTP_401_UNAUTHORIZED,
                    )

                # Inititate a debit on a users' account.
                amount = user_data.get("price_per_kg")
                payment_option = user_data.get("payment_option")

                match payment_option:
                    case "WALLET":
                        amount = int(amount)
                        pts_amt = 0

                        if use_points:
                            _, pts_amt = Pay.with_pts(
                                user=authenticated_user, amount=amount
                            )

                        # Determine wallet debit amount
                        if use_points and pts_amt >= amount:
                            wallet_debit_amount = 0
                        elif use_points and pts_amt < amount:
                            wallet_debit_amount = amount - pts_amt
                        else:
                            wallet_debit_amount = amount

                        if wallet_debit_amount > 0:
                            debit_response = Wallet.Debit(
                                debitAccount=account.account_number,
                                amount=amount,
                                reason="Debit for booking courier service.",
                                transactionReference="",
                            )
                            if debit_response.status_code == 200:
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

                                serializer.save()
                                purchase = PurchaseModel.objects.create(
                                    user=authenticated_user,
                                    service_type="Courier Service.",
                                    service_id=serializer.data["id"],
                                    amount=amount,
                                )
                                tx_status = TransactionStatus.objects.create(
                                    status="Success",
                                    details="Courier service booked successfully.",
                                )
                                tx = TxModel.objects.create(
                                    user=authenticated_user,
                                    tx_type="Courier",
                                    amount=amount,
                                    status="SUCCESS",
                                    description="Courier service booked successfully.",
                                )
                                tag = ProductTagmanager.generate(service_type="COU-")
                                current_user = CourierService.objects.get(
                                    user=authenticated_user
                                )
                                current_user.purchase = purchase
                                current_user.product_tag = tag
                                current_user.transaction_status = tx_status
                                current_user.tx = tx
                                current_user.save()
                                PartnerCommissionService.record_purchase(
                                    user=authenticated_user,
                                    partner_service=current_user.partner_service,
                                    tx=tx,
                                    amount=amount,
                                )

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
                                    data=encrypt(response_data),
                                    status=status.HTTP_200_OK,
                                )
                            else:
                                TxModel.objects.create(
                                    user=authenticated_user,
                                    tx_type="Courier",
                                    amount=amount,
                                    status="FAILED",
                                    description="Courier service booking failed.",
                                )
                                response_data = {
                                    "status": "fail!",
                                    "details": debit_response.json(),
                                }
                                return Response(
                                    data=encrypt(response_data),
                                    status=status.HTTP_200_OK,
                                )

                    case "CARD":
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

                        serializer.save()
                        purchase = PurchaseModel.objects.create(
                            user=authenticated_user,
                            service_type="Courier Service.",
                            service_id=serializer.data["id"],
                            amount=amount,
                        )
                        tx_status = TransactionStatus.objects.create(
                            status="Success",
                            details="Courier service booked successfully.",
                        )
                        tx = TxModel.objects.create(
                            user=authenticated_user,
                            tx_type="Courier",
                            amount=amount,
                            status="SUCCESS",
                            description="Courier service booked successfully.",
                        )
                        tag = ProductTagmanager.generate(service_type="COU-")
                        current_user = CourierService.objects.get(
                            user=authenticated_user
                        )
                        current_user.purchase = purchase
                        current_user.product_tag = tag
                        current_user.transaction_status = tx_status
                        current_user.tx = tx
                        current_user.save()
                        PartnerCommissionService.record_purchase(
                            user=authenticated_user,
                            partner_service=current_user.partner_service,
                            tx=tx,
                            amount=amount,
                        )

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
                            data=encrypt(response_data), status=status.HTTP_200_OK
                        )
            except Exception as err:
                logger.error("Self-service booking failed: %s", str(err), exc_info=True)
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "message": "Booking failed. Please try again.",
                        }
                    ),
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
        else:
            return Response(
                data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST
            )


@extend_schema(
    summary="List all courier bookings for the user",
    tags=["Self-Service"],
    description="Returns a paginated list of all courier service bookings made by the currently authenticated user.",
    responses={
        200: inline_serializer(
            "CourierBookingListResponse",
            fields={
                "count": s.IntegerField(),
                "next": s.CharField(allow_null=True),
                "previous": s.CharField(allow_null=True),
                "results": s.ListField(),
            },
        ),
    },
)
class CourierBookingList(generics.ListAPIView):
    """CourierBookingList lists all courier bookings."""

    serializer_class = CourierBookingSerializers
    permission_classes = [IsAuthenticated & (IsMemberOrPartner | IsSuperAdmin)]
    pagination_class = PaginationStyle

    def get_queryset(self):
        return CourierService.objects.filter(user=self.request.user).order_by("-id")

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()

        # Handle pagination manually so we can encrypt the whole response
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)

            paginated_data = {
                "count": self.paginator.page.paginator.count,
                "next": self.paginator.get_next_link(),
                "previous": self.paginator.get_previous_link(),
                "results": serializer.data,
            }

            encrypted = encrypt(paginated_data)
            return Response(data=encrypted, status=status.HTTP_200_OK)

        # Non-paginated response (rare case)
        serializer = self.get_serializer(queryset, many=True)
        encrypted = encrypt(serializer.data)
        return Response(data=encrypted, status=status.HTTP_200_OK)


@extend_schema(
    summary="Get details of a specific courier booking",
    tags=["Self-Service"],
    description="Retrieves a single courier service booking by ID. Returns 404 if the booking doesn't exist or doesn't belong to the authenticated user.",
    responses={
        200: CourierBookingSerializers,
        404: inline_serializer(
            "CourierBookingDetailNotFound", fields={"error": s.CharField()}
        ),
    },
)
class CourierBookingDetail(generics.RetrieveAPIView):
    """
    CourierBookingDetail retrieves a specific courier booking for
    the authenticated user.
    """

    serializer_class = CourierBookingSerializers
    permission_classes = [IsAuthenticated & (IsMemberOrPartner | IsSuperAdmin)]

    def get_object(self):
        booking_id = self.kwargs.get("id")
        user = self.request.user

        try:
            # Check if booking exists and belongs to the user
            booking = CourierService.objects.get(pk=booking_id, user=user)
        except CourierService.DoesNotExist:
            return Response(
                data=encrypt({"error": "Booking not found or does not belong to you."}),
                status=status.HTTP_404_NOT_FOUND,
            )

        return booking

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(data=encrypt(serializer.data), status=status.HTTP_200_OK)


@extend_schema(
    summary="Book a consumable service",
    tags=["Self-Service"],
    description="Creates a consumable (FMCG) service booking for the authenticated user and processes payment via wallet or card. Requires wallet PIN or biometric verification.",
    request=ConsumableSerializers,
    responses={
        201: inline_serializer(
            "BookConsumableResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "data": s.DictField(),
            },
        ),
        400: inline_serializer(
            "BookConsumableError",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        401: inline_serializer(
            "BookConsumableUnauthorized",
            fields={"status": s.CharField(), "error": s.CharField()},
        ),
        404: inline_serializer(
            "BookConsumableNotFound",
            fields={"status": s.CharField(), "error": s.CharField()},
        ),
    },
)
class BookConsumableSercvice(generics.CreateAPIView):
    serializer_class = CourierBookingSerializers
    permission_classes = [IsAuthenticated & (IsMemberOrPartner | IsSuperAdmin)]
    queryset = ConsumableService.objects.all()

    def create(self, request, *args, **kwargs):
        decrypted_payload = decrypt(request.data)
        payload = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_payload.items()
        }
        serializer = self.get_serializer(data=payload)
        authenticated_user = request.user
        if not serializer.is_valid(raise_exception=True):
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        rejection = partner_booking_rejection(
            authenticated_user, serializer.validated_data.get("partner_service")
        )
        if rejection:
            return rejection
        serializer.save()  # Save booking details.

        authenticated_user = request.user
        pin = payload.get("pin")
        biometrics = payload.get("use_biometrics")

        try:
            account = WalletModel.objects.get(user=authenticated_user)
        except WalletModel.DoesNotExist:
            return Response(
                data=encrypt({"status": "fail", "error": "Account not found for user"}),
                status=status.HTTP_404_NOT_FOUND,
            )

        if biometrics:
            verification = Biometrics.authenticate(authenticated_user.phone_number)
        else:
            if account and account.pin is not None:
                verification = Pin.verify(
                    user=authenticated_user, pin=pin, hashed_pin=account.pin
                )
            else:
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "error": "Account or PIN not found for user",
                        }
                    ),
                    status=status.HTTP_404_NOT_FOUND,
                )

        if not verification:
            return Response(
                data=encrypt({"status": "fail", "error": "Invalid credentials"}),
                status=status.HTTP_401_UNAUTHORIZED,
            )

        price = payload.get("price")
        payment_option = payload.get("payment_option")
        user_details = WalletModel.objects.get(user=authenticated_user)
        match payment_option:
            case "WALLET":
                debit_response = Wallet.Debit(
                    debitAccount=user_details.account_number,
                    amount=price,
                    reason="Debit for booking courier service.",
                    transactionReference="",
                )
                if debit_response.status_code == 200:
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
                    tx = TxModel.objects.create(
                        user=authenticated_user,
                        tx_type="Consumables",
                        amount=price,
                        status="SUCCESS",
                        description="Consumable service booked successfully.",
                    )
                    tag = ProductTagmanager.generate(service_type="FMCG-")
                    current_user = ConsumableService.objects.get(user=request.user)
                    current_user.purchase = purchase
                    current_user.product_tag = tag
                    current_user.transaction_status = tx_status
                    current_user.tx = tx
                    current_user.save()
                    PartnerCommissionService.record_purchase(
                        user=request.user,
                        partner_service=current_user.partner_service,
                        tx=tx,
                        amount=price,
                    )

                    response_data = {
                        "status": "success",
                        "message": "Service booked successfully!",
                        "data": {
                            "booking data": serializer.data,
                            "product_tag": tag,
                        },
                    }
                    return Response(data=response_data, status=status.HTTP_201_CREATED)
                else:
                    TxModel.objects.create(
                        user=authenticated_user,
                        tx_type="Consumables",
                        amount=price,
                        status="FAILED",
                        description="Consumable service booking failed.",
                    )
                    response_data = {
                        "status": "fail!",
                        "details": debit_response.json(),
                    }
                    return Response(data=response_data, status=status.HTTP_200_OK)
            case "CARD":
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
                tx = TxModel.objects.create(
                    user=authenticated_user,
                    tx_type="Consumables",
                    amount=price,
                    status="SUCCESS",
                    description="Consumable service booked successfully.",
                )
                tag = ProductTagmanager.generate(service_type="FMCG-")
                current_user = ConsumableService.objects.get(user=request.user)
                current_user.purchase = purchase
                current_user.product_tag = tag
                current_user.transaction_status = tx_status
                current_user.tx = tx
                current_user.save()
                PartnerCommissionService.record_purchase(
                    user=request.user,
                    partner_service=current_user.partner_service,
                    tx=tx,
                    amount=price,
                )

                response_data = {
                    "status": "success",
                    "message": "Service booked successfully!",
                    "data": {
                        "booking data": serializer.data,
                        "product_tag": tag,
                    },
                }
                return Response(data=response_data, status=status.HTTP_201_CREATED)


@extend_schema(
    summary="List all consumable bookings for the user",
    tags=["Self-Service"],
    description="Returns a paginated list of all consumable (FMCG) service bookings made by the currently authenticated user.",
    responses={
        200: inline_serializer(
            "ConsumableBookingListResponse",
            fields={
                "count": s.IntegerField(),
                "next": s.CharField(allow_null=True),
                "previous": s.CharField(allow_null=True),
                "results": s.ListField(),
            },
        ),
    },
)
class ConsumableBookingList(generics.ListAPIView):
    """ConsumableBookingList lists all consumable bookings."""

    serializer_class = ConsumableSerializers
    permission_classes = [IsAuthenticated & (IsMemberOrPartner | IsSuperAdmin)]
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


@extend_schema(
    summary="Get details of a specific consumable booking",
    tags=["Self-Service"],
    description="Retrieves a single consumable (FMCG) service booking by ID. Returns 404 if the booking doesn't exist or doesn't belong to the authenticated user.",
    responses={
        200: ConsumableSerializers,
        404: inline_serializer(
            "ConsumableBookingDetailNotFound", fields={"error": s.CharField()}
        ),
    },
)
class ConsumableBookingDetail(generics.RetrieveAPIView):
    """
    ConsumableBookingDetail retrieves a specific consumable booking for
    the authenticated user.
    """

    serializer_class = ConsumableSerializers
    permission_classes = [IsAuthenticated & (IsMemberOrPartner | IsSuperAdmin)]

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


@extend_schema(
    summary="Book a land travel trip (one-way or round trip)",
    tags=["Self-Service"],
    description="Creates a land travel booking (one-way or round trip) for the authenticated user. No payment is charged at booking; a product tag is issued.",
    request=LandTravelsSerilaizers,
    responses={
        201: inline_serializer(
            "BookLandTripResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "data": s.DictField(),
            },
        ),
        400: inline_serializer(
            "BookLandTripError",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class BookLandTrip(generics.GenericAPIView):
    """
    BookLandTrip is a POST request route for booking a land trip, one way or round trip.
    """

    serializer_class = LandTravelsSerilaizers
    permission_classes = [IsAuthenticated & (IsMemberOrPartner | IsSuperAdmin)]

    def post(self, request):
        decrypted_payload = decrypt(request.data)
        serializer = self.serializer_class(data=decrypted_payload)
        if serializer.is_valid(raise_exception=True):
            rejection = partner_booking_rejection(
                request.user, serializer.validated_data.get("partner_service")
            )
            if rejection:
                return rejection
            try:
                authenticated_user = request.user
                payload = {
                    key: value.strip() if isinstance(value, str) else value
                    for key, value in decrypted_payload.items()
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
                partner_service = serializer.validated_data.get("partner_service")

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
                    partner_service=partner_service,
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
                    tx = TxModel.objects.create(
                        user=authenticated_user,
                        tx_type="Travel",
                        amount=0,
                        status="SUCCESS",
                        description="One way trip booked successfully.",
                    )
                    tag = ProductTagmanager.generate(service_type="LTS-")
                    land_travel.purchase = purchase
                    land_travel.product_tag = tag
                    land_travel.transaction_status = tx_status
                    land_travel.tx = tx
                    land_travel.save()
                    PartnerCommissionService.record_purchase(
                        user=authenticated_user,
                        partner_service=partner_service,
                        tx=tx,
                        amount=0,
                    )

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
                    tx = TxModel.objects.create(
                        user=authenticated_user,
                        tx_type="Travel",
                        amount=0,
                        status="SUCCESS",
                        description="Round trip booked successfully.",
                    )
                    tag = ProductTagmanager.generate(service_type="LTS-")
                    land_travel.purchase = purchase
                    land_travel.product_tag = tag
                    land_travel.transaction_status = tx_status
                    land_travel.tx = tx
                    land_travel.save()
                    PartnerCommissionService.record_purchase(
                        user=authenticated_user,
                        partner_service=partner_service,
                        tx=tx,
                        amount=0,
                    )

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
                    raise NotFound(encrypt("Invalid selection"))

            except Exception as err:
                logger.error("Self-service booking failed: %s", str(err), exc_info=True)
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "message": "Booking failed. Please try again.",
                        }
                    ),
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
        else:
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    summary="Get details of a specific land trip booking",
    tags=["Self-Service"],
    description="Retrieves a single land travel booking by ID. Returns 404 if the booking doesn't exist or doesn't belong to the authenticated user.",
    responses={
        200: LandTravelsSerilaizers,
        404: inline_serializer(
            "LandTripDetailNotFound", fields={"error": s.CharField()}
        ),
    },
)
class LandTripBookingDetail(generics.RetrieveAPIView):
    """
    LandTripBookingDetail retrieves a specific land trip booking for
    the authenticated user.
    """

    serializer_class = LandTravelsSerilaizers
    permission_classes = [IsAuthenticated & (IsMemberOrPartner | IsSuperAdmin)]

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


@extend_schema(
    summary="List all land trip bookings for the user",
    tags=["Self-Service"],
    description="Returns a paginated list of all land travel bookings made by the currently authenticated user.",
    responses={
        200: inline_serializer(
            "LandTripBookingListResponse",
            fields={
                "count": s.IntegerField(),
                "next": s.CharField(allow_null=True),
                "previous": s.CharField(allow_null=True),
                "results": s.ListField(),
            },
        ),
    },
)
class LandTripBookingList(generics.ListAPIView):
    """LandTripBookingList lists all land travel bookings."""

    serializer_class = LandTravelsSerilaizers
    permission_classes = [IsAuthenticated & (IsMemberOrPartner | IsSuperAdmin)]
    pagination_class = PaginationStyle

    def get_queryset(self):
        user = self.request.user
        queryset = LandTravels.objects.filter(user=user)
        return queryset

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()

        # Handle pagination manually so we can encrypt the whole response
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)

            paginated_data = {
                "count": self.paginator.page.paginator.count,
                "next": self.paginator.get_next_link(),
                "previous": self.paginator.get_previous_link(),
                "results": serializer.data,
            }

            encrypted = encrypt(paginated_data)
            return Response(data=encrypted, status=status.HTTP_200_OK)

        # Non-paginated response (rare case)
        serializer = self.get_serializer(queryset, many=True)
        encrypted = encrypt(serializer.data)
        return Response(data=encrypted, status=status.HTTP_200_OK)


@extend_schema(
    summary="Book a hotel room",
    tags=["Self-Service"],
    description="Creates a hotel room booking for the authenticated user and processes payment via wallet or card. Requires wallet PIN or biometric verification.",
    request=HotelSerializers,
    responses={
        200: inline_serializer(
            "BookHotelResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "data": s.DictField(),
            },
        ),
        400: inline_serializer(
            "BookHotelError", fields={"status": s.CharField(), "message": s.CharField()}
        ),
        401: inline_serializer(
            "BookHotelUnauthorized",
            fields={"status": s.CharField(), "error": s.CharField()},
        ),
        404: inline_serializer(
            "BookHotelNotFound",
            fields={"status": s.CharField(), "error": s.CharField()},
        ),
    },
)
class BookHotel(generics.GenericAPIView):
    """
    BookHotel is a POST request route for booking a hotel.
    """

    serializer_class = HotelSerializers
    permission_classes = [IsAuthenticated & (IsMemberOrPartner | IsSuperAdmin)]

    def post(self, request):
        decrypted_payload = decrypt(request.data)
        serializer = HotelSerializers(data=decrypted_payload)
        if serializer.is_valid(raise_exception=True):
            rejection = partner_booking_rejection(
                request.user, serializer.validated_data.get("partner_service")
            )
            if rejection:
                return rejection
            try:
                authenticated_user = request.user
                user_data = {
                    key: value.strip() if isinstance(value, str) else value
                    for key, value in decrypted_payload.items()
                }
                pin = user_data("pin")
                biometrics = user_data.get("use_biometrics")

                try:
                    account = WalletModel.objects.get(user=authenticated_user)
                except WalletModel.DoesNotExist:
                    return Response(
                        data=decrypt(
                            {"status": "fail", "error": "Account not found for user"}
                        ),
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
                            data=encrypt(
                                {
                                    "status": "fail",
                                    "error": "Account or PIN not found for user",
                                }
                            ),
                            status=status.HTTP_404_NOT_FOUND,
                        )

                if not verification:
                    return Response(
                        data=encrypt(
                            {"status": "fail", "error": "Invalid credentials"}
                        ),
                        status=status.HTTP_401_UNAUTHORIZED,
                    )

                # Inititate a debit on a users' account.
                amount = user_data.get("amount")
                payment_option = user_data.get("payment_option")
                user_detail = WalletModel.objects.get(user=authenticated_user)
                match payment_option:
                    case "WALLET":
                        debit_response = Wallet.Debit(
                            debitAccount=user_detail.account_number,
                            amount=amount,
                            reason="Debit for hotel booking.",
                            transactionReference="",
                        )
                        if debit_response.status_code == 200:
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
                            tx = TxModel.objects.create(
                                user=authenticated_user,
                                tx_type="Hotel",
                                amount=amount,
                                status="SUCCESS",
                                description="Hotel service booking paid successfully.",
                            )
                            tag = ProductTagmanager.generate(service_type="LTS-")
                            current_user = Hotels.objects.get(user=request.user)
                            current_user.purchase = purchase
                            current_user.product_tag = tag
                            current_user.transaction_status = tx_status
                            current_user.tx = tx
                            current_user.save()
                            PartnerCommissionService.record_purchase(
                                user=authenticated_user,
                                partner_service=current_user.partner_service,
                                tx=tx,
                                amount=amount,
                            )

                            response_data = {
                                "status": "Success!",
                                "message": "Hotel service booking paid successfully.",
                                "data": {
                                    "booking data": serializer.data,
                                    "product_tag": tag,
                                },
                            }

                            return Response(
                                data=encrypt(response_data), status=status.HTTP_200_OK
                            )
                        else:
                            TxModel.objects.create(
                                user=authenticated_user,
                                tx_type="Hotel",
                                amount=amount,
                                status="FAILED",
                                description="Hotel service booking failed.",
                            )
                            response_data = {
                                "status": "fail",
                                "details": debit_response.json(),
                            }
                            return Response(
                                data=encrypt(response_data),
                                status=status.HTTP_400_BAD_REQUEST,
                            )
                    case "CARD":
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
                        tx = TxModel.objects.create(
                            user=authenticated_user,
                            tx_type="Hotel",
                            amount=amount,
                            status="SUCCESS",
                            description="Hotel service booking paid successfully.",
                        )
                        tag = ProductTagmanager.generate(service_type="LTS-")
                        current_user = Hotels.objects.get(user=request.user)
                        current_user.purchase = purchase
                        current_user.product_tag = tag
                        current_user.transaction_status = tx_status
                        current_user.tx = tx
                        current_user.save()
                        PartnerCommissionService.record_purchase(
                            user=authenticated_user,
                            partner_service=current_user.partner_service,
                            tx=tx,
                            amount=amount,
                        )

                        response_data = {
                            "status": "Success!",
                            "message": "Hotel service booking paid successfully.",
                            "data": {
                                "booking data": serializer.data,
                                "product_tag": tag,
                            },
                        }

                        return Response(data=response_data, status=status.HTTP_200_OK)
            except Exception as err:
                logger.error("Self-service booking failed: %s", str(err), exc_info=True)
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "message": "Booking failed. Please try again.",
                        }
                    ),
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
        else:
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    summary="Rate a self-service booking",
    tags=["Self-Service"],
    description="Allows the authenticated user to rate and review a specific self-service booking (restaurant, gym, cinema, courier, consumable, land travel, or hotel). Each user may only rate a given service once.",
    request=CustomerRatingSerializer,
    responses={
        201: inline_serializer(
            "ServiceRatingResponse", fields={"success": s.CharField()}
        ),
        400: inline_serializer("ServiceRatingError", fields={"error": s.CharField()}),
        404: inline_serializer(
            "ServiceRatingNotFound", fields={"error": s.CharField()}
        ),
    },
)
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
    permission_classes = [IsAuthenticated & (IsMemberOrPartner | IsSuperAdmin)]
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


@extend_schema(
    summary="Get a self-service transaction by product tag",
    tags=["Self-Service"],
    description="Retrieves a self-service transaction record using its product tag prefix (RST, GYM, CIN, COU, FMCG, LTS, HOT). Returns 400 if not found.",
    responses={
        200: GetTransactionSerializer,
        400: inline_serializer(
            "GetTransactionNotFound", fields={"error": s.CharField()}
        ),
    },
)
class GetTransaction(generics.RetrieveAPIView):
    """
    GetTransaction is the GET request route used
    to retrieve a transaction using product tag.
    """

    serializer_class = GetTransactionSerializer
    permission_classes = [IsAuthenticated & (IsMemberOrPartner | IsSuperAdmin)]

    def get_queryset(self, request):
        decrypted_payload = decrypt(request.data)
        payment_tag = decrypted_payload["payment_tag"]
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
