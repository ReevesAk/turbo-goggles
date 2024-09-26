from django.shortcuts import get_object_or_404

from rest_framework.views import APIView
from rest_framework import generics
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, JSONParser
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.pagination import PageNumberPagination

from .models import PRODUCT_CATEGORY, COMPANY, Product, Cart, CartItem
from .serializers import ProductSerializers, AddToCartSerializers, RemoveFromCartSerializers, RetrieveCartProductsSerializers

from cloudinary import uploader as cloud


class PaginationStyle(PageNumberPagination):
    page_size = 20


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


class AddProduct(generics.GenericAPIView):
    """
    AddProduct is the POST request that handles the creation
    of fmcg products instance.
    """

    serializer_class = ProductSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)
    parser_classes = (
        MultiPartParser,
        JSONParser,
    )

    def post(self, request):
        user_data = request.data

        serializer = self.serializer_class(data=user_data)
        if serializer.is_valid(raise_exception=True):
            try:
                product_upload = request.data.get("image_url")
                upload_product = cloud.upload(product_upload)
                product_url = upload_product["url"]

            except Exception as err:
                return Response(
                    {"error": "An error occurred: {}".format(err)},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

            Product.objects.create(
                name=request.data.get("name"),
                image_url=product_url,
                category=request.data.get("name"),
                company=request.data.get("company"),
                price=request.data.get("price"),
                description=request.data.get("description"),
                quantity=request.data.get("quantity"),
            )
            resp = {
                "status": "success",
                "message": "Product added successfully!",
                "data": {
                    "name": request.data.get("name"),
                    "image_url": product_url,
                    "category": request.data.get("name"),
                    "company": request.data.get("company"),
                    "price": request.data.get("price"),
                    "description": request.data.get("description"),
                    "quantity": request.data.get("quantity"),
                }
            }
            return Response(data=resp, status=status.HTTP_201_CREATED)

        else:
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def upload_files(self, doc_file):
        document = cloud.upload(file=doc_file)
        self.uploaded_doc_url = document["url"]


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
        all_products = Product.objects.all()
        return all_products

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
        user_data = request.data

        serializer = self.serializer_class(data=user_data)
        if serializer.is_valid(raise_exception=True):
            product_id = kwargs("product_id")
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

            return Response({
                "status": "success",
                "message": "Product added to cart.",
                "cart_item": {
                    "cart_id": cart.cart_id,
                    "product": product.name,
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
        user_data = request.data
        cart_items = CartItem.objects.filter(user=user)

        serializer = self.serializer_class(data=user_data)
        if serializer.is_valid(raise_exception=True):
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
                    "product": item.product.name,
                    "quantity": item.quantity,
                    "price_per_unit": item.price,
                    "total_price": item.get_total_price()
                })

            return Response({
                "status": "success",
                "message": "Cart items retrieved successfully.",
                "cart_items": cart_data
            }, status=status.HTTP_200_OK)
        else:
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)


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

        return Response({
            "status": "success",
            "message": "Product removed from cart."
        }, status=status.HTTP_204_NO_CONTENT)
