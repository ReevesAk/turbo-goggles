from rest_framework import permissions
from rest_framework.exceptions import ValidationError


class VasPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        # Required types.
        required_user_types = ["User", "Member", "SuperAdmin"]

        # Check if the user is authenticated
        if request.user.is_authenticated:
            # Check if the user's user_type matches the required user_type
            if request.user.account_type in required_user_types:
                return True
            else:
                raise ValidationError("Only Users and Members can use this service.")

        raise ValidationError("Authentication is required to access this resource.")


class IsSuperAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        # Required type.
        required_user_types = ["SuperAdmin"]

        if request.user.is_authenticated:
            # Check if the user_type matches the required user_type
            if request.user.account_type in required_user_types:
                return True
            else:
                raise ValidationError("Only SuperAdmin Users can perform this action.")

        raise ValidationError("Authentication is required to access this resource.")


class IsPartner(permissions.BasePermission):
    def has_permission(self, request, view):
        # Required type.
        required_user_types = ["Partner"]

        if request.user.is_authenticated:
            # Check if the user_type matches the required user_type
            if request.user.account_type in required_user_types:
                return True
            else:
                raise ValidationError("Only Partners can perform this action.")

        raise ValidationError("Authentication is required to access this resource.")


class IsMember(permissions.BasePermission):
    def has_permission(self, request, view):
        # Required type.
        required_user_types = ["Member"]

        if request.user.is_authenticated:
            # Check if the user_type matches the required user_type
            if request.user.account_type in required_user_types:
                return True
            else:
                raise ValidationError("Only Members can perform this action.")

        raise ValidationError("Authentication is required to access this resource.")


class IsPartnerAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        # Required type.
        required_user_types = ["PartnersAdmin"]

        if request.user.is_authenticated:
            # Check if the user_type matches the required user_type
            if request.user.account_type in required_user_types:
                return True
            else:
                raise ValidationError("Only PartnersAdmin can perform this action.")

        raise ValidationError("Authentication is required to access this resource.")
