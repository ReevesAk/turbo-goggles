"""
event/views.py

Views for the event/ticketing module, organized by role.

"""

import logging
from decimal import Decimal
from datetime import datetime, timedelta
from uuid import UUID

from django.db import IntegrityError, transaction
from django.db.models import Sum, Q
from django.utils import timezone
from django.core.cache import cache

from rest_framework import status, generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.pagination import PageNumberPagination

from drf_spectacular.utils import (
    extend_schema,
    OpenApiParameter,
)
from drf_spectacular.types import OpenApiTypes


from accounts.models import UserNotification
from banking.controllers import KYC, Transfers
from banking.helpers import cloudinary_to_base64, verify_wallet_auth
from commons import generate_txId, first_validation_error
from permissions import IsMember, IsPartner, IsPartnerAdminOrSuperAdmin
from security import encrypt, decrypt

from modules.billing_mixings import BrandChargeMixin, _round_money
from .models import (
    Event,
    EventPartnerProfile,
    PartnerSaleWindow,
    PartnerTicketSale,
    Ticket,
    TicketCode,
    TicketConfiguration,
    TicketOrder,
    TicketPurchase,
    TicketTransfer,
)
from accounts.models import User
from .serializers import (
    EventAdminReviewSerializer,
    EventPartnerSerializer,
    EventPartnerVerificationAdminReviewSerializer,
    EventPartnerVerificationReadSerializer,
    EventPartnerVerificationSubmitSerializer,
    EventPublicSerializer,
    PartnerSaleWindowSerializer,
    PartnerTicketSaleSerializer,
    TicketCartPaymentSerializer,
    TicketCodeSerializer,
    TicketConfigurationSerializer,
    TicketOrderReadSerializer,
    TicketPartnerSerializer,
    TicketPaymentSerializer,
    TicketPublicSerializer,
    TicketPurchaseReadSerializer,
    TicketTransferRequestSerializer,
    TicketTransferRespondSerializer,
    TicketVerifySerializer,
)

logger = logging.getLogger(__name__)


class EventTicketPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


# ===================
#  HELPER FUNCTIONS
# ===================


def _error_response(message: str, status_code: int) -> Response:
    """Return a consistent encrypted error response."""
    return Response(encrypt({"status": "fail", "message": message}), status=status_code)


def _success_response(
    message: str, data: dict = None, status_code: int = 200
) -> Response:
    """Return a consistent encrypted success response."""
    response = {"status": "success", "message": message}
    if data is not None:
        response["data"] = data
    return Response(encrypt(response), status=status_code)


def _decrypt_request_data(request):
    """Decrypt request data with error handling."""
    try:
        return decrypt(request.data)
    except Exception as e:
        logger.error(f"Decryption failed: {e}")
        return None


def _validate_serializer(serializer):
    """Validate serializer and return error response if invalid."""
    try:
        serializer.is_valid(raise_exception=True)
        return None
    except DRFValidationError as exc:
        message = first_validation_error(exc.detail)
        return _error_response(message, status.HTTP_400_BAD_REQUEST)


def _get_event_by_slug_or_id(value: str):
    """Get event by slug or UUID."""
    try:
        UUID(value)
        return Event.objects.filter(id=value).first()
    except (ValueError, TypeError):
        return Event.objects.filter(slug=value).first()


def _require_verified_partner(user):
    """
    Gate event creation on the *event-specific* partner verification, not the
    legacy `User.business_verified` flag. A partner is eligible only when they
    have an APPROVED `EventPartnerProfile`.

    The error message points them to the new dedicated verification endpoint
    so the front-end can deep-link straight to it.
    """
    if not EventPartnerProfile.is_partner_verified(user):
        profile = EventPartnerProfile.objects.filter(user=user).first()
        if profile is None:
            message = (
                "You are not yet verified to create events. Please complete "
                "event-partner verification (NIN + business bank account) first."
            )
        elif profile.status == EventPartnerProfile.Status.PENDING:
            message = (
                "Your event-partner verification is still under review. "
                "You will be notified once it is approved."
            )
        elif profile.status == EventPartnerProfile.Status.REJECTED:
            message = (
                "Your event-partner verification was rejected. "
                "Please review the reason and resubmit."
            )
        else:
            message = "You are not eligible to create events."

        return _error_response(message, status.HTTP_403_FORBIDDEN)
    return None


# ======================
#  MEMBER-FACING VIEWS
# ======================


@extend_schema(
    summary="List all public events",
    tags=["Events [Member]"],
    description="Returns all events that are currently on sale. Cached for 5 minutes.",
    parameters=[
        OpenApiParameter(
            name="category",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            description="Filter events by category",
            required=False,
        ),
        OpenApiParameter(
            name="mode",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            description="Filter events by mode (Physical, Online, Hybrid)",
            required=False,
        ),
        OpenApiParameter(
            name="upcoming",
            type=OpenApiTypes.BOOL,
            location=OpenApiParameter.QUERY,
            description="Only show upcoming events",
            required=False,
        ),
        OpenApiParameter(
            name="search",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            description="Search by event name",
            required=False,
        ),
    ],
)
class EventPublicListView(generics.ListAPIView):
    """GET /events/ - List all public events."""

    serializer_class = EventPublicSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = EventTicketPagination

    def get_queryset(self):
        now = timezone.now()
        qs = Event.objects.filter(
            status=Event.Status.ON_SALE,
            start_date__lte=now,
            end_date__gte=now,
        )

        category = self.request.query_params.get("category")
        if category:
            qs = qs.filter(category__iexact=category)

        mode = self.request.query_params.get("mode")
        if mode:
            qs = qs.filter(mode__iexact=mode)

        upcoming = self.request.query_params.get("upcoming", "false").lower() == "true"
        if upcoming:
            qs = qs.filter(start_date__gte=now)

        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(
                Q(event_name__icontains=search)
                | Q(user__business_name__icontains=search)
            )

        return qs.order_by("-approved_at", "-created_at")

    def list(self, request, *args, **kwargs):
        cache_key = f"events_public:{request.GET.urlencode()}"
        cached = cache.get(cache_key)

        if cached:
            return Response(encrypt(cached), status=status.HTTP_200_OK)

        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)

        response_data = {
            "status": "success",
            "message": "Events retrieved successfully.",
            "data": {
                "count": queryset.count(),
                "results": serializer.data,
            },
        }

        cache.set(cache_key, response_data, timeout=300)
        return Response(encrypt(response_data), status=status.HTTP_200_OK)


@extend_schema(
    summary="Get event details with tickets",
    tags=["Events [Member]"],
    description="Returns detailed event information including all available ticket types.",
)
class EventPublicDetailView(generics.RetrieveAPIView):
    """GET /events/<slug_or_id>/ - Get event details."""

    serializer_class = EventPublicSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "slug"

    def get_queryset(self):
        return Event.objects.filter(status=Event.Status.ON_SALE)

    def retrieve(self, request, *args, **kwargs):
        lookup_value = kwargs.get("slug")
        event = _get_event_by_slug_or_id(lookup_value)

        if not event or event.status != Event.Status.ON_SALE:
            return _error_response("Event not found.", status.HTTP_404_NOT_FOUND)

        event.update_view_count()

        event_serializer = self.get_serializer(event)
        tickets = event.create_ticket.filter(is_active=True)
        ticket_serializer = TicketPublicSerializer(tickets, many=True)

        return _success_response(
            "Event details retrieved successfully.",
            {
                "event": event_serializer.data,
                "tickets": ticket_serializer.data,
            },
        )


@extend_schema(
    summary="List available tickets for an event",
    tags=["Tickets [Member]"],
    description="Returns all active, on-sale ticket types for a given event.",
)
class EventTicketsListView(generics.ListAPIView):
    """GET /events/<slug_or_id>/tickets/ - List event tickets."""

    serializer_class = TicketPublicSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        event_slug = self.kwargs.get("slug")
        event = _get_event_by_slug_or_id(event_slug)

        if not event:
            return Ticket.objects.none()

        return event.create_ticket.filter(is_active=True)

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        if not queryset.exists():
            return _error_response("Event not found.", status.HTTP_404_NOT_FOUND)

        serializer = self.get_serializer(queryset, many=True)
        return _success_response(
            "Tickets retrieved successfully.",
            {"tickets": serializer.data},
        )


