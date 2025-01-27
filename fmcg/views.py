import logging
import random
import string
import uuid
from commons import Allocate, Biometrics

from django.shortcuts import get_object_or_404
from django.http import Http404
from django.db import transaction

from rest_framework.views import APIView
from rest_framework import generics
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.pagination import PageNumberPagination

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
from banking.controllers import Account
from banking.models import AccountCreation
from banking.helpers import Pin
from roles.models import ActivityModel
from security import encrypt, decrypt

logger = logging.getLogger(__name__)


class PaginationStyle(PageNumberPagination):
    page_size = 20


def generate_tracking_id(length):
    characters = string.ascii_letters + string.digits  # Letters and digits
    result = "".join(random.choice(characters) for _ in range(length))
    return result


class CategoryListView(APIView):
    """
    CategoryListView is the GET request handler that returns a list of product categories.
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

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


class CompanyListView(APIView):
    """
    CompanyListView is the GET request handler that returns a list of fmcg companies.
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

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


class ListAllProducts(generics.ListAPIView):

    """
    ListAllProducts is the GET request that handles the retrieval
    of all fmcg products.
    """
    serializer_class = ProductSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
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

        page = self.paginate_queryset(queryset)
        for query in queryset:
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                response_data = {
                    "status": "success",
                    "message": "All FMCG products retrieved successfully.",
                    "count": total_count,
                    "product_images": query.image_url,
                    "data": serializer.data,
                }
                # Encrypt the entire response data
                encrypted_response = encrypt(response_data)
                return Response(data=encrypted_response, status=status.HTTP_200_OK)

        # If pagination is not used
        serializer = self.get_serializer(queryset, many=True)
        for query in queryset:
            resp = {
                "status": "success",
                "message": "All FMCG products retrieved successfully.",
                "count": total_count,
                "product_images": query.image_url,
                "data": serializer.data
            }
            # Encrypt the entire response data
            encrypted_response = encrypt(resp)
            return Response(data=encrypted_response, status=status.HTTP_200_OK)


