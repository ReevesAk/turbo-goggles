from rest_framework import permissions
from rest_framework.exceptions import ValidationError
from rest_framework.exceptions import PermissionDenied

from banking.models import CustomerData


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


class IsUser(permissions.BasePermission):
    def has_permission(self, request, view):
        # Required type.
        required_user_types = ["User"]

        if request.user.is_authenticated:
            # Check if the user_type matches the required user_type
            if request.user.active_role in required_user_types:
                return True
            else:
                raise ValidationError("Only Users can perform this action.")

        raise ValidationError("Authentication is required to access this resource.")


class VasPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        # Required types.
        required_user_types = ["User", "Member", "Partner", "SuperAdmin"]

        # Check if the user is authenticated
        if request.user.is_authenticated:
            # Check if the user's user_type matches the required user_type
            if request.user.active_role in required_user_types:
                return True
            else:
                raise ValidationError("Only Users, Members and Partners can use this service.")

        raise ValidationError("Authentication is required to access this resource.")


class IsSuperAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        # Required type.
        required_user_types = ["SuperAdmin"]

        if request.user.is_authenticated:
            # Check if the user_type matches the required user_type
            if request.user.active_role in required_user_types:
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
            if request.user.active_role in required_user_types:
                return True
            else:
                raise ValidationError("Only Partners can perform this action.")

        raise ValidationError("Authentication is required to access this resource.")


class IsPartnerUserOrMember(permissions.BasePermission):
    def has_permission(self, request, view):
        # Required type.
        required_user_types = ["Partner", "User", "Member"]

        if request.user.is_authenticated:
            # Check if the user_type matches the required user_type
            if request.user.active_role in required_user_types:
                return True
            else:
                raise ValidationError("Only Partners, Users and Members can perform this action.")

        raise ValidationError("Authentication is required to access this resource.")


class IsUserOrMember(permissions.BasePermission):
    def has_permission(self, request, view):
        # Required type.
        required_user_types = ["User", "Member"]

        if request.user.is_authenticated:
            # Check if the user_type matches the required user_type
            if request.user.active_role in required_user_types:
                return True
            else:
                raise ValidationError("Only Users and Members can perform this action.")

        raise ValidationError("Authentication is required to access this resource.")


class IsBrandAd(permissions.BasePermission):
    def has_permission(self, request, view):
        # Required type.
        required_user_types = ["BrandAd"]

        if request.user.is_authenticated:
            # Check if the user_type matches the required user_type
            if request.user.active_role in required_user_types:
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
            if request.user.active_role in required_user_types:
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
            if request.user.active_role in required_user_types:
                return True
            else:
                raise ValidationError("Only PartnersAdmin can perform this action.")

        raise ValidationError("Authentication is required to access this resource.")


class IsTaskAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        # Required type.
        required_user_types = ["TaskAdmin"]

        if request.user.is_authenticated:
            # Check if the user_type matches the required user_type
            if request.user.active_role in required_user_types:
                return True
            else:
                raise ValidationError("Only TaskAdmin Users can perform this action.")

        raise ValidationError("Authentication is required to access this resource.")


class IsOwnerOrReadOnly(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object to delete it.
    """

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True

        return obj.user == request.user


class hasWallet(permissions.BasePermission):
    """
    Custom permission to only allow owners of wallet to convert naira to ddollar.
    """

    def has_permission(self, request, view):

        if request.user.is_authenticated:
            customer = CustomerData.objects.filter(user=request.user).exists()

            # Check if the user_type matches the required user_type
            if customer:
                return True
            else:
                raise ValidationError("You need to have a wallet to conduct this transaction.")

        raise ValidationError("Authentication is required to access this resource.")