@extend_schema(
    summary="Purchase tickets with payment",
    tags=["Tickets [Member]"],
    description="Purchase tickets using either wallet or card payment.",
    request=TicketPaymentSerializer,
)
class TicketPurchaseView(BrandChargeMixin, generics.GenericAPIView):
    """
    POST /tickets/purchase/ - Purchase tickets.

    Uses BrandChargeMixin for idempotent payment processing with:
    - Wallet payment (PIN/biometric verification + debit)
    - Card payment (Paystack verification)
    - Automatic refund on item creation failure
    - PENDING/SUCCESS/FAILED transaction tracking
    """

    serializer_class = TicketPaymentSerializer
    permission_classes = [IsAuthenticated, IsMember]

    def post(self, request, *args, **kwargs):
        try:
            decrypted_data = _decrypt_request_data(request)
            if decrypted_data is None:
                return _error_response(
                    "Invalid request format.", status.HTTP_400_BAD_REQUEST
                )

            serializer = self.get_serializer(data=decrypted_data)
            error_response = _validate_serializer(serializer)
            if error_response:
                return error_response

            user = request.user
            validated_data = serializer.validated_data
            ticket = validated_data["ticket"]
            quantity = validated_data["quantity"]
            payment_option = validated_data.get("payment_option")
            pin = validated_data.get("pin")
            use_biometrics = validated_data.get("use_biometrics", False)
            card_reference = validated_data.get("card_reference")

            # Get idempotency key from header or body
            idempotency_key = request.headers.get(
                "Idempotency-Key"
            ) or decrypted_data.get("idempotency_key")

            total_amount = _round_money(ticket.price * quantity)

            # Generate tx_reference using idempotency key if provided
            tx_reference = idempotency_key if idempotency_key else generate_txId()

            # Verify wallet authentication before processing
            is_verified, error_response = verify_wallet_auth(
                user=user,
                payment_option=payment_option,
                pin=pin,
                use_biometrics=use_biometrics,
            )
            if not is_verified:
                return error_response

            # Use BrandChargeMixin for atomic payment processing
            purchase, error_response = self.charge_and_create(
                user=user,
                payment_option=payment_option,
                card_reference=card_reference,
                amount=total_amount,
                tx_reference=tx_reference,
                tx_type="Ticket Purchase",
                tx_description=f"Ticket purchase: {quantity}x {ticket.name} for {ticket.event.event_name}",
                notification_title="Ticket Purchase Successful",
                notification_phrase=f"{quantity}x {ticket.name} tickets for {ticket.event.event_name}",
                activity_description=f"purchased {quantity}x {ticket.name} tickets",
                debit_reason=f"Ticket purchase: {quantity}x {ticket.name}",
                save_fn=self._create_ticket_purchase(
                    user=user,
                    ticket=ticket,
                    quantity=quantity,
                    total_amount=total_amount,
                    tx_reference=tx_reference,
                    idempotency_key=idempotency_key,
                ),
            )

            if error_response is not None:
                return error_response

            # Refresh purchase from database and get ticket codes
            purchase.refresh_from_db()
            codes = purchase.codes.all()

            return _success_response(
                "Tickets purchased successfully!",
                {
                    "purchase": TicketPurchaseReadSerializer(purchase).data,
                    "payment_reference": tx_reference,
                    "total_amount": str(total_amount),
                    "ticket_codes": TicketCodeSerializer(codes, many=True).data,
                },
                status.HTTP_201_CREATED,
            )

        except DRFValidationError as exc:
            message = first_validation_error(exc.detail)
            logger.warning("Ticket purchase validation failed: %s", exc.detail)
            return _error_response(message, status.HTTP_400_BAD_REQUEST)

        except Exception as err:
            logger.error(f"Ticket purchase failed: {str(err)}", exc_info=True)
            return _error_response(
                "An error occurred during purchase.",
                status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def _create_ticket_purchase(
        self, user, ticket, quantity, total_amount, tx_reference, idempotency_key
    ):
        """
        Returns a save_fn closure for BrandChargeMixin.charge_and_create().
        """

        def save_fn():
            # Create purchase record
            purchase = TicketPurchase.objects.create(
                member=user,
                ticket=ticket,
                event=ticket.event,
                quantity=quantity,
                unit_price=ticket.price,
                total_amount=total_amount,
                status=TicketPurchase.Status.PENDING,
                payment_reference=tx_reference,
            )

            # Mark as paid
            try:
                purchase.mark_as_paid(tx_reference)
            except ValueError as e:
                logger.error(f"Slot reservation failed for purchase {purchase.id}: {e}")
                raise

            return purchase

        return save_fn


@extend_schema(
    summary="Purchase multiple ticket types (cart checkout)",
    tags=["Tickets [Member]"],
    description="Purchase multiple ticket types in a single transaction.",
    request=TicketCartPaymentSerializer,
)
class TicketCartPurchaseView(BrandChargeMixin, generics.GenericAPIView):
    """
    POST /tickets/cart-purchase/ - Purchase multiple ticket types at once.
    """

    serializer_class = TicketCartPaymentSerializer
    permission_classes = [IsAuthenticated, IsMember]

    def post(self, request, *args, **kwargs):
        try:
            decrypted_data = _decrypt_request_data(request)
            if decrypted_data is None:
                return _error_response(
                    "Invalid request format.", status.HTTP_400_BAD_REQUEST
                )

            serializer = self.get_serializer(data=decrypted_data)
            error_response = _validate_serializer(serializer)
            if error_response:
                return error_response

            user = request.user
            validated_data = serializer.validated_data
            items = validated_data["items"]
            payment_option = validated_data.get("payment_option")
            pin = validated_data.get("pin")
            use_biometrics = validated_data.get("use_biometrics", False)
            card_reference = validated_data.get("card_reference")

            # Get idempotency key
            idempotency_key = request.headers.get(
                "Idempotency-Key"
            ) or decrypted_data.get("idempotency_key")

            # Calculate total amount
            total_amount = Decimal("0")
            ticket_items = []
            first_ticket = None

            for item_data in items:
                ticket = Ticket.objects.select_related("event").get(
                    id=item_data["ticket_id"]
                )
                quantity = item_data["quantity"]
                item_total = _round_money(ticket.price * quantity)
                total_amount += item_total

                if first_ticket is None:
                    first_ticket = ticket

                ticket_items.append(
                    {
                        "ticket": ticket,
                        "quantity": quantity,
                        "item_total": item_total,
                    }
                )

            total_amount = _round_money(total_amount)
            event = first_ticket.event

            # Generate tx_reference
            tx_reference = idempotency_key if idempotency_key else generate_txId()

            # Verify wallet authentication
            is_verified, error_response = verify_wallet_auth(
                user=user,
                payment_option=payment_option,
                pin=pin,
                use_biometrics=use_biometrics,
            )
            if not is_verified:
                return error_response

            # Build notification description
            item_descriptions = [
                f"{item['quantity']}x {item['ticket'].name}" for item in ticket_items
            ]
            notification_phrase = ", ".join(item_descriptions)

            # Use BrandChargeMixin
            order, error_response = self.charge_and_create(
                user=user,
                payment_option=payment_option,
                card_reference=card_reference,
                amount=total_amount,
                tx_reference=tx_reference,
                tx_type="Ticket Purchase",
                tx_description=f"Ticket purchase: {notification_phrase} for {event.event_name}",
                notification_title="Ticket Purchase Successful",
                notification_phrase=f"{notification_phrase} for {event.event_name}",
                activity_description=f"purchased {notification_phrase} tickets",
                debit_reason=f"Ticket purchase: {notification_phrase}",
                save_fn=self._create_ticket_order(
                    user=user,
                    event=event,
                    ticket_items=ticket_items,
                    total_amount=total_amount,
                    tx_reference=tx_reference,
                    idempotency_key=idempotency_key,
                ),
            )

            if error_response is not None:
                return error_response

            # Refresh order and get all ticket codes
            order.refresh_from_db()
            all_codes = TicketCode.objects.filter(
                purchase__order=order,
                purchase__status=TicketPurchase.Status.PAID,
            ).select_related("purchase", "purchase__event", "purchase__ticket")

            return _success_response(
                "Tickets purchased successfully!",
                {
                    "order": TicketOrderReadSerializer(order).data,
                    "payment_reference": tx_reference,
                    "total_amount": str(total_amount),
                    "ticket_codes": TicketCodeSerializer(all_codes, many=True).data,
                },
                status.HTTP_201_CREATED,
            )

        except DRFValidationError as exc:
            message = first_validation_error(exc.detail)
            logger.warning("Ticket cart purchase validation failed: %s", exc.detail)
            return _error_response(message, status.HTTP_400_BAD_REQUEST)

        except Exception as err:
            logger.error(f"Ticket cart purchase failed: {str(err)}", exc_info=True)
            return _error_response(
                "An error occurred during purchase.",
                status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def _create_ticket_order(
        self, user, event, ticket_items, total_amount, tx_reference, idempotency_key
    ):
        """Returns a save_fn closure for BrandChargeMixin."""

        def save_fn():
            # Create the order
            order = TicketOrder.objects.create(
                member=user,
                event=event,
                total_amount=total_amount,
                status=TicketOrder.Status.PENDING,
                payment_reference=tx_reference,
                idempotency_key=idempotency_key,
            )

            # Create line items
            for item in ticket_items:
                TicketPurchase.objects.create(
                    order=order,
                    member=user,
                    ticket=item["ticket"],
                    event=event,
                    quantity=item["quantity"],
                    unit_price=item["ticket"].price,
                    total_amount=item["item_total"],
                    status=TicketPurchase.Status.PENDING,
                    payment_reference=tx_reference,
                )

            # Mark order as paid
            try:
                order.mark_as_paid(tx_reference)
            except ValueError as e:
                logger.error(f"Slot reservation failed for order {order.id}: {e}")
                raise

            return order

        return save_fn


@extend_schema(
    summary="List member's ticket orders",
    tags=["Tickets [Member]"],
    description="Returns all ticket orders for the authenticated member.",
)
class MemberOrderListView(generics.ListAPIView):
    """GET /tickets/orders/ - List member's orders."""

    serializer_class = TicketOrderReadSerializer
    permission_classes = [IsAuthenticated, IsMember]

    def get_queryset(self):
        qs = (
            TicketOrder.objects.filter(member=self.request.user)
            .select_related("event")
            .prefetch_related("items", "items__codes")
        )

        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)

        event_id = self.request.query_params.get("event")
        if event_id:
            qs = qs.filter(event_id=event_id)

        return qs.order_by("-created_at")

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)

        return _success_response(
            "Your orders retrieved successfully.",
            {"orders": serializer.data},
        )


