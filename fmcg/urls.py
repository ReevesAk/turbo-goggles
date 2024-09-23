from django.urls import path
from .views import CategoryListView, CompanyListView

urlpatterns = [
    path("categories", CategoryListView.as_view(), name="category_list"),
    path("companies", CompanyListView.as_view(), name="company_list"),
]