class ProductDetails(generics.RetrieveAPIView):
    """
    ProductDetails is the GET request that handles the retrieval
    of a single fmcg product and it's details.
    """

    serializer_class = ProductSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    lookup_field = "id"

    def get_queryset(self):
        return Product.objects.all()

    def get(self, request, *args, **kwargs):
        product_id = kwargs.get(self.lookup_field)
        logger.info("ProductDetails: GET request received for product ID: %s", product_id)

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

            return Response(data=encrypt(resp), status=status.HTTP_200_OK)
        except Product.DoesNotExist:
            logger.warning("Product with ID %s not found.", product_id)
            return Response(
                data=encrypt({
                    "status": "error",
                    "message": "Product not found."
                }),
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error("Error retrieving product with ID %s: %s", product_id, str(e))
            return Response(
                data=encrypt({
                    "status": "error",
                    "message": "An error occurred while retrieving the product."
                }),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class AddToCart(generics.CreateAPIView):
    """
    AddToCart is the POST request handler of adding a product to cart.
    If the product is already in the cart, update the quantity.
    """
    serializer_class = AddToCartSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get_cart(self, user):
        """
        Get or create a cart for the user.
        """
        logger.info("Fetching or creating a cart for user: %s", user.id)
        cart, _ = Cart.objects.get_or_create(
            cart_id=f"cart_{user.id}",  # Generates a unique cart_id
        )
        return cart

    def post(self, request, *args, **kwargs):
        user = request.user
        decrypted_payload = decrypt(request.data)
        user_data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_payload.items()
        }

        logger.info("Received request to add product to cart for user: %s, data: %s", user.id, user_data)

        serializer = self.serializer_class(data=user_data)
        if serializer.is_valid(raise_exception=True):
            product_id = kwargs.get("product_id")
            quantity = user_data.get("quantity", 1)

            logger.debug("Fetching product with ID: %s", product_id)
            product = get_object_or_404(Product, id=product_id)

            logger.info("Product found: %s. Retrieving cart for user: %s", product.name_and_size, user.id)
            cart = self.get_cart(user)

            logger.debug("Checking if product %s is already in the cart for user: %s", product_id, user.id)
            cart_item, created = CartItem.objects.get_or_create(
                user=user, product=product,
                defaults={'quantity': quantity, 'price': product.price}
            )

            if not created:
                logger.info("Product %s already in cart. Updating quantity for user: %s", product.name_and_size, user.id)
                cart_item.quantity += quantity
                cart_item.save()
            else:
                logger.info("Added new product %s to cart for user: %s", product.name_and_size, user.id)

            ActivityModel.objects.create(
                user=user,
                title="Cart Item.",
                description=f"{user.first_name} {user.last_name} added {product.name_and_size} to cart."
            )

            logger.info("Cart updated successfully for user: %s", user.id)
            resp = {
                "status": "success",
                "message": "Product added to cart.",
                "cart_item": {
                    "cart_id": cart.cart_id,
                    "product": product.name_and_size,
                    "quantity": cart_item.quantity,
                    "price": cart_item.price,
                    "total_price": cart_item.get_total_price()
                }
            }
            return Response(data=encrypt(resp), status=status.HTTP_200_OK)
        else:
            logger.error("Validation failed for adding product to cart: %s", serializer.errors)
            return Response(data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST)


class RetrieveCartProducts(generics.RetrieveAPIView):
    """
    RetrieveCartProducts is the GET request handler for retrieving all
    items in the user's cart.
    """

    serializer_class = RetrieveCartProductsSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = request.user
        logger.info("Fetching cart items for user: %s", user.id)

        cart_items = CartItem.objects.filter(user=user)

        if not cart_items.exists():
            logger.info("Cart is empty for user: %s", user.id)
            resp = {
                "status": "success",
                "message": "Your cart is empty.",
                "cart_items": []
            }
            return Response(data=encrypt(resp), status=status.HTTP_200_OK)

        logger.info("Cart items found for user: %s. Preparing data.", user.id)

        # Prepare cart item data
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
            logger.debug(
                "Cart item for product: %s added to response data for user: %s",
                item.product.name_and_size,
                user.id
            )

        logger.info("Successfully retrieved and prepared cart data for user: %s", user.id)
        response = {
            "status": "success",
            "message": "Cart items retrieved successfully.",
            "cart_items": cart_data
        }
        return Response(data=encrypt(response), status=status.HTTP_200_OK)


class RemoveFromCart(generics.DestroyAPIView):
    """
    RemoveFromCart is the DELETE request handler that removes a product from the cart.
    """

    serializer_class = RemoveFromCartSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

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

        logger.info("Attempting to remove product with ID %s from the cart for user: %s", product_id, user.id)

        try:
            # Fetch the product and cart item
            product = get_object_or_404(Product, id=product_id)
            cart_item = get_object_or_404(CartItem, user=user, product=product)
            logger.info("Product %s found in cart for user: %s", product.name_and_size, user.id)

        except Http404:
            logger.error("Product or cart item not found for user: %s", user.id)
            response = {
                "status": "fail",
                "error": "Product or cart item not found."
            }
            return Response(
                data=encrypt(response),
                status=status.HTTP_404_NOT_FOUND
            )

        # Delete the cart item
        cart_item.delete()
        logger.info("Product %s removed from cart for user: %s", product.name_and_size, user.id)

        # Log activity
        ActivityModel.objects.create(
            user=user,
            title="Cart Item.",
            description=f"{user.first_name} {user.last_name} removed {product.name_and_size} from cart."
        )

        logger.info("Activity logged for user: %s regarding removal of product: %s", user.id, product.name_and_size)

        return Response(
            encrypt(data={
                "status": "success",
                "message": "Product removed from cart."
            }), status=status.HTTP_204_NO_CONTENT)


class FmcgCheckout(generics.CreateAPIView):
    serializer_class = FmcgOrderSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        payload = {key: value.strip() if isinstance(value, str) else value for key, value in request.data.items()}
        serializer = self.get_serializer(data=payload)

        if not serializer.is_valid(raise_exception=True):
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        authenticated_user = request.user
        tracking_id = generate_tracking_id(10)
        tx_reference = uuid.uuid4()
        amount = 0
        products_data = payload["products"]

        logger.info("Processing order creation for user: %s", authenticated_user.id)

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
            logger.info("Added product %s with quantity %s to the order for user: %s", product.name_and_size, quantity, authenticated_user.id)

        # Create the order
        order = FmcgOrder.objects.create(
            user=authenticated_user,
            total_price=amount,
            billing_address=payload["billing_address"],
            delivery_address=payload.get("delivery_address", ""),
            status="Pending",
            tracking_id=tracking_id,
            tx_reference=tx_reference
        )
        logger.info("Order created with tracking_id: %s for user: %s", tracking_id, authenticated_user.id)

        # Verify PIN or biometrics
        pin = payload["pin"]
        biometrics = payload.get("use_biometrics")

        try:
            account = AccountCreation.objects.get(user=authenticated_user)
        except AccountCreation.DoesNotExist:
            logger.error("Account not found for user: %s", authenticated_user.id)
            return Response(
                data=encrypt({"status": "fail", "error": "Account not found for user"}),
                status=status.HTTP_404_NOT_FOUND,
            )

        if biometrics:
            verification = Biometrics.authenticate(authenticated_user.phone_number)
            logger.info("Biometrics authentication attempted for user: %s", authenticated_user.id)
        else:
            if account and account.pin is not None:
                verification = Pin.verify(user=authenticated_user, pin=pin, hashed_pin=account.pin)
            else:
                logger.error("PIN not found for user: %s", authenticated_user.id)
                return Response(
                    data=encrypt({"status": "fail", "error": "Account or PIN not found for user"}),
                    status=status.HTTP_404_NOT_FOUND,
                )

        if not verification:
            logger.error("Invalid credentials for user: %s", authenticated_user.id)
            return Response(
                data=encrypt({"status": "fail", "error": "Invalid credentials"}),
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # Handle payment
        payment_option = payload["payment_method"]
        logger.info("Processing payment using method: %s for user: %s", payment_option, authenticated_user.id)

        match payment_option:
            case "WALLET":
                debit_response = Account.Debit(
                    debitAccount=account.account_number,
                    amount=float(amount),
                    reason="Payment of FMCG products",
                    transactionReference=str(tx_reference)
                )
                if debit_response.status_code == 200:
                    logger.info("Wallet payment successful for user: %s", authenticated_user.id)
                    order.status = "Completed"
                    order.save()

                    UserNotification.objects.create(
                        user=authenticated_user,
                        title="Payment Successful",
                        message=f"You have successfully paid {amount} for your order."
                    )
                    logger.info("Notification sent for successful payment for user: %s", authenticated_user.id)

                    ActivityModel.objects.create(
                        user=authenticated_user,
                        title="Payment Successful",
                        description=f"{authenticated_user.first_name} {authenticated_user.last_name} paid {amount} for their order."
                    )

                    # Rewards allocation
                    if authenticated_user.active_role == "Member" and amount >= 100:
                        new_rewards = Allocate.reward(amount=amount)
                    else:
                        new_rewards = 0

                    try:
                        with transaction.atomic():
                            TxModel.objects.create(
                                user=authenticated_user,
                                tx_id="",
                                tx_reference="",
                                tx_type="FMCG",
                                amount=amount,
                                description="Debit for FMCG purchase.",
                                rwd=new_rewards,
                            )

                            rwd, _ = Rewards.objects.get_or_create(user=authenticated_user)
                            rwd.balance += new_rewards
                            rwd.save()
                            logger.info("Rewards allocated: %s for user: %s", new_rewards, authenticated_user.id)

                    except Exception as e:
                        logger.error("Error during rewards allocation for user: %s - %s", authenticated_user.id, str(e))

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
                    logger.error("Wallet payment failed for user: %s", authenticated_user.id)
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
                # Similar handling for CARD payment
                logger.info("Card payment processing for user: %s", authenticated_user.id)
                order.status = "Completed"
                order.save()
                # Notifications, rewards, and response as above

            case _:
                logger.warning("Invalid payment method provided by user: %s", authenticated_user.id)
                return Response(data=encrypt({"status": "fail", "message": "Invalid payment method"}), status=status.HTTP_400_BAD_REQUEST)


class FmcgRatingView(generics.GenericAPIView):
    """
    FmcgRatingView is the POST request that allows a customer to rate a
    products purchased on fmcg.

    `rating`: This comes in numbers 1-5 depending on the quality of the product purchased.\n
    `review`: The review is a written appraisal of the product consumed.
    """

    serializer_class = FmcgRatingSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

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


class GetFmcgReview(generics.ListAPIView):
    """
    GetFmcgReview is the GET request handler that retrieves all the reviews on a product.
    """

    serializer_class = FmcgRatingListSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
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


class PickupAddressListView(generics.ListAPIView):
    serializer_class = PickupAddressSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
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