@extend_schema(
    summary="List member's ticket purchases",
    tags=["Tickets [Member]"],
    description="Returns all ticket purchases for the authenticated member.",
)
class MemberPurchaseListView(generics.ListAPIView):
    """GET /tickets/purchases/ - List member's purchases."""

    serializer_class = TicketPurchaseReadSerializer
    permission_classes = [IsAuthenticated, IsMember]

    def get_queryset(self):
        qs = (
            TicketPurchase.objects.filter(member=self.request.user)
            .select_related("ticket", "event", "order")
            .prefetch_related("codes")
        )

        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)

        upcoming = self.request.query_params.get("upcoming", "false").lower() == "true"
        if upcoming:
            qs = qs.filter(event__start_date__gte=timezone.now())

        return qs.order_by("-purchased_at")

    def list(self, request, *args, **kwargs):
        cache_key = f"member_purchases:{request.user.id}:{request.GET.urlencode()}"
        cached = cache.get(cache_key)

        if cached:
            return Response(encrypt(cached), status=status.HTTP_200_OK)

        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)

        response_data = {
            "status": "success",
            "message": "Your purchases retrieved successfully.",
            "data": serializer.data,
        }

        cache.set(cache_key, response_data, timeout=60)
        return Response(encrypt(response_data), status=status.HTTP_200_OK)


@extend_schema(
    summary="Get member's ticket codes",
    tags=["Tickets [Member]"],
    description="Returns all ticket codes owned by the authenticated member.",
)
class MemberTicketCodesView(generics.ListAPIView):
    """GET /tickets/my-codes/ - Get member's ticket codes."""

    serializer_class = TicketCodeSerializer
    permission_classes = [IsAuthenticated, IsMember]

    def get_queryset(self):
        qs = TicketCode.objects.filter(
            current_owner=self.request.user,
            purchase__status=TicketPurchase.Status.PAID,
        ).select_related("purchase", "purchase__event", "purchase__ticket")

        purchase_id = self.request.query_params.get("purchase")
        if purchase_id:
            qs = qs.filter(purchase_id=purchase_id)

        event_id = self.request.query_params.get("event")
        if event_id:
            qs = qs.filter(purchase__event_id=event_id)

        checked_in = self.request.query_params.get("checked_in")
        if checked_in is not None:
            checked_in_bool = checked_in.lower() == "true"
            qs = qs.filter(is_checked_in=checked_in_bool)

        return qs.order_by("-created_at")

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)

        return _success_response(
            "Your ticket codes retrieved successfully.",
            {"tickets": serializer.data},
        )


@extend_schema(
    summary="Request a ticket transfer",
    tags=["Tickets [Member]"],
    description="Request to transfer ownership of a single ticket code to another member.",
)
class TicketTransferRequestView(generics.CreateAPIView):
    """POST /tickets/transfer/request/ - Request transfer."""

    serializer_class = TicketTransferRequestSerializer
    permission_classes = [IsAuthenticated, IsMember]

    def create(self, request, *args, **kwargs):
        decrypted_data = _decrypt_request_data(request)
        if decrypted_data is None:
            return _error_response(
                "Invalid request format.", status.HTTP_400_BAD_REQUEST
            )

        serializer = self.get_serializer(data=decrypted_data)
        error_response = _validate_serializer(serializer)
        if error_response:
            return error_response

        transfer = serializer.save()

        UserNotification.objects.create(
            user=transfer.to_user,
            title="Ticket Transfer Request",
            message=f"{transfer.from_user.full_name} has sent you a ticket transfer request.",
        )

        return _success_response(
            "Transfer request sent successfully.",
            TicketTransferRequestSerializer(transfer).data,
            status.HTTP_201_CREATED,
        )


@extend_schema(
    summary="List pending transfer requests",
    tags=["Tickets [Member]"],
    description="Returns all pending transfer requests sent to the authenticated member.",
)
class PendingTransferRequestsView(generics.ListAPIView):
    """GET /tickets/transfer/pending/ - List pending transfers."""

    serializer_class = TicketTransferRequestSerializer
    permission_classes = [IsAuthenticated, IsMember]

    def get_queryset(self):
        return TicketTransfer.objects.filter(
            to_user=self.request.user,
            status=TicketTransfer.Status.PENDING,
        ).select_related(
            "ticket_code",
            "ticket_code__purchase",
            "ticket_code__purchase__event",
            "ticket_code__purchase__ticket",
            "from_user",
        )

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)

        return _success_response(
            "Pending transfers retrieved successfully.",
            {"transfers": serializer.data},
        )


@extend_schema(
    summary="Accept or decline a transfer request",
    tags=["Tickets [Member]"],
    description="Accept or decline a pending transfer request.",
)
class TicketTransferRespondView(generics.GenericAPIView):
    """POST /tickets/transfer/<id>/respond/ - Respond to transfer."""

    serializer_class = TicketTransferRespondSerializer
    permission_classes = [IsAuthenticated, IsMember]

    def post(self, request, *args, **kwargs):
        transfer_id = kwargs.get("id")

        try:
            transfer = TicketTransfer.objects.select_related(
                "ticket_code", "from_user", "to_user"
            ).get(id=transfer_id)
        except TicketTransfer.DoesNotExist:
            return _error_response("Transfer not found.", status.HTTP_404_NOT_FOUND)

        decrypted_data = _decrypt_request_data(request)
        if decrypted_data is None:
            return _error_response(
                "Invalid request format.", status.HTTP_400_BAD_REQUEST
            )

        serializer = self.get_serializer(
            data=decrypted_data,
            context={"transfer": transfer, "request": request},
        )

        error_response = _validate_serializer(serializer)
        if error_response:
            return error_response

        updated_transfer = serializer.save()

        action_text = (
            "accepted"
            if updated_transfer.status == TicketTransfer.Status.ACCEPTED
            else "declined"
        )

        UserNotification.objects.create(
            user=updated_transfer.from_user,
            title=f"Transfer {action_text.capitalize()}",
            message=f"{updated_transfer.to_user.full_name} has {action_text} your ticket transfer request.",
        )

        return _success_response(
            f"Transfer {action_text} successfully.",
            TicketTransferRequestSerializer(updated_transfer).data,
        )


