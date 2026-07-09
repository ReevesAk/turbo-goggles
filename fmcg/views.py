import logging
import random
import string
import uuid
from commons import Allocate, Biometrics

from django.shortcuts import get_object_or_404
from django.http import Http404
from django.db import transaction
from django.core.cache import cache

from rest_framework.views import APIView
from rest_framework import generics
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.pagination import PageNumberPagination

import rest_framework.serializers as s
from drf_spectacular.utils import extend_schema, OpenApiParameter, inline_serializer
from drf_spectacular.types import OpenApiTypes

from .models import PRODUCT_CATEGORY, COMPANY, Product, Cart, CartItem, FmcgRating, FmcgOrder, PickupAdress
from .serializers import (
    ProductSerializers,
    AddToCartSerializers,
    RemoveFromCartSerializers,
    RetrieveCartProductsSerializers,
    FmcgRatingSerializer,
    FmcgRatingListSerializer,
    FmcgOrderSerializer,
    PickupAddressSerializer
)
from accounts.models import UserNotification, TxModel, Rewards
from banking.helpers import Pin
from roles.models import ActivityModel
from security import encrypt, decrypt
from permissions import IsAuthenticatedOrGuestWithValidId

logger = logging.getLogger(__name__)


class PaginationStyle(PageNumberPagination):
    page_size = 20


def generate_tracking_id(length):
    characters = string.ascii_letters + string.digits  # Letters and digits
    result = "".join(random.choice(characters) for _ in range(length))
    return result


