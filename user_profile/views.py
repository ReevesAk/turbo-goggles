import logging

from sms import Message
from commons import Messaging
from permissions import IsSuperAdmin, IsMember

from django.contrib.auth.hashers import check_password
from django.contrib.contenttypes.models import ContentType
from django.template.loader import render_to_string
from django.db.models import Q

from rest_framework import generics, exceptions
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.exceptions import ValidationError

from drf_spectacular.utils import extend_schema_view, extend_schema


from .serializers import (
    ProfileStatusSerializer,
    ChangePasswordSerializer,
    GetUserSerializer,
    UpdateUserSerializer,
    ProfileImageSerializer,
    DeleteUserSerializer,
    OpenRewardBoxSerializers,
    ClaimRewardSerializers,
    MemberSurverySerializers,
    SwitchToUserSerializer,
    SwitchToPartnersSerializer,
    SwitchToBrandAdSerializer,
    AddToFavouriteSerializer,
    FavouriteSerializer,
    SupportTicketSerializer,
    TierListResponseSerializer
)
from .helpers import MysteryBox, VariationCodes
from .choices import LEVELS
from accounts.models import User, Rewards, UserNotification, AccountType
from roles.models import ActivityModel
from support.models import Ticket
from gamification.models import Points
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
from vas.models import (
    AirtimeTopup,
    DataSubscription,
    TvSubscription,
    WaecRegistration,
    ElectricityBill,
)
from fmcg.models import Product, Favourite
from security import encrypt, decrypt


logger = logging.getLogger(__name__)


class SwitchToUser(generics.RetrieveAPIView):
    """
    SwitchToUser is the PUT request method for updating and switching
    to a user's account type.
    """

    serializer_class = SwitchToUserSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        description="Switch to User.",
        responses={200: {"description": "Switch an account type to User."}},
    )
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

            # Check if any AccountType has "User " in user_type
            is_user = any(acct.user_type == "User" for acct in account_types)

            if not is_user:
                data = {
                    "status": "fail",
                    "message": "Oops, you haven't registered as a User yet.",
                    "data": user.active_role,
                }
                logger.warning(
                    "User  %s attempted to switch to User but is not registered as one.",
                    user.email,
                )
                return Response(data=encrypt(data), status=status.HTTP_400_BAD_REQUEST)

        except AccountType.DoesNotExist:
            logger.error("AccountType for user %s does not exist.", user.email)
            raise exceptions.ValidationError(
                encrypt("AccountType for the user does not exist.")
            )

        # Handle already switched to User
        if user.active_role == "User":
            data = {
                "status": "success",
                "message": "You are already on the User screen.",
                "data": user.active_role,
            }
            logger.info("User  %s is already on the User screen.", user.email)
            return Response(data=encrypt(data), status=status.HTTP_200_OK)

        # Log the switch action
        logger.info(
            "User  %s is switching account type from %s to User.",
            user.email,
            user.active_role,
        )

        UserNotification.objects.create(
            user=user,
            title="User Type Switch.",
            message="Account type switched to User successfully.",
        )

        ActivityModel.objects.create(
            user=user,
            title="User  Type Switch.",
            description=f"{user.first_name} {user.last_name} switched account from {user.active_role} to User.",
        )

        # User has a Partner account type, switch the role
        user.active_role = "User"
        user.save()

        data = {
            "status": "success",
            "message": "Account type switched to User successfully.",
            "data": user.active_role,
        }
        logger.info("User  %s successfully switched account type to User.", user.email)
        return Response(data=encrypt(data), status=status.HTTP_200_OK)


class SwitchToPartner(generics.RetrieveAPIView):
    """
    SwitchToPartner is the PUT request method for updating and switching
    to a Partner's account type.
    """

    serializer_class = SwitchToPartnersSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        description="Switch to Partner.",
        responses={200: {"description": "Switch an account type to Partner."}},
    )
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


class SwitchToBrandAd(generics.RetrieveAPIView):
    """
    SwitchToBrandAd is the PUT request method for updating and switching
    to a BrandAd account type.
    """

    serializer_class = SwitchToBrandAdSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        description="Switch to BrandAd.",
        responses={200: {"description": "Switch an account type to BrandAd."}},
    )
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


