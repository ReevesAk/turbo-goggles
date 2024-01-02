from django.urls import path
from .views import (
    RegisterSuperAdmin,
    CreateOtherAdmin,
    UpdateAdminRole,
    ListAdmin,
    GetAllCustomers,
    DeleteAdmin,
)


urlpatterns = [
    path("register-super-admin/", RegisterSuperAdmin.as_view(), name="resgiter_admin"),
    path("create-new-admin/", CreateOtherAdmin.as_view(), name="create_new_admin"),
    path("update-admin-role/", UpdateAdminRole.as_view(), name="update_admin_role"),
    path("list-admin-users/", ListAdmin.as_view(), name="list_admin_users"),
    path("get-all-customers/", GetAllCustomers.as_view(), name="get_all_customers"),
    path("delete-admin/", DeleteAdmin.as_view(), name="delete_admin_users"),
]