@extend_schema(
    summary="Cancel a pending transfer",
    tags=["Tickets [Member]"],
    description="Cancel a pending transfer request initiated by the authenticated member.",
)
class TicketTransferCancelView(generics.GenericAPIView):
    """POST /tickets/transfer/<id>/cancel/ - Cancel transfer."""

    permission_classes = [IsAuthenticated, IsMember]

    def post(self, request, *args, **kwargs):
        transfer_id = kwargs.get("id")

        try:
            transfer = TicketTransfer.objects.get(
                id=transfer_id, from_user=request.user
            )
        except TicketTransfer.DoesNotExist:
            return _error_response("Transfer not found.", status.HTTP_404_NOT_FOUND)

        if transfer.status != TicketTransfer.Status.PENDING:
            return _error_response(
                "This transfer is no longer pending.",
                status.HTTP_400_BAD_REQUEST,
            )

        transfer.cancel()

        return _success_response("Transfer cancelled successfully.")


# =======================
#  PARTNER-FACING VIEWS
# =======================


@extend_schema(
    summary="List partner's events",
    tags=["Events [Partner]"],
    description="Returns all events owned by the authenticated partner.",
)
class PartnerEventListView(generics.ListCreateAPIView):
    """GET/POST /partner/events/ - List/create partner events."""

    serializer_class = EventPartnerSerializer
    permission_classes = [IsAuthenticated, IsPartner]
    pagination_class = EventTicketPagination

    def get_queryset(self):
        qs = Event.objects.filter(user=self.request.user)

        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)

        upcoming = self.request.query_params.get("upcoming", "false").lower() == "true"
        if upcoming:
            qs = qs.filter(start_date__gte=timezone.now())

        return qs.order_by("-created_at")

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)

        return _success_response(
            "Your events retrieved successfully.",
            {"events": serializer.data},
        )

    def create(self, request, *args, **kwargs):
        # Require verified partner before event creation
        error_response = _require_verified_partner(request.user)
        if error_response:
            return error_response

        decrypted_data = _decrypt_request_data(request)
        if decrypted_data is None:
            return _error_response(
                "Invalid request format.", status.HTTP_400_BAD_REQUEST
            )

        serializer = self.get_serializer(data=decrypted_data)
        error_response = _validate_serializer(serializer)
        if error_response:
            return error_response

        event = serializer.save()

        return _success_response(
            "Event created successfully and submitted for review.",
            EventPartnerSerializer(event).data,
            status.HTTP_201_CREATED,
        )


@extend_schema(
    summary="Get/update/delete partner's event",
    tags=["Events [Partner]"],
    description="Retrieve, update, or delete an event owned by the partner.",
)
class PartnerEventDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET/PATCH/DELETE /partner/events/<id>/ - Manage partner event."""

    serializer_class = EventPartnerSerializer
    permission_classes = [IsAuthenticated, IsPartner]
    lookup_field = "id"

    def get_queryset(self):
        return Event.objects.filter(user=self.request.user)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return _success_response(
            "Event retrieved successfully.",
            {"event": serializer.data},
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", True)
        instance = self.get_object()

        # Prevent editing on-sale events
        if instance.status == Event.Status.ON_SALE:
            return _error_response(
                "Cannot edit an event that is currently on sale.",
                status.HTTP_400_BAD_REQUEST,
            )

        decrypted_data = _decrypt_request_data(request)
        if decrypted_data is None:
            return _error_response(
                "Invalid request format.", status.HTTP_400_BAD_REQUEST
            )

        serializer = self.get_serializer(instance, data=decrypted_data, partial=partial)
        error_response = _validate_serializer(serializer)
        if error_response:
            return error_response

        event = serializer.save()

        return _success_response(
            "Event updated successfully.",
            {"event": EventPartnerSerializer(event).data},
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()

        if instance.status not in [Event.Status.DRAFT, Event.Status.REJECTED]:
            return _error_response(
                "Only draft or rejected events can be deleted.",
                status.HTTP_400_BAD_REQUEST,
            )

        # Check for existing purchases
        if instance.ticket_purchases.exists():
            return _error_response(
                "Cannot delete event with existing purchases.",
                status.HTTP_400_BAD_REQUEST,
            )

        instance.delete()
        return _success_response("Event deleted successfully.")


@extend_schema(
    summary="List/create tickets for partner's event",
    tags=["Tickets [Partner]"],
    description="List all tickets for a partner's event or create a new ticket type.",
)
class PartnerEventTicketsView(generics.ListCreateAPIView):
    """GET/POST /partner/events/<event_id>/tickets/ - Manage event tickets."""

    serializer_class = TicketPartnerSerializer
    permission_classes = [IsAuthenticated, IsPartner]

    def get_queryset(self):
        event_id = self.kwargs.get("event_id")
        try:
            event = Event.objects.get(id=event_id, user=self.request.user)
        except Event.DoesNotExist:
            return Ticket.objects.none()
        return event.create_ticket.all()

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        if not queryset.exists() and not self._event_exists():
            return _error_response("Event not found.", status.HTTP_404_NOT_FOUND)

        serializer = self.get_serializer(queryset, many=True)
        return _success_response(
            "Tickets retrieved successfully.",
            {"tickets": serializer.data},
        )

    def create(self, request, *args, **kwargs):
        event_id = self.kwargs.get("event_id")

        try:
            event = Event.objects.get(id=event_id, user=self.request.user)
        except Event.DoesNotExist:
            return _error_response("Event not found.", status.HTTP_404_NOT_FOUND)

        # Check event status
        if event.status == Event.Status.ON_SALE:
            return _error_response(
                "Cannot create tickets for an event that is already on sale.",
                status.HTTP_400_BAD_REQUEST,
            )

        decrypted_data = _decrypt_request_data(request)
        if decrypted_data is None:
            return _error_response(
                "Invalid request format.", status.HTTP_400_BAD_REQUEST
            )

        decrypted_data["event"] = str(event.id)

        serializer = self.get_serializer(data=decrypted_data)
        error_response = _validate_serializer(serializer)
        if error_response:
            return error_response

        ticket = serializer.save()

        return _success_response(
            "Ticket created successfully.",
            TicketPartnerSerializer(ticket).data,
            status.HTTP_201_CREATED,
        )

    def _event_exists(self):
        try:
            Event.objects.get(id=self.kwargs.get("event_id"), user=self.request.user)
            return True
        except Event.DoesNotExist:
            return False


@extend_schema(
    summary="Get/update/delete partner's ticket",
    tags=["Tickets [Partner]"],
    description="Retrieve, update, or delete a ticket owned by the partner.",
)
class PartnerTicketDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET/PATCH/DELETE /partner/tickets/<id>/ - Manage partner ticket."""

    serializer_class = TicketPartnerSerializer
    permission_classes = [IsAuthenticated, IsPartner]
    lookup_field = "id"

    def get_queryset(self):
        return Ticket.objects.filter(event__user=self.request.user)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return _success_response(
            "Ticket retrieved successfully.",
            {"ticket": serializer.data},
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", True)
        instance = self.get_object()

        # Prevent editing tickets for on-sale events
        if instance.event.status == Event.Status.ON_SALE:
            return _error_response(
                "Cannot edit ticket for an event that is currently on sale.",
                status.HTTP_400_BAD_REQUEST,
            )

        decrypted_data = _decrypt_request_data(request)
        if decrypted_data is None:
            return _error_response(
                "Invalid request format.", status.HTTP_400_BAD_REQUEST
            )

        serializer = self.get_serializer(instance, data=decrypted_data, partial=partial)
        error_response = _validate_serializer(serializer)
        if error_response:
            return error_response

        ticket = serializer.save()

        return _success_response(
            "Ticket updated successfully.",
            TicketPartnerSerializer(ticket).data,
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()

        if instance.purchases.filter(status=TicketPurchase.Status.PAID).exists():
            return _error_response(
                "Cannot delete a ticket with existing purchases.",
                status.HTTP_400_BAD_REQUEST,
            )

        instance.delete()
        return _success_response("Ticket deleted successfully.")


@extend_schema(
    summary="Get partner's sales ledger",
    tags=["Events [Partner]"],
    description="Returns the partner's ticket sales ledger with settlement status.",
)
class PartnerSalesLedgerView(generics.ListAPIView):
    """GET /partner/sales/ - Get partner sales ledger."""

    serializer_class = PartnerTicketSaleSerializer
    permission_classes = [IsAuthenticated, IsPartner]

    def get_queryset(self):
        qs = PartnerTicketSale.objects.filter(partner=self.request.user).select_related(
            "event", "ticket", "purchase", "purchase__member"
        )

        settlement_status = self.request.query_params.get("settlement_status")
        if settlement_status:
            qs = qs.filter(settlement_status=settlement_status)

        event_id = self.request.query_params.get("event")
        if event_id:
            qs = qs.filter(event_id=event_id)

        return qs.order_by("-created_at")

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)

        total_gross = queryset.aggregate(Sum("gross_amount"))[
            "gross_amount__sum"
        ] or Decimal("0")
        total_net = queryset.aggregate(Sum("net_amount"))["net_amount__sum"] or Decimal(
            "0"
        )
        total_fees = queryset.aggregate(Sum("platform_fee_amount"))[
            "platform_fee_amount__sum"
        ] or Decimal("0")
        pending = queryset.filter(
            settlement_status=PartnerTicketSale.SettlementStatus.PENDING
        ).aggregate(Sum("net_amount"))["net_amount__sum"] or Decimal("0")

        return _success_response(
            "Sales ledger retrieved successfully.",
            {
                "sales": serializer.data,
                "summary": {
                    "total_gross": str(total_gross),
                    "total_net": str(total_net),
                    "total_fees": str(total_fees),
                    "pending_settlement": str(pending),
                },
            },
        )


@extend_schema(
    summary="Get event check-in statistics",
    tags=["Events [Partner]"],
    description="Returns check-in statistics for a partner's event.",
)
class PartnerEventCheckInStatsView(generics.GenericAPIView):
    """GET /partner/events/<id>/check-ins/ - Get check-in stats."""

    permission_classes = [IsAuthenticated, IsPartner]

    def get(self, request, *args, **kwargs):
        event_id = kwargs.get("id")

        try:
            event = Event.objects.get(id=event_id, user=request.user)
        except Event.DoesNotExist:
            return _error_response("Event not found.", status.HTTP_404_NOT_FOUND)

        total_tickets = TicketCode.objects.filter(
            purchase__event=event,
            purchase__status=TicketPurchase.Status.PAID,
        ).count()

        checked_in = TicketCode.objects.filter(
            purchase__event=event,
            purchase__status=TicketPurchase.Status.PAID,
            is_checked_in=True,
        ).count()

        not_checked_in = total_tickets - checked_in
        check_in_rate = (checked_in / total_tickets * 100) if total_tickets > 0 else 0

        return _success_response(
            "Check-in statistics retrieved successfully.",
            {
                "total_tickets": total_tickets,
                "checked_in": checked_in,
                "not_checked_in": not_checked_in,
                "check_in_rate": f"{check_in_rate:.1f}%",
            },
        )


# =====================
#  ADMIN-FACING VIEWS
# =====================


@extend_schema(
    summary="List all events (admin)",
    tags=["Events [Admin]"],
    description="Returns all events in the system for admin review.",
)
class AdminEventListView(generics.ListAPIView):
    """GET /admin/events/ - List all events."""

    serializer_class = EventPartnerSerializer
    permission_classes = [IsAuthenticated, IsPartnerAdminOrSuperAdmin]
    pagination_class = EventTicketPagination

    def get_queryset(self):
        qs = Event.objects.all()

        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)

        partner_email = self.request.query_params.get("partner")
        if partner_email:
            qs = qs.filter(user__email__icontains=partner_email)

        review_needed = (
            self.request.query_params.get("review_needed", "false").lower() == "true"
        )
        if review_needed:
            qs = qs.filter(status=Event.Status.IN_REVIEW)

        return qs.order_by("-created_at")

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)

        return _success_response(
            "Events retrieved successfully.",
            {
                "count": queryset.count(),
                "results": serializer.data,
            },
        )


