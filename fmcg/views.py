import random
import string

from django.shortcuts import get_object_or_404

from rest_framework.views import APIView
from rest_framework import generics
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.pagination import PageNumberPagination

from .models import PRODUCT_CATEGORY, COMPANY, Product, Cart, CartItem, FmcgRating, FmcgOrder
from .serializers import (
    ProductSerializers,
    AddToCartSerializers,
    RemoveFromCartSerializers,
    RetrieveCartProductsSerializers,
    FmcgRatingSerializer,
    FmcgRatingListSerializer,
    FmcgOrderSerializer
)
from accounts.models import UserNotification
from banking.controllers import Account
from banking.models import AccountCreation
from banking.helpers import Pin
from roles.models import ActivityModel


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
        categories = [category[1] for category in PRODUCT_CATEGORY]
        return Response(
            data={
                "status": "success.",
                "message": "FMCG Categories retrieved successfully.",
                "categories": categories,
            },
            status=status.HTTP_200_OK)


class CompanyListView(APIView):
    """
    CompanyListView is the GET request handler that returns a list of fmcg companies.
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        companies = [company[1] for company in COMPANY]
        return Response(
            data={
                "status": "success.",
                "message": "FMCG Companies retrieved successfully.",
                "categories": companies,
            },
            status=status.HTTP_200_OK)


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

        # If a category is passed, filter the products by category
        if category:
            return Product.objects.filter(category__iexact=category)
        else:
            return Product.objects.all()

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        total_count = queryset.count()

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response({
                "status": "success",
                "message": "All Fmcg products retrieved successfully.",
                "count": total_count,
                "data": serializer.data
            })

        serializer = self.get_serializer(queryset, many=True)
        return Response({
            "status": "success",
            "message": "All Fmcg products retrieved successfully.",
            "count": total_count,
            "data": serializer.data
        }, status=status.HTTP_200_OK)


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
        try:
            # Retrieve product by UUID
            product = self.get_object()
            serializer = self.get_serializer(product)
            return Response({
                "status": "success",
                "message": "Product details retrieved successfully.",
                "data": serializer.data
            }, status=status.HTTP_200_OK)
        except Product.DoesNotExist:
            return Response(
                data={
                    "status": "error",
                    "message": "Product not found."
                },
                status=status.HTTP_404_NOT_FOUND
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
        cart, _ = Cart.objects.get_or_create(
            cart_id=f"cart_{user.id}",  # Generates a unique cart_id
        )
        return cart

    def post(self, request, *args, **kwargs):
        user = request.user
        user_data = {key: value.strip() if isinstance(value, str) else value for key, value in request.data.items()}

        serializer = self.serializer_class(data=user_data)
        if serializer.is_valid(raise_exception=True):
            product_id = kwargs.get("product_id")
            quantity = request.data.get("quantity", 1)

            product = get_object_or_404(Product, id=product_id)

            cart = self.get_cart(user)

            # Check if the product is already in the user's cart
            cart_item, created = CartItem.objects.get_or_create(
                user=user, product=product,
                defaults={'quantity': quantity, 'price': product.price}
            )

            if not created:
                # If the product is already in the cart, update the quantity
                cart_item.quantity += quantity
                cart_item.save()

                ActivityModel.objects.create(
                    user=user,
                    title="Cart Item.",
                    description=f"{user.first_name} {user.last_name} added {product.name_and_size} to cart."
                )

            return Response({
                "status": "success",
                "message": "Product added to cart.",
                "cart_item": {
                    "cart_id": cart.cart_id,
                    "product": product.name_and_size,
                    "quantity": cart_item.quantity,
                    "price": cart_item.price,
                    "total_price": cart_item.get_total_price()
                }
            }, status=status.HTTP_200_OK)
        else:
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)


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
        cart_items = CartItem.objects.filter(user=user)

        if not cart_items.exists():
            return Response({
                "status": "success",
                "message": "Your cart is empty.",
                "data": []
            }, status=status.HTTP_200_OK)

        # Prepare cart item data
        cart_data = []
        for item in cart_items:
            cart_data.append({
                "product": item.product.name_and_size,
                "quantity": item.quantity,
                "price_per_unit": item.price,
                "total_price": item.get_total_price()
            })

        return Response({
            "status": "success",
            "message": "Cart items retrieved successfully.",
            "cart_items": cart_data
        }, status=status.HTTP_200_OK)


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
        product_id = kwargs("product_id")

        # Fetch the product and cart item
        product = get_object_or_404(Product, id=product_id)
        cart_item = get_object_or_404(CartItem, user=user, product=product)

        cart_item.delete()

        ActivityModel.objects.create(
            user=user,
            title="Cart Item.",
            description=f"{user.first_name} {user.last_name} removed {product.name_and_size} from cart."
        )

        return Response({
            "status": "success",
            "message": "Product removed from cart."
        }, status=status.HTTP_204_NO_CONTENT)


class FmcgCheckout(generics.CreateAPIView):
    """
    FmcgCheckout is the POST request handler for finalizing an order from the cart.
    This will handle payment and creating an order.
    """
    serializer_class = FmcgOrderSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        payload = {key: value.strip() if isinstance(value, str) else value for key, value in request.data.items()}
        serializer = self.get_serializer(data=payload)
        if serializer.is_valid(raise_exception=True):
            tracking_id = generate_tracking_id(10)
            authenticated_user = request.user
            amount = payload["total_price"]
            product = payload["product"]
            order = FmcgOrder.objects.create(
                user=authenticated_user,
                product=product,
                price=amount,
                billing_address=payload["billing_address"],
                available_addresses=payload["available_addresses"],
                delivery_address=payload["delivery_address"],
                status="Pending",
                tracking_id=tracking_id
            )

            # Proceed to checkout and pay for the product.
            pin = payload["pin"]
            user_details = AccountCreation.objects.get(user=authenticated_user)
            verification = Pin.verify_pin(user=authenticated_user, pin=pin)
            if verification:
                debit_response = Account.Debit(
                    debitAccount=user_details.account_number,
                    amount=amount,
                    reason="Payment of fmcg product.",
                    transactionReference=""
                )
                if debit_response.status_code == 200:
                    order.status = "Completed"
                    order.save()

                    UserNotification.objects.create(
                        user=authenticated_user,
                        title="Payment Successful.",
                        message=f"You have successfully paid {amount} for the purchase of {product.name_and_size}."
                    )

                    ActivityModel.objects.create(
                        user=authenticated_user,
                        title="Payment Successful.",
                        description=f"{authenticated_user.first_name} {authenticated_user.last_name} has successfully paid {amount} for the purchase of {product.name_and_size}."
                    )
                    resp = {
                        "status": "success.",
                        "message": f"You have successfully paid {amount} for the purchase of {product.name_and_size}.",
                        "data": serializer.data
                    }
                    return Response(data=resp, status=status.HTTP_200_OK)
                else:
                    order.status = "Failed"
                    order.save()
                    UserNotification.objects.create(
                        user=authenticated_user,
                        title="Payment failed.",
                        message=f"Payment of {amount} for the purchase of {product} failed."
                    )
                    error_resp = {
                        "status": "fail",
                        "message": f"You have successfully paid {amount} for the purchase of {product}.",
                        "data": debit_response.json()
                    }
                    return Response(data=error_resp, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)


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
        payload = {key: value.strip() if isinstance(value, str) else value for key, value in request.data.items()}
        serializer = self.get_serializer(data=payload)
        if serializer.is_valid(raise_exception=True):
            user = request.user
            product_id = kwargs.get("id")

            try:
                product = Product.objects.get(id=product_id)

                # Check if the user has purchased the product
                has_purchased = FmcgOrder.objects.filter(
                    user=user,
                    product=product.name_and_size,
                    status=FmcgOrder.Status.COMPLETED  # Check only completed orders
                ).exists()

                if not has_purchased:
                    return Response(
                        data={"status": "fail", "error": "You can only rate products you have purchased."},
                        status=status.HTTP_403_FORBIDDEN
                    )

                # Check if the user has already rated the product
                existing_rating = FmcgRating.objects.filter(product=product, user=user).first()
                if existing_rating:
                    return Response(
                        data={"error": "You have already rated this product."},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                # Save the rating linked to the product
                serializer.save(product=product, user=user)

                UserNotification.objects.create(
                    user=user,
                    title="FMCG Product Rating.",
                    message="Product rated successfully!.",
                )

                ActivityModel.objects.create(
                    user=user,
                    title="FMCG Product Rating.",
                    description=f"{user.first_name} {user.last_name} has rated an FMCG product."
                )

                return Response(
                    {"success": "Product rating added successfully."},
                    status=status.HTTP_201_CREATED,
                )

            except Product.DoesNotExist:
                return Response(
                    data={"error": "This product does not exist in the store."},
                    status=status.HTTP_404_NOT_FOUND
                )
        else:
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)


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
        return Response(serializer.data, status=status.HTTP_200_OK)
