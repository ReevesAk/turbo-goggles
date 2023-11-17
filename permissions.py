from rest_framework import permissions
from rest_framework.exceptions import ValidationError
from rest_framework.exceptions import PermissionDenied


class IsVerifiedUser(permissions.BasePermission):
    """
    Custom permission to only allow verified users to access the view.
    """

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return True
        
        if request.user.is_verified:
            return True
        else:
            raise PermissionDenied("Only verified users can login.")


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


class IsPartnerOrMember(permissions.BasePermission):
    def has_permission(self, request, view):
        # Required type.
        required_user_types = ["Partner", "Member"]

        if request.user.is_authenticated:
            # Check if the user_type matches the required user_type
            if request.user.account_type in required_user_types:
                return True
            else:
                raise ValidationError("Only Partners and Members can perform this action.")

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


class IsBrandAd(permissions.BasePermission):
    def has_permission(self, request, view):
        # Required type.
        required_user_types = ["BrandAd"]

        if request.user.is_authenticated:
            # Check if the user_type matches the required user_type
            if request.user.account_type in required_user_types:
                return True
            else:
                raise ValidationError("Only BrandAd can perform this action.")

        raise ValidationError("Authentication is required to access this resource.")


class IsBrandAdAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        # Required type.
        required_user_types = ["BrandAdAdmin"]

        if request.user.is_authenticated:
            # Check if the user_type matches the required user_type
            if request.user.account_type in required_user_types:
                return True
            else:
                raise ValidationError("Only BrandAdAdmin can perform this action.")

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