class AdminEventReviewView(generics.GenericAPIView):
    """
    POST /admin/events/<id>/review/ - Review event.

    Approves or rejects an event. Uses POST method as specified in the API docs.
    PartnersAdmin and SuperAdmin can review events.
    """

    serializer_class = EventAdminReviewSerializer
    permission_classes = [IsAuthenticated, IsPartnerAdminOrSuperAdmin]
    lookup_field = "id"

    def get_queryset(self):
        return Event.objects.all()

    def get_object(self):
        """Get event by ID."""
        event_id = self.kwargs.get("id")
        try:
            return Event.objects.get(id=event_id)
        except Event.DoesNotExist:
            return None

    def post(self, request, *args, **kwargs):
        """Handle POST request for event review."""
        instance = self.get_object()

        if instance is None:
            return _error_response("Event not found.", status.HTTP_404_NOT_FOUND)

        decrypted_data = _decrypt_request_data(request)
        if decrypted_data is None:
            return _error_response(
                "Invalid request format.", status.HTTP_400_BAD_REQUEST
            )

        if instance.status not in [Event.Status.DRAFT, Event.Status.IN_REVIEW]:
            return _error_response(
                "Only draft or in-review events can be reviewed.",
                status.HTTP_400_BAD_REQUEST,
            )

        serializer = self.get_serializer(
            instance, data=decrypted_data, context={"request": request}
        )

        error_response = _validate_serializer(serializer)
        if error_response:
            return error_response

        event = serializer.save()

        logger.info(
            f"Event {event.id} reviewed by {request.user.email}: "
            f"status={event.status}, reason={event.rejection_reason}"
        )

        UserNotification.objects.create(
            user=event.user,
            title=f"Event {event.get_status_display()}",
            message=f"Your event '{event.event_name}' has been {event.get_status_display().lower()}.",
        )

        return _success_response(
            f"Event {event.get_status_display()} successfully.",
            EventAdminReviewSerializer(event).data,
        )


@extend_schema(
    summary="Verify and check-in a ticket",
    tags=["Tickets [Admin/Partner]"],
    description="Scan a ticket's QR code or enter the fallback code to check in an attendee.",
)
class TicketVerifyView(generics.GenericAPIView):
    """POST /admin/tickets/verify/ - Verify and check in ticket."""

    serializer_class = TicketVerifySerializer
    permission_classes = [IsAuthenticated, IsPartner]

    def post(self, request, *args, **kwargs):
        decrypted_data = _decrypt_request_data(request)
        if decrypted_data is None:
            return _error_response(
                "Invalid request format.", status.HTTP_400_BAD_REQUEST
            )

        # If partner, restrict to their events
        event_id = None
        if "Admin" not in request.user.active_role:
            event_id = self.kwargs.get("event_id")

        serializer = self.get_serializer(
            data=decrypted_data,
            context={"request": request, "event_id": event_id},
        )

        error_response = _validate_serializer(serializer)
        if error_response:
            return error_response

        ticket_code = serializer.save()

        return _success_response(
            "Ticket checked in successfully!",
            {
                "ticket_code": TicketCodeSerializer(ticket_code).data,
                "checked_in_at": ticket_code.checked_in_at.strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                "attendee_name": ticket_code.current_owner.full_name,
                "event_name": ticket_code.purchase.event.event_name,
            },
        )


@extend_schema(
    summary="Grant partner sale window (admin)",
    tags=["Tickets [Admin]"],
    description="Grants a partner a time-boxed window to increase ticket slot capacity.",
)
class AdminPartnerSaleWindowView(generics.CreateAPIView):
    """POST /admin/sale-windows/create/ - Grant sale window."""

    serializer_class = PartnerSaleWindowSerializer
    permission_classes = [IsAuthenticated, IsPartnerAdminOrSuperAdmin]

    def create(self, request, *args, **kwargs):
        decrypted_data = _decrypt_request_data(request)
        if decrypted_data is None:
            return _error_response(
                "Invalid request format.", status.HTTP_400_BAD_REQUEST
            )

        serializer = self.get_serializer(
            data=decrypted_data,
            context={"request": request},
        )

        error_response = _validate_serializer(serializer)
        if error_response:
            return error_response

        sale_window = serializer.save()

        UserNotification.objects.create(
            user=sale_window.partner,
            title="Sale Window Granted",
            message=f"You have been granted a sale window from {sale_window.starts_at} to {sale_window.ends_at}.",
        )

        logger.info(
            f"Sale window granted to {sale_window.partner.email} "
            f"by {request.user.email}: {sale_window.starts_at} - {sale_window.ends_at}"
        )

        return _success_response(
            "Sale window granted successfully.",
            PartnerSaleWindowSerializer(sale_window).data,
            status.HTTP_201_CREATED,
        )


