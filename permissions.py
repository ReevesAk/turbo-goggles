import uuid

from rest_framework import permissions
from rest_framework.exceptions import ValidationError
from rest_framework.exceptions import PermissionDenied

from security import encrypt


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
            raise PermissionDenied(encrypt("Only verified users can login."))


class IsGuestWithValidId(permissions.BasePermission):
    """
    Allows access only to unauthenticated (guest) users with a valid UUID guest_id.
    """

    def has_permission(self, request, view):
        user = request.user
        if user and user.is_authenticated:
            return False  # Block authenticated users

        guest_id = request.headers.get('X-Guest-ID')
        if guest_id:
            try:
                uuid.UUID(guest_id, version=4)  # Validate UUID
                return True
            except (ValueError, TypeError):
                raise ValidationError({"guest_id": "Invalid guest_id. Must be a valid UUIDv4."})

        return False


class IsAuthenticatedOrGuestWithValidId(permissions.BasePermission):
    """
    Allows access via:
    - Authenticated users (JWT)
    - Guests with valid X-Guest-ID header (UUIDv4)
    """
    def has_permission(self, request, view):
        # Authenticated users always have permission
        if request.user and request.user.is_authenticated:
            return True

        # Guest users need valid UUID
        guest_id = request.headers.get('X-Guest-ID')
        if not guest_id:
            return False

        try:
            uuid.UUID(guest_id, version=4)
            return True
        except ValueError:
            return False


class HasCompletedSurvey(permissions.BasePermission):
    """
    Allows access only to authenticated users who have completed the survey.
    """

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            raise ValidationError(encrypt("Authentication is required to access this resource."))

        if request.user.has_done_survey:
            return True

        raise ValidationError(encrypt("You need to complete the survey to access this resource."))


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
                raise ValidationError(encrypt("Only Users, Members and Partners can use this service."))

        raise ValidationError(encrypt("Authentication is required to access this resource."))


class IsSuperAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        # Required type.
        required_user_types = ["SuperAdmin"]

        if request.user.is_authenticated:
            # Check if the user_type matches the required user_type
            if request.user.active_role in required_user_types:
                return True
            else:
                raise ValidationError(encrypt("Only SuperAdmin Users can perform this action."))

        raise ValidationError(encrypt("Authentication is required to access this resource."))


class IsPartner(permissions.BasePermission):
    def has_permission(self, request, view):
        # Required type.
        required_user_types = ["Partner"]

        if request.user.is_authenticated:
            # Check if the user_type matches the required user_type
            if request.user.active_role in required_user_types:
                return True
            else:
                raise ValidationError(encrypt("Only Partners can perform this action."))

        raise ValidationError(encrypt("Authentication is required to access this resource."))


class IsPartnerUserOrMember(permissions.BasePermission):
    def has_permission(self, request, view):
        # Required type.
        required_user_types = ["Partner", "User", "Member", "BrandAd"]

        if request.user.is_authenticated:
            # Check if the user_type matches the required user_type
            if request.user.active_role in required_user_types:
                return True
            else:
                raise ValidationError(encrypt("Only Partners, Users and Members can perform this action."))

        raise ValidationError(encrypt("Authentication is required to access this resource."))


class IsMember(permissions.BasePermission):
    def has_permission(self, request, view):
        # Required type.
        required_user_types = ["Member"]

        if request.user.is_authenticated:
            # Check if the user_type matches the required user_type
            if request.user.active_role in required_user_types:
                return True
            else:
                raise ValidationError(encrypt("Only Users and Members can perform this action."))

        raise ValidationError(encrypt("Authentication is required to access this resource."))


class IsBrandAd(permissions.BasePermission):
    def has_permission(self, request, view):
        # Required type.
        required_user_types = ["BrandAd"]

        if request.user.is_authenticated:
            # Check if the user_type matches the required user_type
            if request.user.active_role in required_user_types:
                return True
            else:
                raise ValidationError(encrypt("Only BrandAd can perform this action."))

        raise ValidationError(encrypt("Authentication is required to access this resource."))


class IsBrandAdAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        # Required type.
        required_user_types = ["BrandAdAdmin"]

        if request.user.is_authenticated:
            # Check if the user_type matches the required user_type
            if request.user.active_role in required_user_types:
                return True
            else:
                raise ValidationError(encrypt("Only BrandAdAdmin can perform this action."))

        raise ValidationError(encrypt("Authentication is required to access this resource."))


class IsPartnerAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        # Required type.
        required_user_types = ["PartnersAdmin"]

        if request.user.is_authenticated:
            # Check if the user_type matches the required user_type
            if request.user.active_role in required_user_types:
                return True
            else:
                raise ValidationError(encrypt("Only PartnersAdmin can perform this action."))

        raise ValidationError(encrypt("Authentication is required to access this resource."))


class IsWalletAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        # Required type.
        required_user_types = ["WalletAdmin"]

        if request.user.is_authenticated:
            # Check if the user_type matches the required user_type
            if request.user.active_role in required_user_types:
                return True
            else:
                raise ValidationError(encrypt("Only WalletAdmin can perform this action."))

        raise ValidationError(encrypt("Authentication is required to access this resource."))


class IsFmcgAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        # Required type.
        required_user_types = ["FmcgAdmin"]

        if request.user.is_authenticated:
            # Check if the user_type matches the required user_type
            if request.user.active_role in required_user_types:
                return True
            else:
                raise PermissionDenied(encrypt(detail="Only FmcgAdmin can perform this action."))

        raise ValidationError(encrypt(detail="Authentication is required to access this resource."))


class IsTaskAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        # Required type.
        required_user_types = ["TaskAdmin"]

        if request.user.is_authenticated:
            # Check if the user_type matches the required user_type
            if request.user.active_role in required_user_types:
                return True
            else:
                raise ValidationError(encrypt(detail="Only TaskAdmin Users can perform this action."))

        raise ValidationError(encrypt(detail="Authentication is required to access this resource."))


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

    # def has_permission(self, request, view):

    #     if request.user.is_authenticated:
    #         customer = CustomerData.objects.filter(user=request.user).exists()

    #         # Check if the user_type matches the required user_type
    #         if customer:
    #             return True
    #         else:
    #             raise ValidationError(encrypt("You need to have a wallet to conduct this transaction."))

    #     raise ValidationError(encrypt("Authentication is required to access this resource."))

    pass


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
                raise ValidationError(encrypt("Only admin users can perform this action."))

        raise ValidationError(encrypt("Authentication is required to access this resource."))


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
        if request.user.active_role == 'WalletAdmin' or request.user.active_role == 'SuperAdmin':
            return True

        return False


class IsPartnerUserOrMemberBrandAdOrSuperAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        # Required type.
        required_user_types = ["Partner", "User", "Member", "BrandAd", "SuperAdmin"]

        if request.user.is_authenticated:
            # Check if the user_type matches the required user_type
            if request.user.active_role in required_user_types:
                return True
            else:
                raise ValidationError(encrypt("Only the SuperAdmin, BrandAds, Partners, Users and Members can perform this action."))

        raise ValidationError(encrypt("Authentication is required to access this resource."))


class IsManager(permissions.BasePermission):
    def has_permission(self, request, view):
        # Required type.
        required_user_types = ["Manager"]

        if request.user.is_authenticated:
            # Check if the user_type matches the required user_type
            if request.user.active_role in required_user_types:
                return True
            else:
                raise ValidationError(encrypt("Only the Manager can perform this action."))

        raise ValidationError(encrypt("Authentication is required to access this resource."))


class IsAgent(permissions.BasePermission):
    def has_permission(self, request, view):
        # Define the agent roles you want to allow
        support_agents = ["Manager", "Agent", "Moderator"]

        if request.user.is_authenticated:
            # Check if the user's active role is in the list of allowed admin roles
            if request.user.active_role in support_agents:
                return True
            else:
                raise ValidationError("Only agents users can perform this action.")

        raise ValidationError("Authentication is required to access this resource.")