@extend_schema(
    summary="List product categories",
    tags=["FMCG"],
    description="Returns the full list of available FMCG product categories.",
    responses={
        200: inline_serializer(
            name="CategoryListResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "categories": s.ListField(child=s.CharField()),
            },
        ),
    },
)
class CategoryListView(APIView):
    """
    CategoryListView is the GET request handler that returns a list of product categories.
    """
    permission_classes = [IsAuthenticatedOrGuestWithValidId]

    def get(self, request):

        try:
            categories = [category[1] for category in PRODUCT_CATEGORY]
            logger.debug("Categories retrieved: %s", categories)

            return Response(
                data=encrypt({
                    "status": "success",
                    "message": "FMCG Categories retrieved successfully.",
                    "categories": categories,
                }),
                status=status.HTTP_200_OK
            )
        except Exception as e:
            logger.error("Error retrieving categories: %s", str(e))
            return Response(
                data=encrypt({
                    "status": "fail",
                    "message": "An error occurred while retrieving categories.",
                }),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


@extend_schema(
    summary="List FMCG companies",
    tags=["FMCG"],
    description="Returns the full list of FMCG companies available on the platform.",
    responses={
        200: inline_serializer(
            name="CompanyListResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "companies": s.ListField(child=s.CharField()),
            },
        ),
    },
)
class CompanyListView(APIView):
    """
    CompanyListView is the GET request handler that returns a list of fmcg companies.
    """
    permission_classes = [IsAuthenticatedOrGuestWithValidId]

    def get(self, request):

        try:
            companies = [company[1] for company in COMPANY]
            logger.debug("Companies retrieved: %s", companies)

            return Response(
                data=encrypt({
                    "status": "success",
                    "message": "FMCG Companies retrieved successfully.",
                    "companies": companies,
                }),
                status=status.HTTP_200_OK
            )
        except Exception as e:
            logger.error("Error retrieving companies: %s", str(e))
            return Response(
                data=encrypt({
                    "status": "fail",
                    "message": "An error occurred while retrieving companies.",
                }),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


@extend_schema(
    summary="List all FMCG products",
    tags=["FMCG"],
    description="Returns a paginated list of all FMCG products. Optionally filter by category using the query parameter.",
    parameters=[
        OpenApiParameter(
            name="category",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            required=False,
            description="Filter products by category name (case-insensitive).",
        ),
        OpenApiParameter(
            name="page",
            type=OpenApiTypes.INT,
            location=OpenApiParameter.QUERY,
            required=False,
            description="Page number for pagination.",
        ),
    ],
    responses={200: ProductSerializers(many=True)},
)
class ListAllProducts(generics.ListAPIView):

    """
    ListAllProducts is the GET request that handles the retrieval
    of all fmcg products.
    """
    serializer_class = ProductSerializers
    permission_classes = [IsAuthenticatedOrGuestWithValidId]
    pagination_class = PaginationStyle

    def get_queryset(self):
        category = self.request.query_params.get('category', None)
        logger.info("ListAllProducts: GET request received with category: %s", category)

        # If a category is passed, filter the products by category
        if category:
            queryset = Product.objects.filter(category__iexact=category)
            logger.debug("Filtered products by category '%s': %d products found.", category, queryset.count())
            return queryset
        else:
            queryset = Product.objects.all()
            logger.debug("No category filter applied: %d products found.", queryset.count())
            return queryset

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        total_count = queryset.count()
        logger.info("Total products to be returned: %d", total_count)

        user_id = request.user.id
        cache_key = f"user_products:{user_id}"

        cached_products = cache.get(cache_key)
        if cached_products:
            logger.info("Returning cached products for user %s", request.user.email)
            encrypted_response = encrypt(cached_products)
            return Response(data=encrypted_response, status=status.HTTP_200_OK)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            serialized_data = serializer.data  # ✅ Get serialized data safely

            for item, product in zip(serialized_data, page):
                item["image_url"] = product.image_url

            response_data = {
                "status": "success",
                "message": "All FMCG products retrieved successfully.",
                "count": total_count,
                "data": serialized_data,  # ✅ Use updated serialized data
            }
            encrypted_response = encrypt(response_data)  # 🔐 Encrypt response
            return Response(data=encrypted_response, status=status.HTTP_200_OK)

        # If pagination is not used
        serializer = self.get_serializer(queryset, many=True)
        serialized_data = serializer.data

        for item, product in zip(serialized_data, queryset):
            item["image_url"] = product.image_url

        response_data = {
            "status": "success",
            "message": "All FMCG products retrieved successfully.",
            "count": total_count,
            "data": serialized_data,
        }

        # Save to cache (short TTL)
        cache.set(cache_key, response_data, timeout=300)  # 5 minutes

        encrypted_response = encrypt(response_data)  # 🔐 Encrypt response
        return Response(data=encrypted_response, status=status.HTTP_200_OK)


@extend_schema(
    summary="Retrieve a single product",
    tags=["FMCG"],
    description="Fetches the full details of a specific FMCG product by its UUID.",
    responses={
        200: ProductSerializers,
        404: inline_serializer(
            name="ProductNotFoundResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class ProductDetails(generics.RetrieveAPIView):
    """
    ProductDetails is the GET request that handles the retrieval
    of a single fmcg product and it's details.
    """

    serializer_class = ProductSerializers
    permission_classes = [IsAuthenticatedOrGuestWithValidId]
    lookup_field = "id"

    def get_queryset(self):
        return Product.objects.all()

    def get(self, request, *args, **kwargs):
        product_id = kwargs.get(self.lookup_field)
        logger.info("ProductDetails: GET request received for product ID: %s", product_id)

        cache_key = f"product__id:{product_id}"

        cached_products = cache.get(cache_key)
        if cached_products:
            logger.info("Returning cached products for user %s", request.user.email)
            encrypted_response = encrypt(cached_products)
            return Response(data=encrypted_response, status=status.HTTP_200_OK)

        try:
            # Retrieve product by ID
            product = self.get_object()
            serializer = self.get_serializer(product)
            logger.debug("Product details retrieved: %s", serializer.data)

            resp = {
                "status": "success",
                "message": "Product details retrieved successfully.",
                "data": serializer.data
            }

            # Save to cache (short TTL)
            cache.set(cache_key, resp, timeout=300)  # 5 minutes
            return Response(data=encrypt(resp), status=status.HTTP_200_OK)
        except Product.DoesNotExist:
            logger.warning("Product with ID %s not found.", product_id)
            return Response(
                data=encrypt({
                    "status": "fail",
                    "message": "Product not found."
                }),
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error("Error retrieving product with ID %s: %s", product_id, str(e))
            return Response(
                data=encrypt({
                    "status": "fail",
                    "message": "An error occurred while retrieving the product."
                }),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


@extend_schema(
    summary="Add product to cart",
    tags=["FMCG"],
    description="Adds a product to the authenticated user's or guest's cart. If the product is already in the cart, its quantity is incremented.",
    request=AddToCartSerializers,
    responses={
        200: inline_serializer(
            name="AddToCartResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "guest_id": s.CharField(allow_null=True),
                "cart_item": inline_serializer(
                    name="CartItemDetail",
                    fields={
                        "cart_id": s.CharField(),
                        "product": s.CharField(),
                        "quantity": s.IntegerField(),
                        "price": s.CharField(),
                        "total_price": s.CharField(),
                    },
                ),
            },
        ),
        400: inline_serializer(
            name="AddToCartErrorResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class AddToCart(generics.CreateAPIView):
    """
    AddToCart is the POST request handler of adding a product to cart.
    If the product is already in the cart, update the quantity.
    """
    serializer_class = AddToCartSerializers
    permission_classes = [IsAuthenticatedOrGuestWithValidId]

    def get_cart_id(self, user, guest_id):
        """
        Get cart ID for either authenticated user or guest.
        """
        if user.is_authenticated:
            # For authenticated users, we'll use their user ID as cart_id
            return str(user.id)
        else:
            # For guests
            if not guest_id:
                return Response(data=encrypt({
                    "status": "fail",
                    "message": "Guest ID is required for anonymous users.",
                    "cart_items": []
                }), status=status.HTTP_200_OK)

            return str(guest_id)

    def get_cart(self, user, guest_id):
        """
        Get or create a cart for a user or guest.
        """
        cart_id = self.get_cart_id(user, guest_id)
        logger.info("Fetching or creating cart with ID: %s", cart_id)
        cart, _ = Cart.objects.get_or_create(cart_id=cart_id)
        return cart

    def post(self, request, *args, **kwargs):
        user = request.user
        guest_id = request.headers.get('X-Guest-ID')

        try:
            if isinstance(request.data, dict):
                # Already decrypted (likely during testing)
                decrypted_payload = request.data
            else:
                # Normal case - decrypt the payload
                decrypted_payload = decrypt(request.data)
        except Exception as e:
            logger.error("Decryption failed: %s", str(e))
            return Response(
                {"status": "fail", "message": "Invalid payload format"},
                status=status.HTTP_400_BAD_REQUEST
            )

        user_data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_payload.items()
        }

        guest_id = request.headers.get('X-Guest-ID')
        if user:
            logger.info("Received request to add product to cart for user: %s, data: %s", user.id, user_data)
        elif guest_id:
            logger.info("Received request to add product to cart for guest user: %s, data: %s", guest_id, user_data)

        serializer = self.serializer_class(data=user_data)
        if serializer.is_valid(raise_exception=True):
            product_id = kwargs.get("product_id")
            quantity = user_data.get("quantity", 1)

            logger.debug("Fetching product with ID: %s", product_id)
            product = get_object_or_404(Product, id=product_id)

            logger.info("Product found: %s. Retrieving cart for user: %s", product.name_and_size, user.id)
            cart = self.get_cart(user, guest_id)

            logger.debug("Checking if product %s is already in the cart for user: %s", product_id, user.id)
            if user.is_authenticated:
                cart_item, created = CartItem.objects.get_or_create(
                    user=user, 
                    product=product,
                    guest_id=None,  # Explicit None for authenticated users
                    defaults={'quantity': quantity, 'price': product.price}
                )
            else:
                # For guests, user should be None and guest_id should be set
                cart_item, created = CartItem.objects.get_or_create(
                    user=None,  # None for guests
                    product=product,
                    guest_id=guest_id,
                    defaults={'quantity': quantity, 'price': product.price}
                )

            if not created:
                if user:
                    logger.info("Product %s already in cart. Updating quantity for user: %s", product.name_and_size, user.id)
                if isinstance(quantity, str):
                    quantity = int(quantity)

                cart_item.quantity += quantity
                cart_item.save()
            else:
                logger.info("Added new product %s to cart for user: %s", product.name_and_size, user.id)

            if user.is_authenticated:
                ActivityModel.objects.create(
                    user=user,
                    title="Cart Item.",
                    description=f"{user.first_name} {user.last_name} added {product.name_and_size} to cart."
                )
                logger.info("Cart updated successfully for user: %s", user.id)

            resp = {
                "status": "success",
                "message": "Product added to cart.",
                "guest_id": guest_id if not user.is_authenticated else None,
                "cart_item": {
                    "cart_id": cart.cart_id,
                    "product": product.name_and_size,
                    "quantity": cart_item.quantity,
                    "price": str(cart_item.price),
                    "total_price": str(cart_item.get_total_price())
                }
            }
            return Response(data=encrypt(resp), status=status.HTTP_200_OK)
        else:
            logger.error("Validation failed for adding product to cart: %s", serializer.errors)
            return Response(data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    summary="Retrieve cart items",
    tags=["FMCG"],
    description="Returns all items currently in the authenticated user's or guest's cart.",
    responses={
        200: inline_serializer(
            name="RetrieveCartResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "cart_items": s.ListField(
                    child=inline_serializer(
                        name="CartItemEntry",
                        fields={
                            "product_id": s.CharField(),
                            "product": s.CharField(),
                            "quantity": s.IntegerField(),
                            "price_per_unit": s.FloatField(),
                            "image": s.CharField(),
                            "total_price": s.FloatField(),
                        },
                    )
                ),
            },
        ),
    },
)
class RetrieveCartProducts(generics.RetrieveAPIView):
    """
    RetrieveCartProducts is the GET request handler for retrieving all
    items in the user's or guest's cart.
    """
    serializer_class = RetrieveCartProductsSerializers
    permission_classes = [IsAuthenticatedOrGuestWithValidId]

    def get_cart_id(self, user, guest_id):
        """
        Get cart ID for either authenticated user or guest.
        """
        if user.is_authenticated:
            # For authenticated users, we'll use their user ID as cart_id
            return str(user.id)
        else:
            # For guests
            if not guest_id:
                return Response(data=encrypt({
                    "status": "fail",
                    "message": "Guest ID is required for anonymous users.",
                    "cart_items": []
                }), status=status.HTTP_200_OK)

            return str(guest_id)

    def get(self, request, *args, **kwargs):
        user = request.user
        guest_id = request.headers.get('X-Guest-ID')

        cart_id = self.get_cart_id(user=user, guest_id=guest_id)
        logger.info("Fetching cart items for cart_id: %s", cart_id)

        cart = Cart.objects.filter(cart_id=cart_id).first()

        cache_key = f"user_products:{cart_id}"

        cached_cartItems = cache.get(cache_key)
        if cached_cartItems:
            logger.info("Returning cached cart items for user %s", request.user.email)
            encrypted_response = encrypt(cached_cartItems)
            return Response(data=encrypted_response, status=status.HTTP_200_OK)

        if not cart:
            logger.info("No cart found for cart_id: %s", cart_id)
            return Response(data=encrypt({
                "status": "success",
                "message": "Your cart is empty.",
                "cart_items": []
            }), status=status.HTTP_200_OK)

        if user.is_authenticated:
            cart_items = CartItem.objects.filter(user=user)
        else:
            cart_items = CartItem.objects.filter(guest_id=guest_id)

        if not cart_items.exists():
            logger.info("Cart is empty for cart_id: %s", cart_id)
            return Response(data=encrypt({
                "status": "success",
                "message": "Your cart is empty.",
                "cart_items": []
            }), status=status.HTTP_200_OK)

        logger.info("Cart items found. Preparing data.")

        cart_data = []
        for item in cart_items:
            cart_data.append({
                "product_id": str(item.product.id),
                "product": item.product.name_and_size,
                "quantity": item.quantity,
                "price_per_unit": float(item.price),
                "image": item.product.image_url,
                "total_price": float(item.get_total_price())
            })

        logger.info("Cart retrieved successfully.")
        resp = {
            "status": "success",
            "message": "Cart items retrieved successfully.",
            "cart_items": cart_data
        }

        # Save to cache (short TTL)
        cache.set(cache_key, resp, timeout=300)  # 5 minutes

        return Response(data=encrypt(resp), status=status.HTTP_200_OK)


@extend_schema(
    summary="Remove product from cart",
    tags=["FMCG"],
    description="Deletes a specific product from the authenticated user's or guest's cart.",
    responses={
        204: inline_serializer(
            name="RemoveFromCartResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        404: inline_serializer(
            name="RemoveFromCartNotFound",
            fields={"status": s.CharField(), "error": s.CharField()},
        ),
    },
)
class RemoveFromCart(generics.DestroyAPIView):
    """
    RemoveFromCart handles deleting a product from the cart for a user or guest.
    """
    serializer_class = RemoveFromCartSerializers
    permission_classes = [IsAuthenticatedOrGuestWithValidId]

    def get_cart(self, user):
        """
        Get or create a cart for the user.
        """
        cart, created = Cart.objects.get_or_create(
            cart_id=f"cart_{user.id}",  # Generates a unique cart_id
        )
        return cart

    def delete(self, request, *args, **kwargs):
        user = request.user
        product_id = kwargs.get("product_id")
        guest_id = request.headers.get('X-Guest-ID')

        cart_id = self.get_cart_id(user, guest_id)

        logger.info("Attempting to remove product ID %s from cart: %s", product_id, cart_id)

        try:
            # Fetch the product and cart item
            product = get_object_or_404(Product, id=product_id)
            cart_item = get_object_or_404(CartItem, user=user, product=product)
            logger.info("Product %s found in cart for user: %s", product.name_and_size, user.id)

        except Http404:
            logger.error("Cart item not found for cart: %s", cart_id)
            return Response(
                encrypt({
                    "status": "fail",
                    "error": "Product or cart item not found."
                }),
                status=status.HTTP_404_NOT_FOUND
            )

        cart_item.delete()
        logger.info("Removed product %s from cart: %s", product.name_and_size, cart_id)

        if user:
            ActivityModel.objects.create(
                user=user,
                title="Cart Item Removed",
                description=f"{user.full_name or user.phone_number} removed {product.name_and_size} from cart."
            )
        elif guest_id:
            ActivityModel.objects.create(
                user=guest_id,
                title="Cart Item Removed",
                description=f"Guest user: {guest_id} removed {product.name_and_size} from cart."
            )

        return Response(
            encrypt({
                "status": "success",
                "message": "Product removed from cart."
            }),
            status=status.HTTP_204_NO_CONTENT
        )


@extend_schema(
    summary="Checkout FMCG order",
    tags=["FMCG"],
    description="Places an FMCG order for the authenticated user, processing payment via wallet or card and allocating rewards points on success.",
    request=FmcgOrderSerializer,
    responses={
        200: inline_serializer(
            name="FmcgCheckoutSuccessResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "order": FmcgOrderSerializer(),
            },
        ),
        400: inline_serializer(
            name="FmcgCheckoutErrorResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        401: inline_serializer(
            name="FmcgCheckoutUnauthorizedResponse",
            fields={"status": s.CharField(), "error": s.CharField()},
        ),
        404: inline_serializer(
            name="FmcgCheckoutNotFoundResponse",
            fields={"status": s.CharField(), "error": s.CharField()},
        ),
    },
)
class FmcgCheckout(generics.CreateAPIView):
    serializer_class = FmcgOrderSerializer
    permission_classes = [IsAuthenticatedOrGuestWithValidId]

    def post(self, request, *args, **kwargs):
        payload = {key: value.strip() if isinstance(value, str) else value for key, value in request.data.items()}
        serializer = self.get_serializer(data=payload)

        if not serializer.is_valid(raise_exception=True):
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # Identify user (authenticated or guest)
        if request.user and request.user.is_authenticated:
            user = request.user
        else:
            guest_id = request.headers.get('X-Guest-ID')
            if not guest_id:
                return Response(
                    data=encrypt({"status": "fail", "message": "Guest ID is required for unauthenticated users."}),
                    status=status.HTTP_400_BAD_REQUEST
                )

        tracking_id = generate_tracking_id(10)
        tx_reference = uuid.uuid4()
        amount = 0
        products_data = payload["products"]

        logger.info("Processing order creation for user: %s", user.id)

        order_items = []
        for item in products_data:
            product = get_object_or_404(Product, id=item["product_id"])
            quantity = item["quantity"]
            total_price_for_product = product.price * quantity
            amount += total_price_for_product

            order_items.append({
                "product": product,
                "quantity": quantity,
                "total_price": total_price_for_product
            })
            logger.info("Added product %s with quantity %s to the order for user: %s", product.name_and_size, quantity, user.id)

        order = FmcgOrder.objects.create(
            user=user,
            total_price=amount,
            billing_address=payload["billing_address"],
            delivery_address=payload.get("delivery_address", ""),
            status="Pending",
            tracking_id=tracking_id,
            tx_reference=tx_reference
        )
        logger.info("Order created with tracking_id: %s for user: %s", tracking_id, user.id)

        pin = payload.get("pin")
        biometrics = payload.get("use_biometrics")

        try:
            account = AccountCreation.objects.get(user=user)
        except AccountCreation.DoesNotExist:
            logger.error("Account not found for user: %s", user.id)
            return Response(
                data=encrypt({"status": "fail", "error": "Account not found for user"}),
                status=status.HTTP_404_NOT_FOUND,
            )

        if biometrics:
            verification = Biometrics.authenticate(user.phone_number)
            logger.info("Biometrics authentication attempted for user: %s", user.id)
        else:
            if account and account.pin is not None:
                verification = Pin.verify(user=user, pin=pin, hashed_pin=account.pin)
            else:
                logger.error("PIN not found for user: %s", user.id)
                return Response(
                    data=encrypt({"status": "fail", "error": "Account or PIN not found for user"}),
                    status=status.HTTP_404_NOT_FOUND,
                )

        if not verification:
            logger.error("Invalid credentials for user: %s", user.id)
            return Response(
                data=encrypt({"status": "fail", "error": "Invalid credentials"}),
                status=status.HTTP_401_UNAUTHORIZED,
            )

        payment_option = payload["payment_method"]
        logger.info("Processing payment using method: %s for user: %s", payment_option, user.id)

        match payment_option:
            case "WALLET":
                debit_response = Account.Debit(
                    debitAccount=account.account_number,
                    amount=float(amount),
                    reason="Payment of FMCG products",
                    transactionReference=str(tx_reference)
                )
                if debit_response.status_code == 200:
                    logger.info("Wallet payment successful for user: %s", user.id)
                    order.status = "Completed"
                    order.save()

                    UserNotification.objects.create(
                        user=user,
                        title="Payment Successful",
                        message=f"You have successfully paid {amount} for your order."
                    )

                    ActivityModel.objects.create(
                        user=user,
                        title="Payment Successful",
                        description=f"{user.first_name} {user.last_name} paid {amount} for their order."
                    )

                    if user.active_role == "Member" and amount >= 100:
                        new_rewards = Allocate.reward(amount=amount)
                    else:
                        new_rewards = 0

                    try:
                        with transaction.atomic():
                            TxModel.objects.create(
                                user=user,
                                tx_id="",
                                tx_reference="",
                                tx_type="FMCG",
                                amount=amount,
                                description="Debit for FMCG purchase.",
                                rwd=new_rewards,
                            )

                            rwd, _ = Rewards.objects.get_or_create(user=user)
                            rwd.balance += new_rewards
                            rwd.save()

                    except Exception as e:
                        logger.error("Error during rewards allocation for user: %s - %s", user.id, str(e))

                    response_data = serializer.data
                    response_data["total_price"] = str(amount)
                    response_data.pop("pin", None)

                    return Response(
                        data=encrypt({
                            "status": "success",
                            "message": f"Payment of {amount} completed.",
                            "order": response_data
                        }),
                        status=status.HTTP_200_OK)

                else:
                    logger.error("Wallet payment failed for user: %s", user.id)
                    order.status = "Failed"
                    order.save()
                    return Response(
                        data=encrypt({
                            "status": "fail",
                            "message": "Payment failed.",
                            "error": debit_response.json()
                        }),
                        status=status.HTTP_400_BAD_REQUEST)

            case "CARD":
                # Card payment logic here
                order.status = "Completed"
                order.save()
                # Notifications, rewards, and response...

            case _:
                logger.warning("Invalid payment method provided by user: %s", user.id)
                return Response(
                    data=encrypt({"status": "fail", "message": "Invalid payment method"}),
                    status=status.HTTP_400_BAD_REQUEST
                )


@extend_schema(
    summary="Rate an FMCG product",
    tags=["FMCG"],
    description="Allows a user to submit a star rating and review for an FMCG product they have purchased. Each user may only rate a given product once.",
    request=FmcgRatingSerializer,
    responses={
        201: inline_serializer(
            name="FmcgRatingSuccessResponse",
            fields={"success": s.CharField()},
        ),
        400: inline_serializer(
            name="FmcgRatingErrorResponse",
            fields={"error": s.CharField()},
        ),
        403: inline_serializer(
            name="FmcgRatingForbiddenResponse",
            fields={"status": s.CharField(), "error": s.CharField()},
        ),
        404: inline_serializer(
            name="FmcgRatingNotFoundResponse",
            fields={"error": s.CharField()},
        ),
    },
)
class FmcgRatingView(generics.GenericAPIView):
    """
    FmcgRatingView is the POST request that allows a customer to rate a
    products purchased on fmcg.

    `rating`: This comes in numbers 1-5 depending on the quality of the product purchased.\n
    `review`: The review is a written appraisal of the product consumed.
    """

    serializer_class = FmcgRatingSerializer
    permission_classes = [IsAuthenticatedOrGuestWithValidId]

    def post(self, request, *args, **kwargs):
        product_id = kwargs.get("id")
        if not product_id:
            return Response(
                data=encrypt({"error": "Product ID is required."}),
                status=status.HTTP_400_BAD_REQUEST
            )

        decrypted_data = decrypt(request.data)
        payload = {key: value.strip() if isinstance(value, str) else value for key, value in decrypted_data.items()}
        serializer = self.get_serializer(data=payload)

        if serializer.is_valid(raise_exception=True):
            user = request.user

            try:
                product = Product.objects.get(id=product_id)

                # Check purchase and rating status in one query
                has_purchased = FmcgOrder.objects.filter(
                    user=user,
                    product=product.name_and_size,
                    status=FmcgOrder.Status.COMPLETED
                ).exists()

                if not has_purchased:
                    return Response(
                        data=encrypt({"status": "fail", "error": "You can only rate products you have purchased."}),
                        status=status.HTTP_403_FORBIDDEN
                    )

                # Check if the user has already rated the product
                if FmcgRating.objects.filter(product=product, user=user).exists():
                    return Response(
                        data=encrypt({"error": "You have already rated this product."}),
                        status=status.HTTP_400_BAD_REQUEST
                    )

                # Save the rating
                serializer.save(product=product, user=user)

                # Notify user and log activity
                UserNotification.objects.create(
                    user=user,
                    title="FMCG Product Rating",
                    message="Product rated successfully!"
                )
                ActivityModel.objects.create(
                    user=user,
                    title="FMCG Product Rating",
                    description=f"{user.first_name} {user.last_name} rated an FMCG product."
                )

                return Response(
                    data=encrypt({"success": "Product rating added successfully."}),
                    status=status.HTTP_201_CREATED
                )

            except Product.DoesNotExist:
                return Response(
                    data=encrypt({"error": "This product does not exist in the store."}),
                    status=status.HTTP_404_NOT_FOUND
                )
        else:
            return Response(data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    summary="List reviews for a product",
    tags=["FMCG"],
    description="Returns a paginated list of all user ratings and reviews for the specified product.",
    responses={200: FmcgRatingListSerializer(many=True)},
)
class GetFmcgReview(generics.ListAPIView):
    """
    GetFmcgReview is the GET request handler that retrieves all the reviews on a product.
    """

    serializer_class = FmcgRatingListSerializer
    permission_classes = [IsAuthenticatedOrGuestWithValidId]
    pagination_class = PaginationStyle

    def get_queryset(self):
        product_id = self.kwargs.get('product_id')
        queryset = FmcgRating.objects.filter(product=product_id)
        return queryset

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.serializer_class(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.serializer_class(queryset, many=True)
        return Response(data=encrypt(serializer.data), status=status.HTTP_200_OK)


@extend_schema(
    summary="List pick-up addresses",
    tags=["FMCG"],
    description="Returns all available store pick-up addresses that customers can choose during FMCG checkout.",
    responses={200: PickupAddressSerializer(many=True)},
)
class PickupAddressListView(generics.ListAPIView):
    serializer_class = PickupAddressSerializer
    permission_classes = [IsAuthenticatedOrGuestWithValidId]
    queryset = PickupAdress.objects.all()

    def get(self, request, *args, **kwargs):
        addresses = self.get_queryset()
        serializer = self.get_serializer(addresses, many=True)
        data = {
            "status": "success",
            "message": "Pick-up addresses fetched succesfully.",
            "data": serializer.data
        }
        return Response(data=encrypt(data), status=status.HTTP_200_OK)