@extend_schema(
    summary="List partner sale windows (admin)",
    tags=["Tickets [Admin]"],
    description="Returns all partner sale windows with filtering.",
)
class AdminSaleWindowListView(generics.ListAPIView):
    """GET /admin/sale-windows/ - List sale windows."""

    serializer_class = PartnerSaleWindowSerializer
    permission_classes = [IsAuthenticated, IsPartnerAdminOrSuperAdmin]

    def get_queryset(self):
        qs = PartnerSaleWindow.objects.all()

        partner_email = self.request.query_params.get("partner")
        if partner_email:
            qs = qs.filter(partner__email__icontains=partner_email)

        active = self.request.query_params.get("active", "false").lower() == "true"
        if active:
            now = timezone.now()
            qs = qs.filter(starts_at__lte=now, ends_at__gte=now)

        return qs.order_by("-created_at")

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)

        return _success_response(
            "Sale windows retrieved successfully.",
            {"sale_windows": serializer.data},
        )


@extend_schema(
    summary="Get/update ticket configuration (admin)",
    tags=["Tickets [Admin]"],
    description="Read or update the singleton ticket configuration.",
)
class AdminTicketConfigurationView(generics.RetrieveUpdateAPIView):
    """GET/PATCH /admin/ticket-config/ - Manage ticket configuration."""

    serializer_class = TicketConfigurationSerializer
    permission_classes = [IsAuthenticated, IsPartnerAdminOrSuperAdmin]

    def get_object(self):
        return TicketConfiguration.get_solo()

    def retrieve(self, request, *args, **kwargs):
        config = self.get_object()
        serializer = self.get_serializer(config)
        return _success_response(
            "Configuration retrieved successfully.",
            {"config": serializer.data},
        )

    def update(self, request, *args, **kwargs):
        config = self.get_object()
        partial = kwargs.pop("partial", True)

        decrypted_data = _decrypt_request_data(request)
        if decrypted_data is None:
            return _error_response(
                "Invalid request format.", status.HTTP_400_BAD_REQUEST
            )

        serializer = self.get_serializer(
            config, data=decrypted_data, partial=partial, context={"request": request}
        )

        error_response = _validate_serializer(serializer)
        if error_response:
            return error_response

        config = serializer.save()

        logger.info(f"Ticket configuration updated by {request.user.email}")

        return _success_response(
            "Configuration updated successfully.",
            {"config": TicketConfigurationSerializer(config).data},
        )


@extend_schema(
    summary="Get ticket statistics (admin)",
    tags=["Tickets [Admin]"],
    description="Returns comprehensive ticket statistics for admin dashboard.",
)
class AdminTicketStatsView(generics.GenericAPIView):
    """GET /admin/tickets/stats/ - Get ticket statistics."""

    permission_classes = [IsAuthenticated, IsPartnerAdminOrSuperAdmin]

    def get(self, request, *args, **kwargs):
        today = timezone.now().date()
        today_start = datetime.combine(today, datetime.min.time())
        today_end = datetime.combine(today, datetime.max.time())
        yesterday = timezone.now() - timedelta(hours=24)

        # Event stats
        total_events = Event.objects.count()
        events_on_sale = Event.objects.filter(status=Event.Status.ON_SALE).count()
        events_in_review = Event.objects.filter(status=Event.Status.IN_REVIEW).count()
        events_expired = Event.objects.filter(status=Event.Status.EXPIRED).count()

        # Purchase stats
        total_purchases = TicketPurchase.objects.count()
        paid_purchases = TicketPurchase.objects.filter(
            status=TicketPurchase.Status.PAID
        ).count()
        total_tickets_sold = TicketCode.objects.filter(
            purchase__status=TicketPurchase.Status.PAID
        ).count()

        # Revenue stats
        revenue_agg = PartnerTicketSale.objects.aggregate(
            total_gross=Sum("gross_amount"),
            total_net=Sum("net_amount"),
            total_fees=Sum("platform_fee_amount"),
        )
        total_revenue = revenue_agg["total_gross"] or Decimal("0")
        total_net = revenue_agg["total_net"] or Decimal("0")
        total_fees = revenue_agg["total_fees"] or Decimal("0")

        # Check-in stats
        check_ins_today = TicketCode.objects.filter(
            is_checked_in=True,
            checked_in_at__gte=today_start,
            checked_in_at__lte=today_end,
        ).count()
        total_check_ins = TicketCode.objects.filter(is_checked_in=True).count()

        # Pending stats
        pending_purchases = TicketPurchase.objects.filter(
            status=TicketPurchase.Status.PENDING
        ).count()
        pending_settlements = PartnerTicketSale.objects.filter(
            settlement_status=PartnerTicketSale.SettlementStatus.PENDING
        ).count()

        # Recent activity
        recent_purchases = TicketPurchase.objects.filter(
            purchased_at__gte=yesterday
        ).count()
        recent_check_ins = TicketCode.objects.filter(
            is_checked_in=True,
            checked_in_at__gte=yesterday,
        ).count()
        recent_transfers = TicketTransfer.objects.filter(
            requested_at__gte=yesterday
        ).count()

        return _success_response(
            "Statistics retrieved successfully.",
            {
                "events": {
                    "total": total_events,
                    "on_sale": events_on_sale,
                    "in_review": events_in_review,
                    "expired": events_expired,
                },
                "purchases": {
                    "total": total_purchases,
                    "paid": paid_purchases,
                    "pending": pending_purchases,
                    "tickets_sold": total_tickets_sold,
                },
                "revenue": {
                    "total_gross": str(total_revenue),
                    "total_net": str(total_net),
                    "total_fees": str(total_fees),
                },
                "check_ins": {
                    "today": check_ins_today,
                    "total": total_check_ins,
                },
                "settlements": {
                    "pending": pending_settlements,
                },
                "recent_activity": {
                    "purchases": recent_purchases,
                    "check_ins": recent_check_ins,
                    "transfers": recent_transfers,
                },
            },
        )


