from django.contrib.auth.hashers import make_password, check_password

from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.response import Response

from .serializers import (
    ChangePasswordSerializer,
    GetUserSerializer,
    UpdateUserSerializer,
)

from accounts.otp import otp_manager


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
            user.save()

            return Response(
                {"detail": "Password updated successfully."}, status=status.HTTP_200_OK
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UpgradeToMember(generics.UpdateAPIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

    def put(self, request):
        user = request.user

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
                            "data": "Congratulations you have been upgraded to a member. You can now enjoy amazing discounts and offers with us.",
                        }
                        return Response(data=resp, status=status.HTTP_200_OK)
                    else:
                        resp = {
                            "status": "fail",
                            "error": "You do not have enough points. Engage in gamification tasks to gain points.",
                        }
                        return Response(data=resp, status=status.HTTP_400_BAD_REQUEST)
                else:
                    resp = {
                        "status": "fail!",
                        "error": "You have not started earning points. Engage in gamification tasks to gain points",
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