class ProfileImage(generics.UpdateAPIView):
    """
    Upload profile image. This endpoint only
    accepts multipart/form-data data format.
    """

    serializer_class = ProfileImageSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

    def update(self, request, *args, **kwargs):
        logger.info(
            "User %s is attempting to upload a profile image.", request.user.email
        )

        # Get the user instance
        user = request.user

        # Use the serializer with the instance
        serializer = self.get_serializer(data=request.data)

        if serializer.is_valid():
            # Update the user's profile image.
            user.profile_img_url = request.data.get("profile_img_url")
            user.save()

            UserNotification.objects.create(
                user=user,
                title="Profile Image.",
                message="You have successfully updated your profile image.",
            )

            # Check if user is an admin and adjust the description
            if user.active_role in {
                "SuperAdmin",
                "TaskAdmin",
                "AdAdmin",
                "MembersAdmin",
                "User Admin",
                "PartnersAdmin",
                "ContentAdmin",
                "IntegrationAdmin",
                "WalletAdmin",
                "FmcgAdmin",
            }:
                description = f"Admin with email: {user.email} and role: {user.active_role} updated their profile image."
            else:
                description = (
                    f"{user.first_name} {user.last_name} updated their profile image."
                )

            ActivityModel.objects.create(
                user=user,
                title="Profile Image.",
                description=description,
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


class GetUserDetails(generics.RetrieveAPIView):
    """User Detials"""

    serializer_class = GetUserSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

    def retrieve(self, request, *args, **kwargs):
        user = self.request.user  # Get the authenticated user
        serializer = self.get_serializer(user)
        return Response(data=encrypt(serializer.data), status=status.HTTP_200_OK)


class UpdateUserProfile(generics.UpdateAPIView):
    """Update User Profile"""

    serializer_class = UpdateUserSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

    def get_object(self):
        return self.request.user

    def update(self, request, *args, **kwargs):
        logger.info(
            "User  %s is attempting to update their profile.", request.user.email
        )

        # Prepare the payload by stripping whitespace from string values
        payload = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in request.data.items()
        }

        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=payload, partial=partial)

        try:
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
                    "picadailys_phone": "+123 456 7890",
                },
            )

            Messaging.send_email(
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


class ChangePassword(generics.UpdateAPIView):
    serializer_class = ChangePasswordSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

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

            # Log the password change activity
            ActivityModel.objects.create(
                user=request.user,
                title="Change Password.",
                description=f"{request.user.first_name} {request.user.last_name} changed their password.",
            )

            body = "This is to inform you that your password on Picadailys has been updated."
            # Render the template with values
            text_content = render_to_string(
                template_name="empty_email.html",
                context={
                    "custom_text": f"Dear {request.user.first_name},<br><br>{body}.",
                    "support_email": "support@picadailys.com",
                    "picadailys_phone": "+123 456 7890",
                },
            )

            Messaging.send_email(
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


class MemberUserSwitch(generics.UpdateAPIView):
    serializer_class = ProfileStatusSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        description="Member-User switch",
        responses={200: {"description": "User and member switch."}},
    )
    def get_object(self):
        return self.request.user

    def put(self, request):
        user = self.get_object()
        logger.info(
            f"User {user.first_name} {user.last_name} initiated a role switch request."
        )

        game_point = Points.objects.get(user=user)

        if user.active_role == "User ":
            try:
                logger.info(
                    f"User {user.first_name} {user.last_name} has current balance: {game_point.balance}"
                )

                if game_point.balance is not None:
                    if game_point.balance >= 10.0:
                        AccountType.objects.update_or_create(
                            user_type="Partners",
                        )

                        user.active_role = "Member"
                        game_point.balance -= 10.0
                        user.save()
                        game_point.save()  # Don't forget to save the updated game_point

                        UserNotification.objects.create(
                            user=request.user,
                            title="Member Switch.",
                            message="Congratulations you have been upgraded to a member. You can now engage in gamifications and enjoy amazing discounts and offers with us.",
                        )

                        ActivityModel.objects.create(
                            user=request.user,
                            title="Member Switch.",
                            description=f"{request.user.first_name} {request.user.last_name} switched from User to Member.",
                        )

                        resp = {
                            "status": "success!",
                            "data": "Congratulations you have been upgraded to a member. You can now engage in gamifications and enjoy amazing discounts and offers with us.",
                        }
                        logger.info(
                            f"User {user.first_name} {user.last_name} successfully upgraded to Member."
                        )
                        return Response(data=encrypt(resp), status=status.HTTP_200_OK)
                    else:
                        resp = {
                            "status": "fail",
                            "error": "You do not have enough points.",
                        }
                        logger.warning(
                            f"User {user.first_name} {user.last_name} attempted to switch roles but does not have enough points."
                        )
                        return Response(
                            data=encrypt(resp), status=status.HTTP_400_BAD_REQUEST
                        )
                else:
                    resp = {
                        "status": "fail!",
                        "error": "You have not started earning points.",
                    }
                    logger.warning(
                        f"User {user.first_name} {user.last_name} has not started earning points."
                    )
                    return Response(
                        data=encrypt(resp), status=status.HTTP_400_BAD_REQUEST
                    )

            except Exception as e:
                logger.error(
                    f"An error occurred while processing the role switch for user {user.first_name} {user.last_name}: {str(e)}"
                )
                return Response(
                    data=encrypt({"error": str(e)}),
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
        elif user.active_role == "Member":
            user.active_role = "User "
            user.save()
            logger.info(
                f"User {user.first_name} {user.last_name} switched from Member to User."
            )
            return Response(
                data=encrypt(
                    {
                        "status": "success",
                        "message": "Member has been switched to a User.",
                    }
                ),
                status=status.HTTP_200_OK,
            )


class PostMemberSurvey(generics.CreateAPIView):
    """
    PostMemberSurvey endpoint to conduct memmber survey.
    """

    serializer_class = MemberSurverySerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsMember)

    def create(self, request):
        user = request.user
        logger.info(
            f"User {user.first_name} {user.last_name} initiated a survey completion request."
        )

        decrypted_payload = decrypt(request.data)
        payload = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_payload.items()
        }

        serializer = MemberSurverySerializers(data=payload)

        if serializer.is_valid(raise_exception=True):
            serializer.save()
            logger.info(
                f"Survey data is valid for user {user.first_name} {user.last_name}. Saving to database."
            )

            user = User.objects.create(user=request.user)

            UserNotification.objects.create(
                user=request.user,
                title="Member Survey.",
                message="Survey completed successfully!",
            )

            ActivityModel.objects.create(
                user=user,
                title="Member Survey.",
                description=f"{request.user.first_name} {request.user.last_name} has completed Member account survey.",
            )

            user.has_done_survey = True
            user.save()
            logger.info(
                f"User {user.first_name} {user.last_name} has completed the survey and updated done_survey status."
            )
            # Prepare the response data
            response = {
                "status": "success",
                "message": "Survey completed successfully!",
                "data": serializer.data,
            }
            logger.info(
                f"Survey completion successful for user {user.first_name} {user.last_name}."
            )
            return Response(data=encrypt(response), status=status.HTTP_201_CREATED)
        else:
            logger.warning(
                f"Survey validation failed for user {user.first_name} {user.last_name}: {serializer.errors}"
            )
            return Response(
                data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST
            )


