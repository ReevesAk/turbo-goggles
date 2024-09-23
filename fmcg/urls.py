from django.urls import path
from .views import CategoryListView, CompanyListView, AddProduct, ListAllProducts, ProductDetails

urlpatterns = [
    path("categories", CategoryListView.as_view(), name="category_list"),
    path("companies", CompanyListView.as_view(), name="company_list"),
    path("add-product", AddProduct.as_view(), name="add_product"),
    path("list-all-products", ListAllProducts.as_view(), name="list_all_products"),
    path("product-details/<uuid:id>", ProductDetails.as_view(), name="product-details"),
]
