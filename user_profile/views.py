import logging
import base64

from commons import Messaging
from permissions import IsSuperAdmin, IsMember

from django.contrib.auth.hashers import check_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.contrib.contenttypes.models import ContentType
from django.template.loader import render_to_string
from django.db.models import Q
from django.db import transaction

from rest_framework import generics, exceptions
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.exceptions import ValidationError

import rest_framework.serializers as s
from drf_spectacular.utils import (
    OpenApiExample,
    extend_schema_view,
    extend_schema,
    inline_serializer,
)


from .serializers import (
    ChangePasswordSerializer,
    GetUserSerializer,
    UpdateUserSerializer,
    ProfileImageSerializer,
    DeleteUserSerializer,
    OpenRewardBoxSerializers,
    ClaimRewardSerializers,
    MemberSurveySerializers,
    HandleChangeRequestSerializer,
    SwitchToMemberSerializer,
    SwitchToPartnersSerializer,
    SwitchToBrandAdSerializer,
    AddToFavouriteSerializer,
    FavouriteSerializer,
    SupportTicketSerializer,
    TierListResponseSerializer,
    SetAlertTypeSerializer,
    CreateUpdateUserLocationSerializer,
    UserLocationResponseSerializer,
    SubmitSocialHandleSerializer,
)
from support.serializers import AgentRatingSerializers
from .helpers import MysteryBox, VariationCodes, MemberSurveyService
from .choices import LEVELS
from accounts.models import User, Rewards, UserNotification, AccountType
from roles.models import ActivityModel
from support.models import Ticket, AgentRating
from vas.helpers import VAS
from self_service.models import (
    LandTravels,
    GymSubcription,
    CinemaBooking,
    CourierService,
    ConsumableService,
    Hotels,
    RestaurantBooking,
)
from vas.models import ValueAddedServices
from fmcg.models import Product, Favourite
from security import encrypt, decrypt
from .models import (
    DeviceToken,
    MemberSurvey,
    HandleChangeRequest,
    PLATFORM_HANDLE_FIELDS,
    UserLocation,
)
from .fcm import send_push_to_user, send_push_to_admins

logger = logging.getLogger(__name__)


@extend_schema(
    summary="Log User's Current Location",
    tags=["Location"],
    description="""
    Create or update the current user's location.

    - **POST**: Creates a new location record if none exists, or updates the existing one.
    - **GET**: Retrieves the user's current location.
    - **PUT**: Replaces the user's location (returns 404 if not found).
    - **PATCH**: Partially updates the user's location.
    - **DELETE**: Removes the user's location.

    Each user can only have one location record. The location is stored as
    latitude and longitude coordinates.

    All requests and responses are encrypted.
    """,
    request=CreateUpdateUserLocationSerializer,
    responses={
        200: inline_serializer(
            name="LocationUpdateResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "data": s.DictField(),
            },
        ),
        201: inline_serializer(
            name="LocationCreateResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "data": s.DictField(),
            },
        ),
        400: inline_serializer(
            name="LocationErrorResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "errors": s.DictField(required=False),
            },
        ),
        401: inline_serializer(
            name="LocationUnauthorizedResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
            },
        ),
        404: inline_serializer(
            name="LocationNotFoundResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
            },
        ),
        409: inline_serializer(
            name="LocationConflictResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
            },
        ),
    },
)
class LogUserLocation(generics.GenericAPIView):
    """
    Log user's current location.

    Creates a new location record if none exists, or updates the existing one.
    Each user can only have one location record.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = CreateUpdateUserLocationSerializer

    def get_serializer_class(self):
        """Return appropriate serializer based on request method."""
        if self.request.method == "GET":
            return UserLocationResponseSerializer
        return CreateUpdateUserLocationSerializer

    def post(self, request):
        """Create user's location. Handles both create and update scenarios."""
        user = request.user

        try:
            decrypted_payload = decrypt(request.data)

            if not isinstance(decrypted_payload, dict):
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "message": "Invalid data format. Expected JSON object.",
                        }
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )

            location_data = {
                key: value.strip() if isinstance(value, str) else value
                for key, value in decrypted_payload.items()
                if value is not None
            }

            serializer = self.serializer_class(data=location_data)

            if not serializer.is_valid():
                logger.warning(
                    f"Location validation failed for user {user.email}: {serializer.errors}"
                )
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "message": "Validation error occurred.",
                            "errors": serializer.errors,
                        }
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )

            with transaction.atomic():
                location, created = UserLocation.objects.update_or_create(
                    user=user,
                    defaults={
                        "latitude": serializer.validated_data["latitude"],
                        "longitude": serializer.validated_data["longitude"],
                    },
                )

            action = "created" if created else "updated"
            logger.info(
                f"Location {action} for user {user.email}: "
                f"lat={location.latitude}, lng={location.longitude}"
            )

            location.user = user
            response_serializer = UserLocationResponseSerializer(location)
            response_data = {
                "status": "success",
                "message": f"Location {action} successfully",
                "data": response_serializer.data,
            }

            return Response(
                data=encrypt(response_data),
                status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
            )

        except Exception as e:
            logger.error(
                f"Error creating/updating location for user {user.email}: {str(e)}",
                exc_info=True,
            )
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "An error occurred while processing your location.",
                    }
                ),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def get(self, request):
        """Get user's current location."""
        user = request.user

        try:
            # Use select_related to avoid N+1 query
            location = UserLocation.objects.select_related("user").get(user=user)
            serializer = UserLocationResponseSerializer(location)

            response_data = {
                "status": "success",
                "message": "Location retrieved successfully",
                "data": serializer.data,
            }

            return Response(
                data=encrypt(response_data),
                status=status.HTTP_200_OK,
            )

        except UserLocation.DoesNotExist:
            logger.warning(f"Location not found for user {user.email}")
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "Location not found for this user. Please log your location first.",
                    }
                ),
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as e:
            logger.error(f"Error retrieving location for user {user.email}: {str(e)}")
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "An error occurred while retrieving your location.",
                    }
                ),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def put(self, request):
        """
        Full replace of user's location.
        Returns 404 if location doesn't exist.
        """
        user = request.user

        try:
            # Check if location exists with select_related
            try:
                location = UserLocation.objects.select_related("user").get(user=user)
            except UserLocation.DoesNotExist:
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "message": "Location not found. Use POST to create one.",
                        }
                    ),
                    status=status.HTTP_404_NOT_FOUND,
                )

            decrypted_payload = decrypt(request.data)

            if not isinstance(decrypted_payload, dict):
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "message": "Invalid data format. Expected JSON object.",
                        }
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )

            location_data = {
                key: value.strip() if isinstance(value, str) else value
                for key, value in decrypted_payload.items()
                if value is not None
            }

            # Full replace - all fields required
            serializer = self.serializer_class(data=location_data)

            if not serializer.is_valid():
                logger.warning(
                    f"Location validation failed for user {user.email}: {serializer.errors}"
                )
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "message": "Validation error occurred.",
                            "errors": serializer.errors,
                        }
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )

            with transaction.atomic():
                location.latitude = serializer.validated_data["latitude"]
                location.longitude = serializer.validated_data["longitude"]
                location.save()

            logger.info(
                f"Location replaced for user {user.email}: "
                f"lat={location.latitude}, lng={location.longitude}"
            )

            response_serializer = UserLocationResponseSerializer(location)
            response_data = {
                "status": "success",
                "message": "Location updated successfully",
                "data": response_serializer.data,
            }

            return Response(
                data=encrypt(response_data),
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            logger.error(f"Error updating location for user {user.email}: {str(e)}")
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "An error occurred while updating your location.",
                    }
                ),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def patch(self, request):
        """Partial update of user's location."""
        user = request.user

        try:
            # Check if location exists with select_related
            try:
                location = UserLocation.objects.select_related("user").get(user=user)
            except UserLocation.DoesNotExist:
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "message": "Location not found. Use POST to create one.",
                        }
                    ),
                    status=status.HTTP_404_NOT_FOUND,
                )

            decrypted_payload = decrypt(request.data)

            if not isinstance(decrypted_payload, dict):
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "message": "Invalid data format. Expected JSON object.",
                        }
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )

            location_data = {
                key: value.strip() if isinstance(value, str) else value
                for key, value in decrypted_payload.items()
                if value is not None
            }

            # Partial update
            serializer = self.serializer_class(
                location, data=location_data, partial=True
            )

            if not serializer.is_valid():
                logger.warning(
                    f"Partial location validation failed for user {user.email}: {serializer.errors}"
                )
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "message": "Validation error occurred.",
                            "errors": serializer.errors,
                        }
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )

            with transaction.atomic():
                for field in ["latitude", "longitude"]:
                    if field in serializer.validated_data:
                        setattr(location, field, serializer.validated_data[field])

                location.save()

            logger.info(
                f"Partial update of location for user {user.email}: "
                f"lat={location.latitude}, lng={location.longitude}"
            )

            response_serializer = UserLocationResponseSerializer(location)
            response_data = {
                "status": "success",
                "message": "Location updated successfully",
                "data": response_serializer.data,
            }

            return Response(
                data=encrypt(response_data),
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            logger.error(f"Error updating location for user {user.email}: {str(e)}")
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "An error occurred while updating your location.",
                    }
                ),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def delete(self, request):
        """Delete user's location."""
        user = request.user

        try:
            location = UserLocation.objects.get(user=user)
            location.delete()

            logger.info(f"Location deleted for user {user.email}")

            return Response(
                data=encrypt(
                    {
                        "status": "success",
                        "message": "Location deleted successfully",
                    }
                ),
                status=status.HTTP_200_OK,
            )

        except UserLocation.DoesNotExist:
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "Location not found for this user.",
                    }
                ),
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as e:
            logger.error(f"Error deleting location for user {user.email}: {str(e)}")
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "An error occurred while deleting your location.",
                    }
                ),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


