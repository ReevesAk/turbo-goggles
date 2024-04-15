from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


from .serializers import (
    NotificationSerializers,
    ClearNotificationSerializer,
    DeleteNotificationStatusSerializer,
)
from accounts.models import UserNotification


class PaginationStyle(PageNumberPagination):
    page_size = 20


class GetAllNotifications(generics.ListAPIView):
    """
    GetAllNotifications is the GET request handler that allows a user to
    receive all notifications.
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = NotificationSerializers
    queryset = UserNotification.objects.all().order_by("-created_at")

    def list(self, request, *args, **kwargs):
        notifications = self.get_queryset().filter(user=request.user)
        user_data = request.user

        data = []
        for notification in notifications:
            data.append(
                {
                    "notification_id": notification.id,
                    "title": notification.title,
                    "message": notification.message,
                    "is_read": notification.is_read,
                    "created_at": notification.created_at,
                }
            )

        response = {
            "status": "success",
            "message": f"All notifications for {user_data.first_name} {user_data.last_name} fetched successfully!",
            "data": data,
        }
        return Response(response, status=status.HTTP_200_OK)


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
            user_notifcation = self.get_object()

            # Check if the notification belongs to the authenticated user
            if user_notifcation.user != request.user:
                return Response(
                    {
                        "status": "fail",
                        "message": "You are not authorized to view this notification.",
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            ntfn_id = kwargs["id"]
            notifcation = UserNotification.objects.get(id=ntfn_id)
            response = {
                "status": "success.",
                "message": "Notification retrieved successfully!.",
                "title": notifcation.title,
                "data": {
                    "notification_id": ntfn_id,
                    "message": notifcation.message,
                    "is_read": notifcation.is_read,
                    "created_at": notifcation.created_at,
                },
            }
            return Response(data=response, status=status.HTTP_200_OK)

        except UserNotification.DoesNotExist:
            return Response(
                {"status": "fail", "message": "Notification not found."},
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
