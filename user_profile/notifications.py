from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.response import Response


from .serializers import (
    NotificationSerializers,
    ClearNotificationSerializer,
    DeleteNotificationStatusSerializer,
)
from accounts.models import UserNotification


class GetAllNotifications(generics.ListAPIView):
    """
    GetAllNotifications is the GET request handler that allows a user to
    receieve all notifications.
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = NotificationSerializers
    ordering_fields = ["-created_at"]

    def get_queryset(self):
        user = self.request.user  # Access authorized user from request
        return UserNotification.objects.filter(user=user).order_by("-created_at")

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.serializer_class(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class GetSingleNotification(generics.RetrieveAPIView):
    """
    GetSingleNotification is the GET request handler that allows a user to
    receieve notification.
    """

    queryset = UserNotification.objects.all()
    serializer_class = NotificationSerializers
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    lookup_field = "id"

    def retrieve(self, request, *args, **kwargs):
        try:
            notification = self.get_object()

            # Check if the notification belongs to the authenticated user
            if notification.user != request.user:
                return Response(
                    {"detail": "You are not authorized to view this notification."},
                    status=status.HTTP_403_FORBIDDEN,
                )

            serializer = self.get_serializer(notification)
            return Response(serializer.data, status=status.HTTP_200_OK)

        except UserNotification.DoesNotExist:
            return Response(
                {"detail": "Notification not found."},
                status=status.HTTP_404_NOT_FOUND,
            )


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
            {"message": "Notifications cleared."}, status=status.HTTP_200_OK
        )


class MarkNotificationsAsRead(generics.UpdateAPIView):
    """
    MarkNotificationsAsRead view for marking multiple user
    notifications as read.
    """

    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    serializer_class = NotificationSerializers

    def post(self, request):
        user = request.user
        notifications = UserNotification.objects.filter(user=user)

        if not notifications.exists():
            return Response(
                {"message": "You have no notifications to mark as read."},
                status=status.HTTP_200_OK,
            )

        notifications.update(is_read=True)
        return Response(
            {"message": "All notifications marked as read."}, status=status.HTTP_200_OK
        )


class DeleteNotification(generics.DestroyAPIView):
    """
    DeleteNotification is the DELETE request handler that allows a user to delete their post.
    """

    queryset = UserNotification.objects.all()
    serializer_class = DeleteNotificationStatusSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    lookup_field = "id"

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
