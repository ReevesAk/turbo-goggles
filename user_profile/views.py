from permissions import IsSuperAdmin
import hmac
import hashlib
import json
from decouple import config

from django.contrib.auth.hashers import check_password
from django.http import HttpRequest
from django.db.models import Q

from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken


from .serializers import (
    ChangePasswordSerializer,
    GetUserSerializer,
    UpdateUserSerializer,
    ProfileImageSerializer,
    DeleteUserSerializer,
)
from accounts.models import User
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

            return Response(
                {"detail": "Password updated successfully."}, status=status.HTTP_200_OK
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UpgradeToMember(generics.UpdateAPIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

    def get_object(self):
        return self.request.user

    def put(self, request):
        user = self.get_object()

        user.game_points = 15
        if user.account_type == "User":
            try:
                if user.game_points is not None:
                    if user.game_points >= 10:
                        user.account_type = "Member"
                        user.game_points -= 10
                        user.save()
                        resp = {
                            "status": "Success!",
                            "data": "Congratulations you have been \
                            upgraded to a member You can now enjoy\
                            amazing discounts and offers with us.",
                        }
                        return Response(data=resp, status=status.HTTP_200_OK)
                    else:
                        resp = {
                            "status": "fail",
                            "error": "You do not have enough points. \
                                Engage in gamification tasks to gain points.",
                        }
                        return Response(data=resp, status=status.HTTP_400_BAD_REQUEST)
                else:
                    resp = {
                        "status": "fail!",
                        "error": "You have not started earning points. \
                            Engage in gamification tasks to gain points",
                    }
                    return Response(data=resp, status=status.HTTP_400_BAD_REQUEST)

            except Exception as e:
                return Response(
                    {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        else:
            return Response(
                {"detail": "User is already a Member."},
                status=status.HTTP_400_BAD_REQUEST,
            )


class WebhookView(generics.GenericAPIView):
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
            return Response(
                f"Account with '{email}' deleted successfully.",
                status=status.HTTP_204_NO_CONTENT,
            )
        except User.DoesNotExist:
            return Response(
                f"User with '{email}' does not exist.",
                status=status.HTTP_404_NOT_FOUND,
            )
