from sms import Message
from permissions import IsSuperAdmin, IsUserOrMember
import hmac
import hashlib
import json
from decouple import config

from django.contrib.auth.hashers import check_password
from django.http import HttpRequest
from django.db.models import Q

from rest_framework import generics, exceptions
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from drf_spectacular.utils import extend_schema


from .serializers import (
    ProfileStatusSerializer,
    ChangePasswordSerializer,
    GetUserSerializer,
    UpdateUserSerializer,
    ProfileImageSerializer,
    DeleteUserSerializer,
    OpenRewardBoxSerializers,
    ClaimRewardSerializers
)
from .helpers import MysteryBox, VariationCodes
from accounts.models import User, Rewards, UserNotification
from roles.models import Points
from vas.helpers import VAS
from cloudinary import uploader as cloud


fincra_webhook_key = config("WEBHOOK_SECRET_KEY")


class ProfileImage(generics.CreateAPIView):
    """Upload profile image. This endpoint only
    accepts multipart/form-data data format.
    """

    serializer_class = ProfileImageSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

    def create(self, request):
        serializer = ProfileImageSerializer(data=request.data)

        if serializer.is_valid():
            profile_image = serializer.validated_data["profile_image"]

            # Upload the image to Cloudinary
            result = cloud.upload(profile_image)

            request.user.profile_img_url = result["url"]
            request.user.save()

            UserNotification.objects.create(
                user=request.user,
                title="Profile Image.",
                messsage="You have been successfully uploaded your profile image."
            )
            return Response(
                {"message": "Profile picture uploaded successfully"},
                status=status.HTTP_200_OK,
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class GetUserDetails(generics.RetrieveAPIView):
    """User Detials"""

    serializer_class = GetUserSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

    def retrieve(self, request, *args, **kwargs):
        user = self.request.user  # Get the authenticated user
        serializer = self.get_serializer(user)
        return Response(serializer.data, status=status.HTTP_200_OK)


class UpdateUserProfile(generics.UpdateAPIView):
    """Update User Profile"""

    serializer_class = UpdateUserSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

    def get_object(self):
        return self.request.user

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        UserNotification.objects.create(
            user=request.user,
            title="Update Profile.",
            messsage="You have been successfully updated your profile."
        )

        return Response(serializer.data, status=status.HTTP_200_OK)


class ChangePassword(generics.UpdateAPIView):
    serializer_class = ChangePasswordSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

    def update(self, request, *args, **kwargs):
        user = request.user
        serializer = self.get_serializer(data=request.data)

        if serializer.is_valid():
            old_password = serializer.validated_data["old_password"]
            new_password = serializer.validated_data["new_password"]

            if not check_password(old_password, user.password):
                return Response(
                    {"detail": "Old password is incorrect."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            user.set_password(new_password)

            # Retrieve existing tokens and blacklist them.
            user_token = request.data.get("refresh_token")
            token = RefreshToken(user_token)
            token.blacklist()
            user.save()

            UserNotification.objects.create(
                user=request.user,
                title="Change Password.",
                messsage="You have successfully changed your password."
            )

            return Response(
                {"detail": "Password updated successfully."}, status=status.HTTP_200_OK
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


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

        game_point = Points.objects.get(user=user)
        if user.account_type == "User":
            try:
                if game_point.balance is not None:
                    if game_point.balance >= 10.0:
                        user.account_type = "Member"

                        game_point.balance -= 10.0
                        user.save()

                        UserNotification.objects.create(
                            user=request.user,
                            title="Member Switch.",
                            messsage="Congratulations you have been \
                                upgraded to a member You can now enagage in\
                                gamifications and enjoy amazing discounts and\
                                offers with us."
                        )

                        resp = {
                            "status": "success!",
                            "data": "Congratulations you have been \
                            upgraded to a member You can now enagage in\
                            gamifications and enjoy amazing discounts and\
                            offers with us.",
                        }
                        return Response(data=resp, status=status.HTTP_200_OK)
                    else:
                        resp = {
                            "status": "fail",
                            "error": "You do not have enough points."
                        }
                        return Response(data=resp, status=status.HTTP_400_BAD_REQUEST)
                else:
                    resp = {
                        "status": "fail!",
                        "error": "You have not started earning points."
                    }
                    return Response(data=resp, status=status.HTTP_400_BAD_REQUEST)

            except Exception as e:
                return Response(
                    {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        elif user.account_type == "Member":
            user.account_type = "User"
            user.save()
            return Response(
                {"status": "success", "detail": "Member has been switched to a User."},
                status=status.HTTP_200_OK,
            )


class WebhookView(generics.GenericAPIView):
    serializer_class = ProfileStatusSerializer

    @extend_schema(
        description="Wenhook view",
        responses={200: {"description": "Webhook responses"}},
    )
    def post(self, request: HttpRequest, *args, **kwargs):
        webhook_secret_key = fincra_webhook_key
        payload = request.data

        key = webhook_secret_key.encode("utf-8")
        message = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        encrypted_data = hmac.new(key, message, hashlib.sha512).hexdigest()
        signature = request.headers.get("signature")

        if signature == encrypted_data:
            # Process the webhook data
            print("Processing webhook data:", payload)
            return Response(
                {"detail": "Webhook data processed successfully!"},
                status=status.HTTP_200_OK,
            )
        else:
            print("Discarding webhook data due to invalid signature.")
            return Response(
                {"detail": "Invalid signature, webhook data discarded."},
                status=status.HTTP_400_BAD_REQUEST,
            )


class DeleteUser(generics.DestroyAPIView):
    serializer_class = DeleteUserSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsSuperAdmin)

    def delete(self, request, *args, **kwargs):
        email = self.request.data.get("email")

        try:
            user = User.objects.get(Q(id=email) | Q(email=email))
            user.delete()

            UserNotification.objects.create(
                user=request.user,
                title="Delete Account.",
                messsage="You have deleted your account."
            )
            recipient = user.phone_number[1:]
            Message.send_msg(
                msg="This is to inform you that your account Picadailys has been deleted.\
                    We regret to lose you, we hope to see you again soon.",
                to=recipient
            )
            return Response(
                f"Account with '{email}' deleted successfully.",
                status=status.HTTP_204_NO_CONTENT,
            )
        except User.DoesNotExist:
            return Response(
                f"User with '{email}' does not exist.",
                status=status.HTTP_404_NOT_FOUND,
            )


class OpenRewardBox(generics.GenericAPIView):
    """
    OpenRewardBox is the GET request handler for opening the reward box.
    """

    serializer_class = OpenRewardBoxSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsUserOrMember)

    @extend_schema(
        description="Open Reward view",
        responses={200: {"description": "Open reward box view"}},
    )
    def get(self, request):
        user = request.user
        user_reward = Rewards.objects.get(user=user)

        if user_reward.balance >= 100:
            item, form= MysteryBox.open()
            user_reward.mystery_box = item
            user_reward.form_of_gift = form
            user_reward.save()

            response_data = {
                "status": "success",
                "message": "Wow, you have have an item in your box, click to claim reward!"
            }
            return Response(data=response_data, status=status.HTTP_200_OK)
        
        elif user_reward.balance < 100:
            raise exceptions.ValidationError(
                detail="Not enough rewards to access the mystery box.",
                code=status.HTTP_400_BAD_REQUEST)
    
        else:
            error_response = {
                "status": "fail",
                "message": "Sorry, you do not have any item in the your mystery box."
            }
            return Response(data=error_response, status=status.HTTP_400_BAD_REQUEST)


class ClaimMysteryBoxGift(generics.GenericAPIView):
    """
    ClaimMysteryBoxGift is the GET request handler for allowing a
    user to claim their reward.
    """

    serializer_class = ClaimRewardSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsUserOrMember)

    def get(self, request):
        authenticated_user = request.user
        user_data = request.data
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid(raise_exception=True):
            user_reward = Rewards.objects.get(user=authenticated_user)

            match user_reward.form_of_gift:
                case "airtime":
                    amount = Rewards.objects.get(user=authenticated_user)
                    airtime_response = VAS.aritime(
                        service_id=user_data["  "],
                        amount=amount.mystery_box,
                        phone=user_data["phone"],
                    )
                    if airtime_response.status_code == 200:
                        UserNotification.objects.create(
                            user=authenticated_user,
                            title="Claim Gift box reward.",
                            messsage="You have successfully claime your mystery box item."
                        )

                        response_data = {
                            "status": "Success",
                            "message": f"Recharge of {amount} was succesful.\
                                continue to purchase items to get rewards.",
                            "data": airtime_response.json(),
                        }
                        return Response(data=response_data, status=status.HTTP_200_OK)
                case "data":
                    amount = Rewards.objects.get(user=authenticated_user)
                    variation_code = VariationCodes.get(service_id=user_data["serviceID"], amount=amount.mystery_box)
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
                            messsage="You have successfully claime your mystery box item."
                        )

                        response = {
                            "status": "Success",
                            "message": f"Data subscription of {amount} was succesful.\
                                continue to purchase items to get rewards.",
                            "data": data_response.json(),
                        }
                        return Response(data=response, status=status.HTTP_200_OK)
