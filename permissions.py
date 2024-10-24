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
        required_user_types = ["Partner", "User", "Member", "BrandAd"]

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


class IsWalletAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        # Required type.
        required_user_types = ["WalletAdmin"]

        if request.user.is_authenticated:
            # Check if the user_type matches the required user_type
            if request.user.active_role in required_user_types:
                return True
            else:
                raise ValidationError("Only WalletAdmin can perform this action.")

        raise ValidationError("Authentication is required to access this resource.")


class IsFmcgAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        # Required type.
        required_user_types = ["FmcgAdmin"]

        if request.user.is_authenticated:
            # Check if the user_type matches the required user_type
            if request.user.active_role in required_user_types:
                return True
            else:
                raise PermissionDenied(detail="Only FmcgAdmin can perform this action.")

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


class IsNotDisabled(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.user.is_disabled:
            raise PermissionDenied("Access denied. Your account is disabled.")
        return True


class IsAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        # Define the admin roles you want to allow
        admin_roles = ["AdAdmin", "SuperAdmin", "TaskAdmin", "MembersAdmin", "UserAdmin", "PartnersAdmin", "ContentAdmin", "IntegrationAdmin", "WalletAdmin"]

        if request.user.is_authenticated:
            # Check if the user's active role is in the list of allowed admin roles
            if request.user.active_role in admin_roles:
                return True
            else:
                raise ValidationError("Only admin users can perform this action.")

        raise ValidationError("Authentication is required to access this resource.")


class IsFmcgAdminOrSuperAdmin(permissions.BasePermission):
    """
    Custom permission that grants access if the user is authenticated and
    is either an FmcgAdmin or a SuperAdmin.
    """

    def has_permission(self, request, view):
        # First, check if the user is authenticated
        if not request.user.is_authenticated:
            return False

        # Check if the user is either FmcgAdmin or SuperAdmin
        if request.user.active_role == 'FmcgAdmin' or request.user.active_role == 'SuperAdmin':
            return True

        return False


class IsPartnerAdminOrSuperAdmin(permissions.BasePermission):
    """
    Custom permission that grants access if the user is authenticated and
    is either an PartnersAdmin or a SuperAdmin.
    """

    def has_permission(self, request, view):
        # First, check if the user is authenticated
        if not request.user.is_authenticated:
            return False

        # Check if the user is either PartnersAdmin or SuperAdmin
        if request.user.active_role == 'PartnersAdmin' or request.user.active_role == 'SuperAdmin':
            return True

        return False


class IsAdAdminOrSuperAdmin(permissions.BasePermission):
    """
    Custom permission that grants access if the user is authenticated and
    is either an PartnersAdmin or a SuperAdmin.
    """

    def has_permission(self, request, view):
        # First, check if the user is authenticated
        if not request.user.is_authenticated:
            return False

        # Check if the user is either AdAdmin or SuperAdmin
        if request.user.active_role == 'AdAdmin' or request.user.active_role == 'SuperAdmin':
            return True

        return False


class IsWalletAdminOrSuperAdmin(permissions.BasePermission):
    """
    Custom permission that grants access if the user is authenticated and
    is either an IsWalletAdmin or a SuperAdmin.
    """

    def has_permission(self, request, view):
        # First, check if the user is authenticated
        if not request.user.is_authenticated:
            return False

        # Check if the user is either IsWalletAdmin or SuperAdmin
        if request.user.active_role == 'IsWalletAdmin' or request.user.active_role == 'SuperAdmin':
            return True

        return False