class DeleteUser(generics.DestroyAPIView):
    serializer_class = DeleteUserSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsSuperAdmin)

    def delete(self, request, *args, **kwargs):
        decrypted_payload = decrypt(request.data)
        email = decrypted_payload.get("email")
        logger.info(
            f"User {self.request.user.first_name} {self.request.user.last_name} initiated account deletion request for email: {email}"
        )

        try:
            user = User.objects.get(Q(id=email) | Q(email=email))
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

            recipient = user.phone_number[1:]  # Assuming phone_number is a string
            Message.send_msg(
                msg="This is to inform you that your account Picadailys has been deleted. We regret to lose you, we hope to see you again soon.",
                to=recipient,
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


class OpenRewardBox(generics.GenericAPIView):
    """
    OpenRewardBox is the GET request handler for opening the reward box.
    """

    serializer_class = OpenRewardBoxSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsMember)

    @extend_schema(
        description="Open Reward view",
        responses={200: {"description": "Open reward box view"}},
    )
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


class ClaimMysteryBoxGift(generics.GenericAPIView):
    """
    ClaimMysteryBoxGift is the GET request handler for allowing a
    user to claim their reward.
    """

    serializer_class = ClaimRewardSerializers
    authentication_classes = [JWTAuthentication]
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


class AddToFavourite(generics.CreateAPIView):
    """
    AddToFavourite is the POST request handler for allowing a
    user to add a product to his favourite list.
    """

    serializer_class = AddToFavouriteSerializer
    authentication_classes = [JWTAuthentication]
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
                "AirtimeTopup": AirtimeTopup,
                "DataSubscription": DataSubscription,
                "ElectricityBill": ElectricityBill,
                "TvSubscription": TvSubscription,
                "WaecRegistration": WaecRegistration,
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


class ListFavourites(generics.ListAPIView):
    """
    List all favourites for the authenticated user.
    """

    serializer_class = FavouriteSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        logger.info("Fetching favorites for user: %s", user.email)

        queryset = Favourite.objects.filter(user=user)

        logger.debug(
            "Retrieved %d favorites for user: %s", queryset.count(), user.email
        )

        return queryset


class RetrieveFavourite(generics.RetrieveAPIView):
    """
    Retrieve a specific favourite by its ID.
    """

    serializer_class = FavouriteSerializer
    authentication_classes = [JWTAuthentication]
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


class CustomerTicketCreation(generics.GenericAPIView):
    """
    CustomerTicketCreation is the POST request handler for allowing a
    user to create a support ticket.
    """

    serializer_class = SupportTicketSerializer
    authentication_classes = [JWTAuthentication]
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

        ticket = Ticket.objects.create(
            user=request.user,
            description=payload.get("description"),
            category=payload.get("category"),
            status="Queuing",
            channel="App",
            escalation_level="Management",
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
                        "Channel": "App",
                        "Escalation Level": "Management",
                        "Status": "Queuing",
                    },
                }
            ),
            status=status.HTTP_201_CREATED,
        )


@extend_schema_view(
    retrieve=extend_schema(
        responses={200: TierListResponseSerializer},
        description="Returns all tier levels with required points and the current level of the user.",
        summary="User Tier Levels",
    )
)
class TierListView(generics.RetrieveAPIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def retrieve(self, request, *args, **kwargs):
        user = request.user

        response = {
            "status": "success",
            "message": "Tier levels retrieved successfully!",
            "data": {
                "current_level": user.level,
                "total_points": user.total_points,
                "tiers": LEVELS,
            },
        }
        return Response(data=encrypt(response), status=status.HTTP_200_OK)
