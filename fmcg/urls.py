from django.urls import path
from .views import (
    CategoryListView, CompanyListView,
    ListAllProducts, ProductDetails,
    AddToCart, RemoveFromCart, RetrieveCartProducts,
    FmcgCheckout, FmcgRatingView, GetFmcgReview, PickupAddressListView
)

urlpatterns = [
    path("categories", CategoryListView.as_view(), name="category_list"),
    path("companies", CompanyListView.as_view(), name="company_list"),
    path("list-all-products", ListAllProducts.as_view(), name="list_all_products"),
    path("product-details/<uuid:id>", ProductDetails.as_view(), name="product-details"),
    path("cart/<uuid:product_id>/add", AddToCart.as_view(), name="add_cart"),
    path("cart/retrieve", RetrieveCartProducts.as_view(), name="retrieve_cart_products"),
    path("cart/<uuid:product_id>/remove", RemoveFromCart.as_view(), name="remove_cart"),
    path("checkout", FmcgCheckout.as_view(), name="checkout"),
    path("product/<int:id>/rate", FmcgRatingView.as_view(), name="rate_product"),
    path('product/<int:product_id>/reviews/', GetFmcgReview.as_view(), name='product-reviews'),
    path("pickup-addresses", PickupAddressListView.as_view(), name='pickup_address_list'),
]