@extend_schema(
    summary="Get detailed event sales statistics",
    tags=["Stats [Admin/Partner]"],
    description=(
        "Returns detailed sales statistics for a specific event, "
        "broken down by ticket type with buyer details. "
        "Payment references are only visible to admins."
    ),
)
class EventDetailedStatsView(generics.GenericAPIView):
    """
    GET /admin/events/<id>/detailed-stats/ - Detailed event stats.
    GET /partner/events/<id>/detailed-stats/ - Partner view of same stats.

    Note: Payment references are only included in admin responses.
    Partners see buyer names and quantities but not payment references.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        event_id = kwargs.get("id")

        try:
            event = Event.objects.get(id=event_id)
        except Event.DoesNotExist:
            return _error_response("Event not found.", status.HTTP_404_NOT_FOUND)

        # Check permission for partner
        is_admin = request.user.active_role in [
            "AdAdmin",
            "SuperAdmin",
            "TaskAdmin",
            "MembersAdmin",
            "UserAdmin",
            "PartnersAdmin",
            "ContentAdmin",
            "IntegrationAdmin",
            "WalletAdmin",
        ]
        is_owner = request.user == event.user

        if not is_admin and not is_owner:
            return _error_response(
                "You do not have permission to view these statistics.",
                status.HTTP_403_FORBIDDEN,
            )

        # Get all paid purchases for this event
        purchases = TicketPurchase.objects.filter(
            event=event,
            status=TicketPurchase.Status.PAID,
        ).select_related("ticket", "member", "order")

        # Build breakdown by ticket type
        ticket_breakdown = []
        all_buyers = []

        # Group by ticket type
        ticket_types = Ticket.objects.filter(event=event)

        for ticket in ticket_types:
            ticket_purchases = purchases.filter(ticket=ticket)
            total_quantity = (
                ticket_purchases.aggregate(total=Sum("quantity"))["total"] or 0
            )
            total_revenue = ticket_purchases.aggregate(total=Sum("total_amount"))[
                "total"
            ] or Decimal("0")

            # Get individual buyers for this ticket type
            buyers = []
            for purchase in ticket_purchases:
                buyer_info = {
                    "id": purchase.id,
                    "first_name": purchase.member.first_name,
                    "last_name": purchase.member.last_name,
                    "ticket_name": ticket.name,
                    "quantity": purchase.quantity,
                    "total_amount": str(purchase.total_amount),
                    "purchase_date": purchase.purchased_at,
                }

                # Only include payment reference for admins
                if is_admin:
                    buyer_info["payment_reference"] = purchase.payment_reference or (
                        purchase.order.payment_reference if purchase.order else ""
                    )

                buyers.append(buyer_info)
                all_buyers.append(buyer_info)

            ticket_breakdown.append(
                {
                    "ticket_id": str(ticket.id),
                    "ticket_name": ticket.name,
                    "total_quantity": total_quantity,
                    "total_revenue": str(total_revenue),
                    "buyers": buyers,
                }
            )

        # Calculate overall totals
        total_tickets_sold = purchases.aggregate(total=Sum("quantity"))["total"] or 0
        total_revenue = purchases.aggregate(total=Sum("total_amount"))[
            "total"
        ] or Decimal("0")
        total_buyers = purchases.values("member").distinct().count()

        response_data = {
            "event_id": str(event.id),
            "event_name": event.event_name,
            "total_tickets_sold": total_tickets_sold,
            "total_revenue": str(total_revenue),
            "total_buyers": total_buyers,
            "ticket_breakdown": ticket_breakdown,
            "all_buyers": all_buyers,
        }

        return _success_response(
            "Detailed statistics retrieved successfully.",
            response_data,
        )


@extend_schema(
    summary="Refund a ticket purchase (admin)",
    tags=["Tickets [Admin]"],
    description="Refund a ticket purchase and cancel associated ticket codes.",
)
class AdminRefundPurchaseView(generics.GenericAPIView):
    """POST /admin/purchases/<id>/refund/ - Refund purchase."""

    permission_classes = [IsAuthenticated, IsPartnerAdminOrSuperAdmin]

    def post(self, request, *args, **kwargs):
        purchase_id = kwargs.get("id")

        try:
            purchase = TicketPurchase.objects.select_for_update().get(id=purchase_id)
        except TicketPurchase.DoesNotExist:
            return _error_response("Purchase not found.", status.HTTP_404_NOT_FOUND)

        if purchase.status != TicketPurchase.Status.PAID:
            return _error_response(
                "Only paid purchases can be refunded.",
                status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            purchase.status = TicketPurchase.Status.REFUNDED
            purchase.save(update_fields=["status", "updated_at"])

            # Update partner sale
            if hasattr(purchase, "sale_record"):
                sale = purchase.sale_record
                sale.settlement_status = PartnerTicketSale.SettlementStatus.REFUNDED
                sale.save(update_fields=["settlement_status", "updated_at"])

            # Cancel ticket codes
            TicketCode.objects.filter(purchase=purchase).update(
                is_checked_in=False,
            )

        return _success_response("Purchase refunded successfully.")


# =========================================
#  PARTNER EVENT VERIFICATION VIEWS
# =========================================


def _notify_partner_verification_pending(profile):
    """Notify the partner + all admins that a verification landed in PENDING."""
    UserNotification.objects.create(
        user=profile.user,
        title="Event Partner Verification Received",
        message=(
            "We received your event-partner verification request. "
            "It is currently under review — you will be notified once a "
            "decision is made."
        ),
    )

    admin_message = (
        f"New event-partner verification from {profile.user.full_name} "
        f"({profile.user.email}) requires manual review."
    )
    admins = User.objects.filter(active_role__in=["PartnersAdmin", "SuperAdmin"])
    UserNotification.objects.bulk_create(
        [
            UserNotification(
                user=admin,
                title="Event Partner Verification Pending",
                message=admin_message,
            )
            for admin in admins
        ]
    )


def _notify_partner_verification_approved(profile):
    UserNotification.objects.create(
        user=profile.user,
        title="Event Partner Verification Approved",
        message=(
            "Congratulations! Your event-partner verification has been "
            "approved. You can now create events and sell tickets."
        ),
    )


@extend_schema(
    summary="Submit event-partner verification",
    tags=["Event Partner Verification"],
    description=(
        "Submit NIN and business bank account details to become eligible for "
        "event/ticket creation. NIN is verified via Dojah (with selfie match "
        "against the user's profile image). The business bank account is "
        "verified via 9PSB. If both succeed and the returned bank account "
        "name matches the user's first + last name, the profile is "
        "auto-approved. Otherwise it is parked at PENDING for admin review. "
        "If already approved, resubmission is rejected as a no-op."
    ),
    request=EventPartnerVerificationSubmitSerializer,
)
class EventPartnerVerificationSubmitView(generics.GenericAPIView):
    """
    POST /events/partner/verification/submit/

    Resubmission semantics: if a profile exists (PENDING or REJECTED), the
    same row is overwritten. An APPROVED profile cannot be resubmitted — the
    partner is already eligible.

    Concurrency:
      - Two concurrent requests from the same user are serialized via
        select_for_update() on the existing row (and by the OneToOne
        constraint if no row exists yet).
      - Two concurrent requests with the same NIN are serialized by the
        DB-level unique constraint on `nin`; the loser receives 409.
      - External calls (Dojah / 9PSB) run OUTSIDE the atomic block so the
        row lock is held only for the final write.
    """

    serializer_class = EventPartnerVerificationSubmitSerializer
    permission_classes = [IsAuthenticated, IsPartner]

    def post(self, request, *args, **kwargs):
        decrypted_data = _decrypt_request_data(request)
        if decrypted_data is None:
            return _error_response(
                "Invalid request format.", status.HTTP_400_BAD_REQUEST
            )

        serializer = self.get_serializer(data=decrypted_data)
        error_response = _validate_serializer(serializer)
        if error_response:
            return error_response

        user = request.user
        data = serializer.validated_data

        existing = EventPartnerProfile.objects.filter(user=user).first()
        if existing and existing.is_approved:
            return _error_response(
                "You are already verified as an event partner.",
                status.HTTP_400_BAD_REQUEST,
            )

        nin_taken_by_other = (
            EventPartnerProfile.objects.filter(nin=data["nin"])
            .exclude(user=user)
            .exists()
        )
        if nin_taken_by_other:
            return _error_response(
                "This NIN is already registered to another event partner.",
                status.HTTP_400_BAD_REQUEST,
            )

        #  Step 1: NIN verification via Dojah (outside the lock)
        try:
            selfie_b64 = cloudinary_to_base64(url=user.profile_img_url)
        except Exception:
            logger.exception("Verification failed: could not fetch selfie image.")
            return _error_response(
                "Verification failed. Please update your profile image and try again.",
                status.HTTP_400_BAD_REQUEST,
            )

        try:
            nin_response = KYC.verify_nin(img_file=selfie_b64, nin=data["nin"])
        except Exception:
            logger.exception("Dojah NIN verification call raised.")
            nin_response = None

        if nin_response is None or nin_response.status_code != 200:
            return _error_response(
                "NIN verification service unavailable or NIN is invalid. "
                "Please try again later.",
                status.HTTP_502_BAD_GATEWAY,
            )

        nin_body = nin_response.json() or {}
        entity = nin_body.get("entity") or {}

        img_resp = entity.get("selfie_verification") or {}
        confidence = img_resp.get("confidence_value")
        if (
            img_resp.get("match") is not True
            or not isinstance(confidence, (int, float))
            or confidence < 90
        ):
            return _error_response(
                "NIN verification failed: selfie does not match.",
                status.HTTP_400_BAD_REQUEST,
            )

        verified_dob = entity.get("date_of_birth")
        supplied_dob = data["nin_dob"].isoformat()
        if not verified_dob or str(verified_dob)[:10] != supplied_dob:
            return _error_response(
                "NIN verification failed: date of birth mismatch.",
                status.HTTP_400_BAD_REQUEST,
            )

        nin_name = (
            f"{entity.get('first_name', '')} {entity.get('last_name', '')}"
        ).strip()

        #  Step 2: Bank account verification via 9PSB (outside the lock)
        try:
            bank_response = Transfers.getAccount(
                acct_num=data["bank_account_number"],
                bank_code=data["bank_code"],
            )
        except Exception:
            logger.exception("9PSB bank account lookup raised.")
            bank_response = None

        if bank_response is None or getattr(bank_response, "status_code", 0) != 200:
            return _error_response(
                "Bank account verification service unavailable. "
                "Please try again later.",
                status.HTTP_502_BAD_GATEWAY,
            )

        bank_body = bank_response.json() or {}
        bank_entity = bank_body.get("entity") or bank_body.get("data") or {}
        verified_account_name = (
            bank_entity.get("account_name") or bank_entity.get("accountName") or ""
        )

        if not verified_account_name:
            return _error_response(
                "Bank account could not be verified. Please check the "
                "account number and bank code.",
                status.HTTP_400_BAD_REQUEST,
            )

        expected_name = f"{user.first_name} {user.last_name}".strip()
        names_match = EventPartnerProfile.names_match(
            expected_name, verified_account_name
        )

        #  Step 3: Persist (locked, re-validated)
        try:
            with transaction.atomic():
                locked_existing = (
                    EventPartnerProfile.objects.select_for_update()
                    .filter(user=user)
                    .first()
                )

                if locked_existing and locked_existing.is_approved:
                    return _error_response(
                        "You are already verified as an event partner.",
                        status.HTTP_400_BAD_REQUEST,
                    )

                nin_conflict = (
                    EventPartnerProfile.objects.filter(nin=data["nin"])
                    .exclude(user=user)
                    .exists()
                )
                if nin_conflict:
                    return _error_response(
                        "This NIN is already registered to another event partner.",
                        status.HTTP_400_BAD_REQUEST,
                    )

                profile = locked_existing or EventPartnerProfile(user=user)

                profile.nin = data["nin"]
                profile.nin_dob = supplied_dob
                profile.nin_verified = True
                profile.nin_name = nin_name

                profile.business_name = data["business_name"]
                profile.business_address = data["business_address"]
                profile.tin = data["tin"]

                profile.bank_code = data["bank_code"]
                profile.bank_name = data.get("bank_name", "") or ""
                profile.bank_account_number = data["bank_account_number"]
                profile.bank_account_name = verified_account_name
                profile.bank_verified = True

                if names_match:
                    profile.status = EventPartnerProfile.Status.APPROVED
                    profile.rejection_reason = ""
                    profile.reviewed_by = None
                    profile.reviewed_at = timezone.now()
                else:
                    profile.status = EventPartnerProfile.Status.PENDING
                    profile.rejection_reason = ""
                    profile.reviewed_by = None
                    profile.reviewed_at = None

                profile.save()

        except IntegrityError as exc:
            logger.warning(
                "Event partner verification IntegrityError for user %s: %s",
                user.id,
                exc,
            )
            return _error_response(
                "This verification conflicts with an existing record. "
                "Please refresh and try again.",
                status.HTTP_409_CONFLICT,
            )

        #  Notifications fire OUTSIDE the lock
        if names_match:
            _notify_partner_verification_approved(profile)
            logger.info(
                "Event partner %s auto-approved (name match on bank account).",
                user.id,
            )
            return _success_response(
                "Verification successful. You are now approved to create events.",
                EventPartnerVerificationReadSerializer(profile).data,
                status.HTTP_201_CREATED,
            )

        _notify_partner_verification_pending(profile)
        logger.info(
            "Event partner %s parked at PENDING (name mismatch: "
            "expected=%r, verified=%r).",
            user.id,
            expected_name,
            verified_account_name,
        )
        return _success_response(
            "Verification received. Your bank account name does not match "
            "your profile name, so a manual review is required.",
            EventPartnerVerificationReadSerializer(profile).data,
            status.HTTP_201_CREATED,
        )


@extend_schema(
    summary="Get own event-partner verification status",
    tags=["Event Partner Verification"],
    description="Returns the authenticated partner's own verification record.",
)
class EventPartnerVerificationStatusView(generics.GenericAPIView):
    """GET /events/partner/verification/status/"""

    permission_classes = [IsAuthenticated, IsPartner]

    def get(self, request, *args, **kwargs):
        profile = EventPartnerProfile.objects.filter(user=request.user).first()
        if profile is None:
            return _success_response(
                "No verification record found.",
                {"verified": False, "profile": None},
                status.HTTP_200_OK,
            )

        return _success_response(
            "Verification status retrieved.",
            {
                "verified": profile.is_approved,
                "profile": EventPartnerVerificationReadSerializer(profile).data,
            },
        )


@extend_schema(
    summary="List event-partner verifications (admin)",
    tags=["Event Partner Verification [Admin]"],
    description="Admins list all verification records, filterable by status.",
    parameters=[
        OpenApiParameter(
            name="status",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            description="Filter by status: pending | approved | rejected",
            required=False,
        ),
        OpenApiParameter(
            name="search",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            description="Search by partner email or name",
            required=False,
        ),
    ],
)
class AdminEventPartnerVerificationListView(generics.ListAPIView):
    """GET /events/admin/partner-verifications/"""

    serializer_class = EventPartnerVerificationReadSerializer
    permission_classes = [IsAuthenticated, IsPartnerAdminOrSuperAdmin]
    pagination_class = EventTicketPagination

    def get_queryset(self):
        qs = EventPartnerProfile.objects.select_related("user", "reviewed_by").all()

        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)

        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(
                Q(user__email__icontains=search)
                | Q(user__first_name__icontains=search)
                | Q(user__last_name__icontains=search)
            )

        return qs.order_by("-submitted_at")

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()

        # Manual pagination because the response envelope is custom
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            paginator = self.paginator
            return _success_response(
                "Event-partner verifications retrieved.",
                {
                    "count": paginator.page.paginator.count,
                    "page": paginator.page.number,
                    "page_size": paginator.get_page_size(request),
                    "total_pages": paginator.page.paginator.num_pages,
                    "next": paginator.get_next_link(),
                    "previous": paginator.get_previous_link(),
                    "results": serializer.data,
                },
            )

        # Fallback (pagination disabled via ?page_size=off or misconfig)
        serializer = self.get_serializer(queryset, many=True)
        return _success_response(
            "Event-partner verifications retrieved.",
            {
                "count": queryset.count(),
                "results": serializer.data,
            },
        )


@extend_schema(
    summary="Review an event-partner verification (admin)",
    tags=["Event Partner Verification [Admin]"],
    description=(
        "Approve or reject a PENDING event-partner verification record. "
        "Already-decided records cannot be re-reviewed. The record is "
        "locked for the duration of the check-then-write so two concurrent "
        "admins cannot both pass the PENDING guard."
    ),
    request=EventPartnerVerificationAdminReviewSerializer,
)
class AdminEventPartnerVerificationReviewView(generics.GenericAPIView):
    """POST /events/admin/partner-verifications/<id>/review/"""

    serializer_class = EventPartnerVerificationAdminReviewSerializer
    permission_classes = [IsAuthenticated, IsPartnerAdminOrSuperAdmin]

    def post(self, request, *args, **kwargs):
        profile_id = kwargs.get("id")

        decrypted_data = _decrypt_request_data(request)
        if decrypted_data is None:
            return _error_response(
                "Invalid request format.", status.HTTP_400_BAD_REQUEST
            )

        serializer = self.get_serializer(data=decrypted_data)
        error_response = _validate_serializer(serializer)
        if error_response:
            return error_response

        action = serializer.validated_data["action"]

        with transaction.atomic():
            try:
                profile = (
                    EventPartnerProfile.objects.select_for_update()
                    .select_related("user")
                    .get(id=profile_id)
                )
            except EventPartnerProfile.DoesNotExist:
                return _error_response(
                    "Verification record not found.", status.HTTP_404_NOT_FOUND
                )

            if profile.status != EventPartnerProfile.Status.PENDING:
                return _error_response(
                    "Only PENDING verification records can be reviewed.",
                    status.HTTP_400_BAD_REQUEST,
                )

            if action == "approve":
                profile.status = EventPartnerProfile.Status.APPROVED
                profile.rejection_reason = ""
            else:
                profile.status = EventPartnerProfile.Status.REJECTED
                profile.rejection_reason = serializer.validated_data[
                    "rejection_reason"
                ].strip()

            profile.reviewed_by = request.user
            profile.reviewed_at = timezone.now()
            profile.save(
                update_fields=[
                    "status",
                    "rejection_reason",
                    "reviewed_by",
                    "reviewed_at",
                    "updated_at",
                ]
            )

        if action == "approve":
            _notify_partner_verification_approved(profile)
            message = "Verification approved."
        else:
            UserNotification.objects.create(
                user=profile.user,
                title="Event Partner Verification Rejected",
                message=(
                    f"Your event-partner verification was rejected. "
                    f"Reason: {profile.rejection_reason}"
                ),
            )
            message = "Verification rejected."

        logger.info(
            "Event partner verification %s %sd by admin %s.",
            profile.id,
            action,
            request.user.email,
        )

        return _success_response(
            message,
            EventPartnerVerificationReadSerializer(profile).data,
        )
