from rest_framework import permissions
from rest_framework.exceptions import ValidationError


class VasPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        # Define the required user_type for this permission
        required_user_types = ["User", "Member", "SuperAdmin"]

        # Check if the user is authenticated
        if request.user.is_authenticated:
            # Check if the user's user_type matches the required user_type
            if request.user.account_type in required_user_types:
                return True
            else:
                raise ValidationError("Only Users and Members can use this service.")

        raise ValidationError("Authentication is required to access this resource.")


class SuperAdminPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        # Define the required user_type for this permission
        required_user_types = ["SuperAdmin"]

        # Check if the user is authenticated
        if request.user.is_authenticated:
            # Check if the user's user_type matches the required user_type
            if request.user.account_type in required_user_types:
                return True
            else:
                raise ValidationError("Only SuperAdmin Users can perform this action.")

        raise ValidationError("Authentication is required to access this resource.")
