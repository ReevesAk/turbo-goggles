from decouple import config

from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.response import Response

from drf_spectacular.utils import extend_schema
 
from .serializers import (
    NotificationSerializers,
    ClearNotificationSerializer,
    DeleteNotificationStatusSerializer,
)
from accounts.models import UserNotification


class GetNotifications(generics.ListAPIView):
    """
    GetNotifications is the GET request handler that allows a user to
    receieve notifications.
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = NotificationSerializers
    ordering_fields = ["-created_at"]

    def get_queryset(self):
        user = self.request.user  # Access authorized user from request
        return UserNotification.objects.filter(user=user).order_by("-created_at")


class ClearNotifications(generics.DestroyAPIView):
    """
    ClearNotifications is the DELETE request hanlder view for
    deleting all notifications for the current user.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = ClearNotificationSerializer
    authentication_classes = [JWTAuthentication]

    def destroy(self, request, *args, **kwargs):
        user = self.request.user
        notifications = UserNotification.objects.filter(user=user)

        if not notifications.exists():
            return Response(
                {"message": "No notifications found to delete."},
                status=status.HTTP_200_OK,
            )

        notifications.delete()
        return Response(
            {"message": "Notifications deleted."}, status=status.HTTP_200_OK
        )


class MarkNotificationsAsRead(generics.UpdateAPIView):
    """
    MarkNotificationsAsRead view for marking multiple user 
    notifications as read.
    """

    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    serializer_class = NotificationSerializers

    def update(self, request, *args, **kwargs):
        user = self.request.user
        data = request.data.get("ids", [])

        if not data:
            return Response(
                {"error": "Please provide notification IDs to mark as read."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate IDs are integers and belong to the user
        valid_ids = []
        for id_str in data:
            try:
                notification_id = int(id_str)
                UserNotification.objects.get(id=notification_id, user=user)
                valid_ids.append(notification_id)
            except (ValueError, UserNotification.DoesNotExist):
                pass

        if not valid_ids:
            return Response(
                data={"error": "Invalid or non-existent notification IDs provided."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        UserNotification.objects.filter(id__in=valid_ids).update(read=True)
        return Response(
            data={"message": "Notifications marked as read."}, status=status.HTTP_200_OK
        )


class DeleteNotification(generics.DestroyAPIView):
    """
    DeletePost is the DELETE request handler that allows a user to delete their post.
    """

    queryset = UserNotification.objects.all()
    serializer_class = DeleteNotificationStatusSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def destroy(self, request, *args, **kwargs):
        try:
            notification = self.get_object()

            if notification.user == request.user:
                notification.delete()
                return Response(
                    {"status": "Notification deleted."},
                    status=status.HTTP_204_NO_CONTENT,
                )
            else:
                return Response(
                    {"detail": "You are not authorized to delete this notification."},
                    status=status.HTTP_403_FORBIDDEN,
                )

        except UserNotification.DoesNotExist:
            return Response(
                {"detail": "Notification not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
