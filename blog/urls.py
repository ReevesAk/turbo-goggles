# blog/urls.py
from django.urls import path
from . import views

app_name = "blog"

urlpatterns = [
    # Admin endpoints
    path("admin/create/", views.BlogCreateView.as_view(), name="admin-create"),
    path("admin/<uuid:pk>/", views.BlogAdminDetailView.as_view(), name="admin-detail"),
    path("admin/", views.BlogAdminListView.as_view(), name="admin-list"),
    # Public endpoints
    path("<slug:slug>/", views.BlogDetailView.as_view(), name="detail"),
    path("", views.BlogListView.as_view(), name="list"),
]
