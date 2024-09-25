from django.urls import path
from .views import CategoryListView, CompanyListView, AddProduct, ListAllProducts, ProductDetails, AddToCart, RemoveFromCart

urlpatterns = [
    path("categories", CategoryListView.as_view(), name="category_list"),
    path("companies", CompanyListView.as_view(), name="company_list"),
    path("add-product", AddProduct.as_view(), name="add_product"),
    path("list-all-products", ListAllProducts.as_view(), name="list_all_products"),
    path("product-details/<uuid:id>", ProductDetails.as_view(), name="product-details"),
    path("cart/<uuid:product_id>/add", AddToCart.as_view(), name='add_cart'),
    path("cart/<uuid:product_id>/remove", RemoveFromCart.as_view(), name='remove_cart'),
]