@extend_schema(
    summary="Switch active role to Member",
    tags=["Profile"],
    description="Switches the authenticated user's active role to Member. The user must already be registered with a Member account type.",
    responses={
        200: inline_serializer(
            name="SwitchToMemberResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "data": s.CharField(),
            },
        ),
        400: inline_serializer(
            name="SwitchToMemberError",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class SwitchToMember(generics.RetrieveAPIView):
    """
    SwitchToMember is the PUT request method for updating and switching
    to a user's account type.
    """

    serializer_class = SwitchToMemberSerializer
    permission_classes = (IsAuthenticated,)

    def get_object(self):
        return self.request.user

    def put(self, request):
        user = self.get_object()
        logger.info("User  %s is attempting to switch account type.", user.email)

        try:
            account_types = AccountType.objects.filter(user=user)
            logger.debug(
                "Account types retrieved for user %s: %s", user.email, account_types
            )

            # Check if any AccountType has "Member" in user_type
            is_member = any(acct.user_type == "Member" for acct in account_types)

            if not is_member:
                data = {
                    "status": "fail",
                    "message": "Oops, you haven't registered as a Member yet.",
                    "data": user.active_role,
                }
                logger.warning(
                    "User  %s attempted to switch to Member but is not registered as one.",
                    user.email,
                )
                return Response(data=encrypt(data), status=status.HTTP_400_BAD_REQUEST)

        except AccountType.DoesNotExist:
            logger.error("AccountType for user %s does not exist.", user.email)
            raise exceptions.ValidationError(
                encrypt("AccountType for the user does not exist.")
            )

        # Handle already switched to Member
        if user.active_role == "Member":
            data = {
                "status": "success",
                "message": "You are already on the Member screen.",
                "data": user.active_role,
            }
            logger.info("User  %s is already on the Member screen.", user.email)
            return Response(data=encrypt(data), status=status.HTTP_200_OK)

        # Log the switch action
        logger.info(
            "User  %s is switching account type from %s to Member.",
            user.email,
            user.active_role,
        )

        UserNotification.objects.create(
            user=user,
            title="User Type Switch",
            message="Account type switched to Member successfully.",
        )

        ActivityModel.objects.create(
            user=user,
            title="User Type Switch",
            description=f"{user.first_name} {user.last_name} switched account from {user.active_role} to Member.",
        )

        # User has a Member account type, switch the role
        user.active_role = "Member"
        user.save()

        data = {
            "status": "success",
            "message": "Account type switched to Member successfully.",
            "data": user.active_role,
        }
        logger.info("User  %s successfully switched account type to User.", user.email)
        return Response(data=encrypt(data), status=status.HTTP_200_OK)


@extend_schema(
    summary="Switch active role to Partner",
    tags=["Profile"],
    description="Switches the authenticated user's active role to Partner. The user must already be registered with a Partner account type.",
    responses={
        200: inline_serializer(
            name="SwitchToPartnerResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "data": s.CharField(),
            },
        ),
        400: inline_serializer(
            name="SwitchToPartnerError",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class SwitchToPartner(generics.RetrieveAPIView):
    """
    SwitchToPartner is the PUT request method for updating and switching
    to a Partner's account type.
    """

    serializer_class = SwitchToPartnersSerializer
    permission_classes = (IsAuthenticated,)

    def get_object(self):
        return self.request.user

    def put(self, request):
        user = self.get_object()
        logger.info("User  %s is attempting to switch account type.", user.email)

        try:
            account_types = AccountType.objects.filter(user=user)
            logger.debug(
                "Account types retrieved for user %s: %s", user.email, account_types
            )

            # Check if any AccountType has "Partner" in user_type
            is_partner = any(acct.user_type == "Partner" for acct in account_types)

            if not is_partner:
                data = {
                    "status": "fail",
                    "message": "Oops, you haven't registered as a Partner yet.",
                    "data": user.active_role,
                }
                logger.warning(
                    "User  %s attempted to switch to Partner but is not registered as one.",
                    user.email,
                )
                return Response(data=encrypt(data), status=status.HTTP_400_BAD_REQUEST)

        except AccountType.DoesNotExist:
            logger.error("AccountType for user %s does not exist.", user.email)
            raise exceptions.ValidationError(
                encrypt("AccountType for the user does not exist.")
            )

        # Handle already switched to Partner
        if user.active_role == "Partner":
            data = {
                "status": "success",
                "message": "You are already on the Partner screen.",
                "data": user.active_role,
            }
            logger.info("User  %s is already on the Partner screen.", user.email)
            return Response(data=encrypt(data), status=status.HTTP_200_OK)

        # Log the switch action
        logger.info(
            "User  %s is switching account type from %s to Partner.",
            user.email,
            user.active_role,
        )

        UserNotification.objects.create(
            user=user,
            title="Role Switch.",
            message="Account type switched to Partner successfully.",
        )

        ActivityModel.objects.create(
            user=user,
            title="Role Switch.",
            description=f"{user.first_name} {user.last_name} switched account type from {user.active_role} to Partner.",
        )

        # User has a Partner account type, switch the role
        user.active_role = "Partner"
        user.save()

        data = {
            "status": "success",
            "message": "Account type switched to Partner successfully.",
            "data": user.active_role,
        }
        logger.info(
            "User  %s successfully switched account type to Partner.", user.email
        )
        return Response(data=encrypt(data), status=status.HTTP_200_OK)


@extend_schema(
    summary="Switch active role to BrandAd",
    tags=["Profile"],
    description="Switches the authenticated user's active role to BrandAd. The user must already be registered with a BrandAd account type.",
    responses={
        200: inline_serializer(
            name="SwitchToBrandAdResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "data": s.CharField(),
            },
        ),
        400: inline_serializer(
            name="SwitchToBrandAdError",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class SwitchToBrandAd(generics.RetrieveAPIView):
    """
    SwitchToBrandAd is the PUT request method for updating and switching
    to a BrandAd account type.
    """

    serializer_class = SwitchToBrandAdSerializer
    permission_classes = (IsAuthenticated,)

    def get_object(self):
        return self.request.user

    def put(self, request):
        user = self.get_object()
        logger.info("User  %s is attempting to switch account type.", user.email)

        try:
            account_types = AccountType.objects.filter(user=user)
            logger.debug(
                "Account types retrieved for user %s: %s", user.email, account_types
            )

            # Check if any AccountType has "BrandAd" in user_type
            is_brandAd = any(acct.user_type == "BrandAd" for acct in account_types)

            if not is_brandAd:
                data = {
                    "status": "fail",
                    "message": "Oops, you haven't registered as a BrandAd yet.",
                    "data": user.active_role,
                }
                logger.warning(
                    "User  %s attempted to switch to BrandAd but is not registered as one.",
                    user.email,
                )
                return Response(data=encrypt(data), status=status.HTTP_400_BAD_REQUEST)

        except AccountType.DoesNotExist:
            logger.error("AccountType for user %s does not exist.", user.email)
            raise exceptions.ValidationError(
                encrypt("AccountType for the user does not exist.")
            )

        # Handle already switched to BrandAd
        if user.active_role == "BrandAd":
            data = {
                "status": "success",
                "message": "You are already on the BrandAd screen.",
                "data": user.active_role,
            }
            logger.info("User  %s is already on the BrandAd screen.", user.email)
            return Response(data=encrypt(data), status=status.HTTP_200_OK)

        # Log the switch action
        logger.info(
            "User  %s is switching account type from %s to BrandAd.",
            user.email,
            user.active_role,
        )

        UserNotification.objects.create(
            user=user,
            title="Role Switch.",
            message="Account type switched to BrandAd successfully.",
        )

        ActivityModel.objects.create(
            user=user,
            title="Role Switch.",
            description=f"{user.first_name} {user.last_name} switched account type from {user.active_role} to BrandAd.",
        )

        # Switch the role to BrandAd
        user.active_role = "BrandAd"
        user.save()

        data = {
            "status": "success",
            "message": "Account type switched to BrandAd successfully.",
            "data": user.active_role,
        }
        logger.info(
            "User  %s successfully switched account type to BrandAd.", user.email
        )
        return Response(data=encrypt(data), status=status.HTTP_200_OK)


@extend_schema(
    summary="Upload or update profile image",
    tags=["Profile"],
    description="Updates the authenticated user's profile image URL. Accepts a base64 URL or CDN URL to the new profile picture.",
    request=ProfileImageSerializer,
    responses={
        200: inline_serializer(
            name="ProfileImageResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        400: inline_serializer(
            name="ProfileImageError",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class ProfileImage(generics.UpdateAPIView):
    """
    Upload profile image.
    """

    serializer_class = ProfileImageSerializer
    permission_classes = (IsAuthenticated,)

    def update(self, request, *args, **kwargs):
        logger.info(
            "User %s is attempting to upload a profile image.", request.user.email
        )

        decrypted_payload = decrypt(request.data)
        payload = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_payload.items()
        }
        # Get the user instance
        user = request.user

        # Use the serializer with the instance
        serializer = self.get_serializer(data=payload)

        if serializer.is_valid():
            # Update the user's profile image.
            user.profile_img_url = payload.get("profile_img_url")
            user.save()

            UserNotification.objects.create(
                user=user,
                title="Profile Image.",
                message="You have successfully updated your profile image.",
            )

            ActivityModel.objects.create(
                user=user,
                title="Profile Image.",
                description=f"{user.first_name} {user.last_name} updated their profile image.",
            )

            response = {
                "status": "success",
                "message": "Profile picture updated successfully",
            }
            logger.info("User %s updated their profile image successfully.", user.email)
            return Response(data=encrypt(response), status=status.HTTP_200_OK)

        logger.warning(
            "Profile image update failed for user %s: %s", user.email, serializer.errors
        )
        return Response(
            data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST
        )


@extend_schema(
    summary="Set preferred alert type (SMS, Email, or Both)",
    tags=["Profile"],
    description="Sets the user's preferred notification channel for transaction alerts. Accepted values are SMS, Email, or Both.",
    request=SetAlertTypeSerializer,
    responses={
        200: inline_serializer(
            name="ChooseAlertTypeResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        400: inline_serializer(
            name="ChooseAlertTypeError",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class ChooseAlertTypeView(generics.GenericAPIView):
    """ChooseAlertTypeView is the POST request method that allows
    users to choose their preferred alert type.
    """

    serializer_class = SetAlertTypeSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request):
        authenticated_user = request.user
        decrypted_payload = decrypt(request.data)

        alert_choice = decrypted_payload.get("alert_type_choice")

        if not alert_choice:
            resp = {
                "status": "fail",
                "message": "It cannot be empty, it has to be 'SMS', 'Email' or 'Both'",
            }
            return Response(data=encrypt(resp), status=status.HTTP_400_BAD_REQUEST)

        serializer = SetAlertTypeSerializer(data=decrypted_payload)
        if not serializer.is_valid(raise_exception=True):
            return Response(
                data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST
            )

        authenticated_user.alert_type_choice = alert_choice
        authenticated_user.save()

        response = {
            "status": "success",
            "message": "Preferred alert type selected sucessfully!.",
            "data": {"user_id": authenticated_user.id, "alert choice": alert_choice},
        }
        return Response(data=encrypt(response), status=status.HTTP_200_OK)


@extend_schema(
    summary="Get authenticated user profile details",
    tags=["Profile"],
    description="Returns the full profile information for the currently authenticated user.",
    responses={200: GetUserSerializer},
)
class GetUserDetails(generics.RetrieveAPIView):
    """User Detials"""

    serializer_class = GetUserSerializer
    permission_classes = (IsAuthenticated,)

    def retrieve(self, request, *args, **kwargs):
        user = self.request.user  # Get the authenticated user
        serializer = self.get_serializer(user)
        return Response(data=encrypt(serializer.data), status=status.HTTP_200_OK)


@extend_schema(
    summary="Update user profile",
    tags=["Profile"],
    description="Updates editable fields on the authenticated user's profile. Sends a confirmation email on success.",
    request=UpdateUserSerializer,
    responses={
        200: inline_serializer(
            name="UpdateProfileResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        400: inline_serializer(
            name="UserProfileUpdateProfileError",
            fields={"status": s.CharField(), "errors": s.DictField()},
        ),
    },
)
class UpdateUserProfile(generics.UpdateAPIView):
    """Update User Profile"""

    serializer_class = UpdateUserSerializer
    permission_classes = (IsAuthenticated,)

    def get_object(self):
        return self.request.user

    def update(self, request, *args, **kwargs):
        logger.info(
            "User  %s is attempting to update their profile.", request.user.email
        )

        kwargs.pop("partial", None)
        instance = self.get_object()

        try:
            decrypted_payload = decrypt(request.data)
            payload = {
                key: value.strip() if isinstance(value, str) else value
                for key, value in decrypted_payload.items()
            }
            payload = {key: value for key, value in payload.items() if value != ""}

            # Always partial: this endpoint edits whichever fields were
            # sent, not a full profile replacement - true independent of
            # whether the client calls PUT or PATCH.
            serializer = self.get_serializer(instance, data=payload, partial=True)
            serializer.is_valid(raise_exception=True)
            self.perform_update(serializer)

            # Create user notification
            UserNotification.objects.create(
                user=request.user,
                title="Update Profile",
                message="You have successfully updated your profile.",
            )

            # Log the profile update activity
            ActivityModel.objects.create(
                user=request.user,
                title="Update Profile.",
                description=f"{request.user.first_name} {request.user.last_name} updated their profile.",
            )

            body = "This is to inform you that your profile on Picadailys has been updated. If you didn't perform this action, kindly reply to this email or send an email to support@picadailys.com."

            text_content = render_to_string(
                template_name="empty_email.html",
                context={
                    "custom_text": f"Dear {request.user.first_name},<br><br>{body}.",
                    "support_email": "support@picadailys.com",
                    "picadailys_phone": [
                        "02012271894",
                        "02012271895",
                    ],
                },
            )

            Messaging.send_email(
                sender_email="notifications@picadailys.com",
                body=body,
                email=request.user.email,
                html_content=text_content,
                subject="Profile Update",
            )

            logger.info(
                "User  %s successfully updated their profile.", request.user.email
            )
            return Response(
                data=encrypt(
                    {
                        "status": "success",
                        "message": "profile updated",
                        "data": serializer.data,
                    }
                ),
                status=status.HTTP_200_OK,
            )

        except ValidationError as validation_error:
            logger.warning(
                "Validation failed for user %s: %s",
                request.user.email,
                str(validation_error),
            )
            return Response(
                data=encrypt({"status": "fail", "errors": validation_error.detail}),
                status=status.HTTP_400_BAD_REQUEST,
            )

        except Exception as e:
            logger.error(
                "Error updating profile for user %s: %s", request.user.email, str(e)
            )
            return Response(
                data=encrypt({"status": "fail", "message": "Profile update failed."}),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


@extend_schema(
    summary="Change account password",
    tags=["Profile"],
    description="Changes the authenticated user's password. The old password is verified first, and the existing refresh token is blacklisted on success.",
    request=ChangePasswordSerializer,
    responses={
        200: inline_serializer(
            name="ChangePasswordResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        400: inline_serializer(
            name="ChangePasswordError",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class ChangePassword(generics.UpdateAPIView):
    serializer_class = ChangePasswordSerializer
    permission_classes = (IsAuthenticated,)
    throttle_scope = "password_change"

    def update(self, request, *args, **kwargs):
        logger.info(
            "User  %s is attempting to change their password.", request.user.email
        )

        decrypted_payload = decrypt(request.data)
        payload = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_payload.items()
        }

        user = request.user
        serializer = ChangePasswordSerializer(data=payload)

        if serializer.is_valid():
            old_password = serializer.validated_data["old_password"]
            new_password = serializer.validated_data["new_password"]

            # Check if the old password is correct
            if not check_password(old_password, user.password):
                response = {"status": "fail", "message": "Old password is incorrect."}
                logger.warning(
                    "User  %s provided an incorrect old password.", user.email
                )
                return Response(
                    data=encrypt(response), status=status.HTTP_400_BAD_REQUEST
                )

            # Update the user's password
            user.set_password(new_password)

            # Retrieve existing tokens and blacklist them
            user_token = payload.get("refresh_token")
            if user_token:
                try:
                    token = RefreshToken(user_token)
                    token.blacklist()
                    logger.info(
                        "User  %s's refresh token has been blacklisted.", user.email
                    )
                except Exception as e:
                    logger.error(
                        "Error blacklisting token for user %s: %s", user.email, str(e)
                    )

            user.save()

            # Create user notification
            UserNotification.objects.create(
                user=request.user,
                title="Change Password.",
                message="You have successfully changed your password.",
            )

            send_push_to_user(
                user=request.user,
                title="Password Changed 🔒",
                body="Your Picadailys password was just changed. If this wasn't you, contact support immediately.",
                data={"type": "password_changed"},
            )

            # Log the password change activity
            ActivityModel.objects.create(
                user=request.user,
                title="Change Password.",
                description=f"{request.user.first_name} {request.user.last_name} changed their password.",
            )

            body = "This is to inform you that your password on Picadailys has been updated."

            if request.user.alert_type_choice in ("SMS", "Both"):
                Messaging.send_sms(phone_number=request.user.phone_number[1:], msg=body)
            if request.user.alert_type_choice in ("Email", "Both"):
                # Render the template with values
                text_content = render_to_string(
                    template_name="empty_email.html",
                    context={
                        "custom_text": f"Dear {request.user.first_name},<br><br>{body}.",
                        "support_email": "support@picadailys.com",
                        "picadailys_phone": "02012271894  02012271895",
                    },
                )

                Messaging.send_email(
                    sender_email="notifications@picadailys.com",
                    body=body,
                    email=request.user.email,
                    html_content=text_content,
                    subject="Password Change",
                )

            response = {
                "status": "success",
                "message": "Password updated successfully.",
            }
            logger.info("User  %s successfully changed their password.", user.email)
            return Response(data=encrypt(response), status=status.HTTP_200_OK)

        logger.warning(
            "Password change failed for user %s: %s", user.email, serializer.errors
        )
        return Response(
            data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST
        )


# class MemberUserSwitch(generics.UpdateAPIView):
#     serializer_class = ProfileStatusSerializer
#     authentication_classes = [JWTAuthentication]
#     permission_classes = (IsAuthenticated,)

#     @extend_schema(
#         description="Member-User switch",
#         responses={200: {"description": "User and member switch."}},
#     )
#     def get_object(self):
#         return self.request.user

#     def put(self, request):
#         user = self.get_object()
#         logger.info(
#             f"User {user.first_name} {user.last_name} initiated a role switch request."
#         )

#         game_point = Points.objects.get(user=user)

#         if user.active_role == "User ":
#             try:
#                 logger.info(
#                     f"User {user.first_name} {user.last_name} has current balance: {game_point.balance}"
#                 )

#                 if game_point.balance is not None:
#                     if game_point.balance >= 10.0:
#                         AccountType.objects.update_or_create(
#                             user_type="Partners",
#                         )

#                         user.active_role = "Member"
#                         game_point.balance -= 10.0
#                         user.save()
#                         game_point.save()  # Don't forget to save the updated game_point

#                         UserNotification.objects.create(
#                             user=request.user,
#                             title="Member Switch.",
#                             message="Congratulations you have been upgraded to a member. You can now engage in gamifications and enjoy amazing discounts and offers with us.",
#                         )

#                         ActivityModel.objects.create(
#                             user=request.user,
#                             title="Member Switch.",
#                             description=f"{request.user.first_name} {request.user.last_name} switched from User to Member.",
#                         )

#                         resp = {
#                             "status": "success!",
#                             "data": "Congratulations you have been upgraded to a member. You can now engage in gamifications and enjoy amazing discounts and offers with us.",
#                         }
#                         logger.info(
#                             f"User {user.first_name} {user.last_name} successfully upgraded to Member."
#                         )
#                         return Response(data=encrypt(resp), status=status.HTTP_200_OK)
#                     else:
#                         resp = {
#                             "status": "fail",
#                             "error": "You do not have enough points.",
#                         }
#                         logger.warning(
#                             f"User {user.first_name} {user.last_name} attempted to switch roles but does not have enough points."
#                         )
#                         return Response(
#                             data=encrypt(resp), status=status.HTTP_400_BAD_REQUEST
#                         )
#                 else:
#                     resp = {
#                         "status": "fail!",
#                         "error": "You have not started earning points.",
#                     }
#                     logger.warning(
#                         f"User {user.first_name} {user.last_name} has not started earning points."
#                     )
#                     return Response(
#                         data=encrypt(resp), status=status.HTTP_400_BAD_REQUEST
#                     )

#             except Exception as e:
#                 logger.error(
#                     f"An error occurred while processing the role switch for user {user.first_name} {user.last_name}: {str(e)}"
#                 )
#                 return Response(
#                     data=encrypt({"error": str(e)}),
#                     status=status.HTTP_500_INTERNAL_SERVER_ERROR,
#                 )
#         elif user.active_role == "Member":
#             user.active_role = "User "
#             user.save()
#             logger.info(
#                 f"User {user.first_name} {user.last_name} switched from Member to User."
#             )
#             return Response(
#                 data=encrypt(
#                     {
#                         "status": "success",
#                         "message": "Member has been switched to a User.",
#                     }
#                 ),
#                 status=status.HTTP_200_OK,
#             )


@extend_schema(
    summary="Submit member onboarding survey",
    tags=["Profile"],
    description="Records the member onboarding survey answers and social media handles. Only accessible to users with the Member role.",
    request=MemberSurveySerializers,
    responses={
        201: inline_serializer(
            name="PostMemberSurveyResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        400: inline_serializer(
            name="PostMemberSurveyError",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class PostMemberSurvey(generics.CreateAPIView):
    """
    PostMemberSurvey handles POST request of conducting member survey.
    """

    serializer_class = MemberSurveySerializers
    permission_classes = (IsAuthenticated, IsMember)

    def create(self, request, *args, **kwargs):
        user = request.user

        decrypted_payload = decrypt(request.data)
        payload = {
            k: v.strip() if isinstance(v, str) else v
            for k, v in decrypted_payload.items()
        }

        serializer = self.get_serializer(
            data=payload,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)

        try:
            MemberSurveyService.complete_member_survey(
                user=user,
                serializer=serializer,
            )
        except (ValidationError, DjangoValidationError) as e:
            message = (
                e.messages[0]
                if hasattr(e, "messages")
                else (e.detail[0] if hasattr(e, "detail") else str(e))
            )
            logger.error("Member survey validation error: %s", message)
            return Response(
                encrypt({"status": "fail", "message": message}),
                status=status.HTTP_400_BAD_REQUEST,
            )

        response = {
            "status": "success",
            "message": "Survey completed successfully!",
            "data": serializer.data,
        }

        return Response(
            encrypt(response),
            status=status.HTTP_201_CREATED,
        )


HANDLE_FIELDS = {
    "facebook_handle",
    "twitter_handle",
    "instagram_handle",
    "tiktok_handle",
    "youtube_handle",
    "linkedin_handle",
}


@extend_schema(
    summary="Get or update social profile handles",
    tags=["Profile"],
    description="Retrieves or updates the authenticated user's linked social media handles. Handle changes require admin approval; submit a handle change request first.",
    request=MemberSurveySerializers,
    responses={
        200: MemberSurveySerializers,
        403: inline_serializer(
            name="SocialProfileForbidden",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class SocialProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = MemberSurveySerializers
    permission_classes = [IsAuthenticated]

    def get_object(self):
        profile, _ = MemberSurvey.objects.get_or_create(user=self.request.user)
        return profile

    def _check_handle_change_allowed(self, data):
        if any(f in data for f in HANDLE_FIELDS):
            profile, _ = MemberSurvey.objects.get_or_create(user=self.request.user)
            if not profile.allow_handle_change:
                return False
        return True

    def patch(self, request, *args, **kwargs):
        if not self._check_handle_change_allowed(request.data):
            return Response(
                {
                    "status": "fail",
                    "message": "Handle changes require admin approval. Please submit a handle change request.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        response = super().partial_update(request, *args, **kwargs)
        # Reset flag after successful handle update
        if response.status_code == 200:
            MemberSurvey.objects.filter(user=request.user).update(
                allow_handle_change=False
            )
        return response

    def put(self, request, *args, **kwargs):
        if not self._check_handle_change_allowed(request.data):
            return Response(
                {
                    "status": "fail",
                    "message": "Handle changes require admin approval. Please submit a handle change request.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        response = super().update(request, *args, **kwargs)
        if response.status_code == 200:
            MemberSurvey.objects.filter(user=request.user).update(
                allow_handle_change=False
            )
        return response


@extend_schema(
    summary="Submit a social handle for the first time",
    tags=["Profile"],
    description=(
        "Sets a social handle for a platform the member has never linked before — used when "
        "they open a task for a platform with no handle on file yet. Only works while that "
        "platform's handle is still blank; changing a handle that's already set requires an "
        "admin-approved handle change request instead."
    ),
    request=SubmitSocialHandleSerializer,
    responses={
        201: MemberSurveySerializers,
        409: inline_serializer(
            name="SocialHandleAlreadySet",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class SubmitSocialHandleView(generics.GenericAPIView):
    serializer_class = SubmitSocialHandleSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        decrypted_payload = decrypt(request.data)

        serializer = self.get_serializer(data=decrypted_payload)
        serializer.is_valid(raise_exception=True)

        platform = serializer.validated_data["platform"]
        handle = serializer.validated_data["handle"].strip()
        field_name = PLATFORM_HANDLE_FIELDS[platform]

        profile, _ = MemberSurvey.objects.get_or_create(user=request.user)

        if getattr(profile, field_name):
            return Response(
                encrypt(
                    {
                        "status": "fail",
                        "message": (
                            f"You already have a {platform} handle on file. "
                            "Submit a handle change request to update it."
                        ),
                    }
                ),
                status=status.HTTP_409_CONFLICT,
            )

        setattr(profile, field_name, handle)
        profile.save(update_fields=[field_name])

        response = {
            "status": "success",
            "message": f"{platform} handle saved.",
            "data": MemberSurveySerializers(profile).data,
        }
        return Response(encrypt(response), status=status.HTTP_201_CREATED)


@extend_schema(
    summary="Request a social handle change",
    tags=["Profile"],
    description="Submits a request to change a social media handle. Admins are notified via push notification; only one pending request per platform is allowed.",
    request=HandleChangeRequestSerializer,
    responses={
        201: HandleChangeRequestSerializer,
        400: inline_serializer(
            name="HandleChangeRequestError",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class RequestHandleChangeView(generics.CreateAPIView):
    serializer_class = HandleChangeRequestSerializer
    permission_classes = [IsAuthenticated]

    def create(self, request, *args, **kwargs):
        decrypted_payload = decrypt(request.data)
        payload = {
            k: v.strip() if isinstance(v, str) else v
            for k, v in decrypted_payload.items()
        }

        serializer = self.get_serializer(
            data=payload,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)

        pending_exists = HandleChangeRequest.objects.filter(
            user=request.user,
            platform=serializer.validated_data["platform"],
            status="pending",
        ).exists()
        if pending_exists:
            return Response(
                encrypt(
                    {
                        "status": "fail",
                        "message": "You already have a pending request for this platform.",
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        req = serializer.save(user=request.user)

        send_push_to_admins(
            title="Handle Change Request",
            body=f"{request.user.full_name or request.user.email} wants to change their {req.get_platform_display()} handle to '{req.new_handle}'.",
            data={"type": "handle_change_request", "request_id": str(req.id)},
        )

        response = (
            {
                "status": "success",
                "message": "Request submitted. You'll be notified once an admin reviews it.",
                "data": serializer.data,
            },
        )

        return Response(
            encrypt(response),
            status=status.HTTP_201_CREATED,
        )


@extend_schema(
    summary="Delete a user account (super admin only)",
    tags=["Profile"],
    description="Permanently deletes a user account. Requires super admin role and a valid X-Delete-Credentials header containing base64-encoded email:password.",
    responses={
        204: inline_serializer(
            name="DeleteUserResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        401: inline_serializer(
            name="DeleteUserUnauth",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        404: inline_serializer(
            name="DeleteUserNotFound",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class DeleteUser(generics.DestroyAPIView):
    serializer_class = DeleteUserSerializer
    permission_classes = (IsAuthenticated, IsSuperAdmin)

    def delete(self, request, *args, **kwargs):
        header = request.headers.get("X-Delete-Credentials")
        if not header:
            response = {
                "status": "fail",
                "message": "X-Delete-Credentials header is required",
            }
            return Response(data=encrypt(response), status=status.HTTP_401_UNAUTHORIZED)

        try:
            decoded = base64.b64decode(header).decode()
            email, password = decoded.split(":", 1)
        except Exception:
            response = {"status": "fail", "message": "Invalid credential format"}
            return Response(data=encrypt(response), status=status.HTTP_400_BAD_REQUEST)

        if not check_password(password, request.user.password):
            response = {"status": "fail", "message": "Incorrect password"}
            return Response(data=encrypt(response), status=status.HTTP_400_BAD_REQUEST)

        logger.info(
            f"User {self.request.user.first_name} {self.request.user.last_name} initiated account deletion request for email: {email}"
        )

        try:
            user = User.objects.get(Q(id=email) | Q(email=email))
            msg = "This is to inform you that there was an attempt to delete your account on Picadailys. If you didn't perform this action, kindly reply to this email or send an email to support@picadailys.com."

            if user.alert_type_choice in ("SMS", "Both"):
                Messaging.send_sms(phone_number=user.phone_number[1:], msg=msg)
            if user.alert_type_choice in ("Email", "Both"):
                # Render the template with values
                text_content = render_to_string(
                    template_name="empty_email.html",
                    context={
                        "custom_text": f"Dear {user.first_name},<br><br>{msg}.",
                        "support_email": "support@picadailys.com",
                        "picadailys_phone": "02012271894  02012271895",
                    },
                )

                Messaging.send_email(
                    sender_email="support@picadailys.com",
                    body=msg,
                    email=user.email,
                    html_content=text_content,
                    subject="Account Deletion",
                )
            logger.info(
                f"User found: {user.first_name} {user.last_name}. Proceeding with account deletion."
            )

            ActivityModel.objects.create(
                user=user,
                title="Delete Account.",
                description=f"{request.user.first_name} {request.user.last_name} has deleted their account.",
            )
            user.delete()
            logger.info(
                f"User {user.first_name} {user.last_name} has been deleted successfully."
            )

            recipient = user.phone_number[1:]
            Messaging.send_sms(
                phone_number=recipient,
                msg="This is to inform you that your account Picadailys has been deleted. We regret to lose you, we hope to see you again soon.",
            )
            response = {
                "status": "success",
                "message": f"Account with '{email}' deleted successfully.",
            }
            return Response(
                data=encrypt(response),
                status=status.HTTP_204_NO_CONTENT,
            )
        except User.DoesNotExist:
            logger.warning(
                f"Attempt to delete account failed: User with '{email}' does not exist."
            )
            resp = {
                "status": "fail",
                "message": f"User  with '{email}' does not exist.",
            }
            return Response(
                data=encrypt(resp),
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as e:
            logger.error(
                f"An error occurred while trying to delete user {email}: {str(e)}"
            )
            return Response(
                data=encrypt(
                    {"error": "An error occurred while deleting the account."}
                ),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


@extend_schema(
    summary="Delete own account",
    tags=["Profile"],
    description="Allows an authenticated user to permanently delete their own account. Requires password confirmation in the request body.",
    responses={
        200: inline_serializer(
            name="SelfDeleteAccountResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        400: inline_serializer(
            name="SelfDeleteAccountBadRequest",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class SelfDeleteAccount(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request):
        decrypted_payload = decrypt(request.data)
        password = decrypted_payload.get("password")
        refresh_token = decrypted_payload.get("refresh_token")

        if not password:
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "Password is required to delete your account.",
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = request.user
        if not check_password(password, user.password):
            return Response(
                data=encrypt({"status": "fail", "message": "Incorrect password."}),
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Blacklist the refresh token so it cannot be reused after account deletion
        if refresh_token:
            try:
                token = RefreshToken(refresh_token)
                token.blacklist()
            except Exception:
                pass

        # Send farewell notification before deleting (CASCADE will remove DB records)
        try:
            msg = (
                "Your Picadailys account has been permanently deleted. "
                "We hope to see you again. If this was not you, contact support@picadailys.com immediately."
            )
            if user.alert_type_choice in ("Email", "Both") and user.email:
                html = render_to_string(
                    "empty_email.html",
                    {
                        "custom_text": f"Dear {user.first_name},<br><br>{msg}",
                        "support_email": "support@picadailys.com",
                        "picadailys_phone": "02012271894 02012271895",
                    },
                )
                Messaging.send_email(
                    sender_email="support@picadailys.com",
                    body=msg,
                    email=user.email,
                    html_content=html,
                    subject="Account Deleted — Picadailys",
                )
            if user.alert_type_choice in ("SMS", "Both") and user.phone_number:
                Messaging.send_sms(phone_number=user.phone_number[1:], msg=msg)
        except Exception as e:
            logger.warning("Could not send account-deletion notification: %s", e)

        logger.info("User id=%s self-deleted their account.", user.id)
        user.delete()

        return Response(
            data=encrypt(
                {
                    "status": "success",
                    "message": "Your account has been permanently deleted.",
                }
            ),
            status=status.HTTP_200_OK,
        )


@extend_schema(
    summary="Open the mystery reward box",
    tags=["Profile"],
    description="Opens the mystery reward box if the authenticated Member user has at least 100 reward points. Returns the prize type ready to be claimed.",
    responses={
        200: inline_serializer(
            name="OpenRewardBoxResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        400: inline_serializer(
            name="OpenRewardBoxError",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class OpenRewardBox(generics.GenericAPIView):
    """
    OpenRewardBox is the GET request handler for opening the reward box.
    """

    serializer_class = OpenRewardBoxSerializers
    permission_classes = (IsAuthenticated, IsMember)

    def get(self, request):
        user = request.user
        logger.info(
            f"User {user.first_name} {user.last_name} initiated a request to open the mystery box."
        )

        try:
            user_reward = Rewards.objects.get(user=user)
            logger.info(
                f"User {user.first_name} {user.last_name} has a reward balance of {user_reward.balance}."
            )

            if user_reward.balance >= 100:
                item, form = MysteryBox.open()
                user_reward.mystery_box = item
                user_reward.form_of_gift = form
                user_reward.save()

                response_data = {
                    "status": "success",
                    "message": "Wow, you have an item in your box, click to claim reward!",
                }

                UserNotification.objects.create(
                    user=request.user,
                    title="Mystery Box.",
                    message="Congratulations, you have an item in your box, click to claim reward!",
                )

                ActivityModel.objects.create(
                    user=user,
                    title="Mystery Box.",
                    description=f"{request.user.first_name} {request.user.last_name} has opened their mystery box.",
                )

                logger.info(
                    f"User {user.first_name} {user.last_name} opened the mystery box and received an item."
                )
                return Response(data=response_data, status=status.HTTP_200_OK)

            elif user_reward.balance < 100:
                logger.warning(
                    f"User {user.first_name} {user.last_name} attempted to open the mystery box but does not have enough rewards."
                )
                raise exceptions.ValidationError(
                    encrypt(detail="Not enough rewards to access the mystery box."),
                    code=status.HTTP_400_BAD_REQUEST,
                )

        except Rewards.DoesNotExist:
            logger.error(
                f"Rewards record not found for user {user.first_name} {user.last_name}."
            )
            return Response(
                data=encrypt(
                    {"status": "fail", "message": "Rewards record not found."}
                ),
                status=status.HTTP_404_NOT_FOUND,
            )
        except exceptions.ValidationError as ve:
            logger.warning(
                f"Validation error for user {user.first_name} {user.last_name}: {str(ve)}"
            )
            return Response(
                data=encrypt({"status": "fail", "message": str(ve.detail)}),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            logger.error(
                f"An unexpected error occurred while processing the mystery box for user {user.first_name} {user.last_name}: {str(e)}"
            )
            return Response(
                data=encrypt({"error": "An unexpected error occurred."}),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


@extend_schema(
    summary="Claim mystery box reward (airtime or data)",
    tags=["Profile"],
    description="Redeems the mystery box reward as airtime or data for the specified phone number and network. Requires the box to have been opened first.",
    request=ClaimRewardSerializers,
    responses={
        200: inline_serializer(
            name="ClaimGiftResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        400: inline_serializer(
            name="ClaimGiftError",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class ClaimMysteryBoxGift(generics.GenericAPIView):
    """
    ClaimMysteryBoxGift is the GET request handler for allowing a
    user to claim their reward.
    """

    serializer_class = ClaimRewardSerializers
    permission_classes = (IsAuthenticated, IsMember)

    def get(self, request):
        authenticated_user = request.user
        logger.info(
            f"User {authenticated_user.first_name} {authenticated_user.last_name} initiated a gift claim request."
        )

        decrypted_payload = decrypt(request.user)
        user_data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_payload.items()
        }

        serializer = self.get_serializer(data=user_data)

        if serializer.is_valid(raise_exception=True):
            user_reward = Rewards.objects.get(user=authenticated_user)
            logger.info(
                f"User {authenticated_user.first_name} {authenticated_user.last_name} has valid data. Reward type: {user_reward.form_of_gift}"
            )

            match user_reward.form_of_gift:
                case "airtime":
                    amount = Rewards.objects.get(user=authenticated_user)
                    logger.info(
                        f"Processing airtime for user {authenticated_user.first_name} {authenticated_user.last_name}, amount: {amount.mystery_box}"
                    )

                    airtime_response = VAS.aritime(
                        service_id=user_data["serviceID"],
                        amount=amount.mystery_box,
                        phone=user_data["phone"],
                    )

                    if airtime_response.status_code == 200:
                        UserNotification.objects.create(
                            user=authenticated_user,
                            title="Claim Gift box reward.",
                            message="You have successfully claimed your mystery box item.",
                        )

                        ActivityModel.objects.create(
                            user=authenticated_user,
                            title="Claim Gift box reward.",
                            description=f"{authenticated_user.first_name} {authenticated_user.last_name} claimed their mystery box item of {amount.mystery_box} airtime.",
                        )

                        response_data = {
                            "status": "Success",
                            "message": f"Recharge of {amount} was successful. continue to purchase items to get rewards.",
                            "data": airtime_response.json(),
                        }
                        logger.info(
                            f"Airtime claim successful for user {authenticated_user.first_name} {authenticated_user.last_name}: {response_data}"
                        )
                        return Response(
                            data=encrypt(response_data), status=status.HTTP_200_OK
                        )

                case "data":
                    amount = Rewards.objects.get(user=authenticated_user)
                    variation_code = VariationCodes.get(
                        service_id=user_data["serviceID"], amount=amount.mystery_box
                    )
                    logger.info(
                        f"Processing data for user {authenticated_user.first_name} {authenticated_user.last_name}, amount: {amount.mystery_box}"
                    )

                    data_response = VAS.data(
                        service_id=user_data["serviceID"],
                        amount=amount.mystery_box,
                        phone=user_data["phone"],
                        billersCode=user_data["phone"],
                        variation_code=variation_code,
                    )

                    if data_response.status_code == 200:
                        UserNotification.objects.create(
                            user=authenticated_user,
                            title="Claim Gift box reward.",
                            message="You have successfully claimed your mystery box item.",
                        )

                        ActivityModel.objects.create(
                            user=authenticated_user,
                            title="Claim Gift box reward.",
                            description=f"{authenticated_user.first_name} {authenticated_user.last_name} claimed their mystery box item of {amount.mystery_box} data subscription.",
                        )

                        response = {
                            "status": "Success",
                            "message": f"Data subscription of {amount} was successful. continue to purchase items to get rewards.",
                            "data": data_response.json(),
                        }
                        logger.info(
                            f"Data claim successful for user {authenticated_user.first_name} {authenticated_user.last_name}: {response}"
                        )
                        return Response(
                            data=encrypt(response), status=status.HTTP_200_OK
                        )
                    else:
                        response = {
                            "status": "fail",
                            "message": f"Data subscription of {amount} was unsuccessful.",
                            "data": data_response.json(),
                        }
                        logger.error(
                            f"Data claim failed for user {authenticated_user.first_name} {authenticated_user.last_name}: {response}"
                        )
                        return Response(
                            data=encrypt(response), status=data_response.status_code
                        )

                case _:
                    logger.warning(
                        f"Invalid option for user {authenticated_user.first_name} {authenticated_user.last_name}."
                    )
                    return Response(
                        data=encrypt({"status": "fail", "message": "Invalid option"}),
                        status=status.HTTP_400_BAD_REQUEST,
                    )
        else:
            logger.error(
                f"Validation failed for user {authenticated_user.first_name} {authenticated_user.last_name}: {serializer.errors}"
            )
            return Response(
                data=encrypt(serializer.errors), status=status.HTTP_404_NOT_FOUND
            )


@extend_schema(
    summary="Add a product or service to favourites",
    tags=["Profile"],
    description="Adds a purchased product or service to the authenticated user's favourites list. Requires both object_id and model_name fields identifying the item.",
    request=AddToFavouriteSerializer,
    responses={
        201: inline_serializer(
            name="AddToFavouriteResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        200: inline_serializer(
            name="AlreadyFavouriteResponse", fields={"message": s.CharField()}
        ),
        400: inline_serializer(
            name="AddToFavouriteError",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class AddToFavourite(generics.CreateAPIView):
    """
    AddToFavourite is the POST request handler for allowing a
    user to add a product to his favourite list.
    """

    serializer_class = AddToFavouriteSerializer
    permission_classes = (IsAuthenticated,)

    def post(self, request, *args, **kwargs):
        logger.info("User  %s is attempting to favorite an item.", request.user.email)

        authenticated_user = request.user
        decrypted_payload = decrypt(request.data)

        object_id = decrypted_payload.get("object_id")
        model_name = decrypted_payload.get("model_name")

        serializer = FavouriteSerializer(data=decrypted_payload)
        if serializer.is_valid(raise_exception=True):
            if not object_id or not model_name:
                logger.warning(
                    "User  %s did not provide both object_id and model_name.",
                    authenticated_user.email,
                )
                raise ValidationError(
                    encrypt("Both object_id and model_name are required.")
                )

            # Map model_name to actual model classes
            model_mapping = {
                "Product": Product,
                "AirtimeTopup": ValueAddedServices,
                "DataSubscription": ValueAddedServices,
                "ElectricityBill": ValueAddedServices,
                "TvSubscription": ValueAddedServices,
                "RestaurantBooking": RestaurantBooking,
                "GymSubcription": GymSubcription,
                "CinemaBooking": CinemaBooking,
                "CourierService": CourierService,
                "ConsumableService": ConsumableService,
                "LandTravels": LandTravels,
                "Hotels": Hotels,
            }

            # Get the model class from the model name
            model_class = model_mapping.get(model_name)
            if not model_class:
                logger.warning(
                    "User  %s provided an invalid model_name.", authenticated_user.email
                )
                raise ValidationError(encrypt(f"Model '{model_name}' is not valid."))

            content_type = ContentType.objects.get_for_model(model_class)

            try:
                service_object = model_class.objects.get(id=object_id)
            except model_class.DoesNotExist:
                logger.warning(
                    "User  %s tried to favorite a non-existent object with id '%s'.",
                    authenticated_user.email,
                    object_id,
                )
                raise ValidationError(
                    encrypt(f"Object with id '{object_id}' not found.")
                )

            # Check if the user has purchased the item before allowing it to be favorited
            if not service_object.purchased:
                logger.warning(
                    "User  %s tried to favorite an unpurchased item.",
                    authenticated_user.email,
                )
                raise ValidationError(
                    encrypt("You can only favorite items you have purchased.")
                )

            # Create the favorite entry
            favourite, created = Favourite.objects.get_or_create(
                user=authenticated_user,
                content_type=content_type,
                object_id=service_object.id,
            )

            if created:
                logger.info(
                    "User   %s successfully favorited an item.",
                    authenticated_user.email,
                )
                return Response(
                    data=encrypt(
                        {"status": "success", "message": "Item favorited successfully!"}
                    ),
                    status=status.HTTP_201_CREATED,
                )
            else:
                logger.info(
                    "User  %s tried to favorite an already favorited item.",
                    authenticated_user.email,
                )
                return Response(
                    data=encrypt({"message": "Item is already in your favorites."}),
                    status=status.HTTP_200_OK,
                )
        else:
            logger.warning(
                "User  %s provided invalid data for favoriting an item.",
                authenticated_user.email,
            )
            return Response(
                data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST
            )


@extend_schema(
    summary="List all favourites for the authenticated user",
    tags=["Profile"],
    description="Returns all items saved as favourites by the authenticated user across all supported product and service categories.",
    responses={200: FavouriteSerializer(many=True)},
)
class ListFavourites(generics.ListAPIView):
    """
    List all favourites for the authenticated user.
    """

    serializer_class = FavouriteSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        logger.info("Fetching favorites for user: %s", user.email)

        queryset = Favourite.objects.filter(user=user)

        logger.debug(
            "Retrieved %d favorites for user: %s", queryset.count(), user.email
        )

        return queryset


@extend_schema(
    summary="Retrieve a specific favourite by ID",
    tags=["Profile"],
    description="Returns a single favourite item by its UUID. The item must belong to the authenticated user.",
    responses={
        200: FavouriteSerializer,
        404: inline_serializer(
            name="FavouriteNotFound",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class RetrieveFavourite(generics.RetrieveAPIView):
    """
    Retrieve a specific favourite by its ID.
    """

    serializer_class = FavouriteSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        logger.info("Fetching favorites for user: %s", user.email)

        queryset = Favourite.objects.filter(user=user)

        logger.debug(
            "Retrieved %d favorites for user: %s", queryset.count(), user.email
        )

        return queryset

    # Specify the field used for lookups
    lookup_field = "id"


@extend_schema(
    summary="Create a customer support ticket",
    tags=["Profile"],
    description="Creates a support ticket for the authenticated user. The ticket is placed in the queue and assigned a ticket number for tracking.",
    request=SupportTicketSerializer,
    responses={
        201: inline_serializer(
            name="UserProfileCreateTicketResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "data": inline_serializer(
                    name="TicketData",
                    fields={
                        "Ticket Number": s.CharField(),
                        "Category": s.CharField(),
                        "Status": s.CharField(),
                    },
                ),
            },
        ),
        400: inline_serializer(
            name="UserProfileCreateTicketError",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class CustomerTicketCreation(generics.GenericAPIView):
    """
    CustomerTicketCreation is the POST request handler for allowing a
    user to create a support ticket.
    """

    serializer_class = SupportTicketSerializer
    permission_classes = (IsAuthenticated,)

    def post(self, request, *args, **kwargs):
        logger.info(
            "User  %s is attempting to create a support ticket.", request.user.email
        )

        decrypted_payload = decrypt(request.data)
        payload = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_payload.items()
        }

        serializer = self.get_serializer(data=payload)
        if not serializer.is_valid(raise_exception=True):
            logger.warning(
                "User  %s provided invalid data for creating a support ticket.",
                request.user.email,
            )
            return Response(
                data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST
            )

        category = payload.get("category")
        ticket = Ticket.objects.create(
            user=request.user,
            title=f"{category} support request" if category else "Support request",
            description=payload.get("description"),
            category=category,
            resolution_hours=5,
            status="Queuing",
            channel="App",
            priority="Low",
        )

        UserNotification.objects.create(
            user=request.user,
            title="Create Ticket.",
            message="You have successfully created a support ticket.",
        )

        ActivityModel.objects.create(
            user=request.user,
            title="Create Ticket.",
            description=f"{request.user.first_name}  with email {request.user.email} has successfully created a support ticket.",
        )

        return Response(
            data=encrypt(
                {
                    "status": "success",
                    "message": "Support ticket created successfully, support will get back to you soon.",
                    "data": {
                        "Ticket Number": ticket.number,
                        "Category": payload.get("category"),
                        "Description": payload.get("description"),
                        "Duration": "2 hours",
                        "Channel": "App",
                        "Escalation Level": "Management",
                        "Status": "Queuing",
                    },
                }
            ),
            status=status.HTTP_201_CREATED,
        )


@extend_schema(
    summary="Rate a support agent after ticket resolution",
    tags=["Profile"],
    description="Allows the authenticated user to rate the support agent who resolved their ticket. The ticket must be resolved and the user must not have already submitted a rating.",
    request=AgentRatingSerializers,
    responses={
        201: inline_serializer(
            name="RateAgentResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        400: inline_serializer(
            name="RateAgentError",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        404: inline_serializer(
            name="RateAgentNotFound",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class RateAgentViewByCustomer(generics.GenericAPIView):
    serializer_class = AgentRatingSerializers
    permission_classes = (IsAuthenticated,)

    def post(self, request, *args, **kwargs):

        decrypted_payload = decrypt(request.data)
        ticket_id = decrypted_payload.get("ticket_id")
        rating = decrypted_payload.get("rating")
        rating_comment = decrypted_payload.get("rating_comment")

        try:
            ticket = Ticket.objects.get(id=ticket_id, deleted=False)
        except Ticket.DoesNotExist:
            return Response(
                encrypt({"status": "fail", "message": "Ticket not found"}),
                status=status.HTTP_404_NOT_FOUND,
            )

        if ticket.user != request.user:
            return Response(
                encrypt(
                    {
                        "status": "fail",
                        "message": "Unauthorized action; you can only rate agents for your own tickets",
                    }
                ),
                status=status.HTTP_403_FORBIDDEN,
            )

        if ticket.status != "Resolved":
            return Response(
                encrypt({"status": "fail", "message": "Ticket is not resolved yet"}),
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not ticket.resolved_by:
            return Response(
                encrypt(
                    {"status": "fail", "message": "No agent assigned to this ticket"}
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        if AgentRating.objects.filter(user=request.user, ticket=ticket).exists():
            return Response(
                encrypt(
                    {"status": "fail", "message": "You have already rated this ticket"}
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Create rating
        AgentRating.objects.create(
            user=request.user,
            agent=ticket.resolved_by,
            ticket=ticket,
            rating=rating,
            rating_comment=rating_comment,
        )

        return Response(
            encrypt(
                {
                    "status": "success",
                    "message": f"Agent {ticket.resolved_by} rated successfully for ticket {ticket.number}",
                }
            ),
            status=status.HTTP_201_CREATED,
        )


example_response = OpenApiExample(
    name="TierResponseExample",
    value={
        "status": "success",
        "message": "Tier levels retrieved successfully!",
        "data": {
            "current_level": "Explorer",
            "total_points": 750,
            "tiers": LEVELS,
        },
    },
    response_only=True,
)


@extend_schema_view(
    retrieve=extend_schema(
        tags=["Profile"],
        responses={200: TierListResponseSerializer},
        examples=[example_response],
        description="Returns all tier levels with required points and the current level of the user.",
        summary="Get user tier levels",
    )
)
class TierListView(generics.RetrieveAPIView):
    serializer_class = TierListResponseSerializer
    permission_classes = [IsAuthenticated]

    def retrieve(self, request, *args, **kwargs):
        user = request.user
        points = getattr(user, "points", None)

        response = {
            "status": "success",
            "message": "Tier levels retrieved successfully!",
            "data": {
                "current_level": points.tier if points else "Starter",
                "total_points": user.total_points,
                "tiers": LEVELS,
            },
        }
        return Response(data=encrypt(response), status=status.HTTP_200_OK)


logger_fcm = logging.getLogger(__name__)


@extend_schema(
    summary="Register or remove an FCM device push token",
    tags=["Profile"],
    description="POST to save or refresh an FCM push token for the authenticated user. DELETE to remove the token on logout. Supports android, ios, and web platforms.",
    request=inline_serializer(
        name="DeviceTokenRequest",
        fields={
            "token": s.CharField(),
            "platform": s.ChoiceField(choices=["android", "ios", "web"]),
        },
    ),
    responses={
        200: inline_serializer(
            name="DeviceTokenResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        400: inline_serializer(
            name="DeviceTokenError",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class RegisterDeviceTokenView(generics.GenericAPIView):
    """
    POST  /v1/user_profile/device-token/  — save or refresh an FCM push token.
    DELETE /v1/user_profile/device-token/ — remove the token on logout.

    Body: { "token": "<FCM_TOKEN>", "platform": "android" | "ios" | "web" }
    """

    permission_classes = (IsAuthenticated,)

    def post(self, request):
        payload = decrypt(request.data)
        token = (payload.get("token") or "").strip()
        platform = payload.get("platform", "android")

        if not token:
            return Response(
                data=encrypt({"status": "fail", "message": "token is required."}),
                status=status.HTTP_400_BAD_REQUEST,
            )

        if platform not in ("android", "ios", "web"):
            platform = "android"

        DeviceToken.objects.update_or_create(
            user=request.user,
            token=token,
            defaults={"platform": platform},
        )
        logger_fcm.info(
            "FCM token registered for %s [%s]", request.user.email, platform
        )

        return Response(
            data=encrypt({"status": "success", "message": "Device token registered."}),
            status=status.HTTP_200_OK,
        )

    def delete(self, request):
        payload = decrypt(request.data)
        token = (payload.get("token") or "").strip()

        if token:
            deleted, _ = DeviceToken.objects.filter(
                user=request.user, token=token
            ).delete()
            logger_fcm.info(
                "FCM token removed for %s (deleted=%d)", request.user.email, deleted
            )

        return Response(
            data=encrypt({"status": "success", "message": "Device token removed."}),
            status=status.HTTP_200_OK,
        )
