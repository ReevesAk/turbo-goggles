import logging

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
from security import encrypt


logger = logging.getLogger(__name__)


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
        logger.info(
            "Received request to list notifications for user: %s", request.user.email
        )

        notifications = self.get_queryset().filter(user=request.user)
        logger.debug(
            "Total notifications found for user %s: %d",
            request.user.email,
            notifications.count(),
        )

        user_data = request.user

        data = []
        for notification in notifications:
            data.append(
                {
                    "notification_id": notification.id,
                    "title": notification.title,
                    "message": notification.message,
                    "is_read": notification.is_read,
                    "created_at": str(notification.created_at),
                }
            )

        response = {
            "status": "success",
            "message": f"All notifications for {user_data.first_name} {user_data.last_name} fetched successfully!",
            "data": data,
        }
        logger.info(
            "Response prepared successfully with %d notifications for user: %s",
            len(data),
            user_data.email,
        )
        return Response(data=encrypt(response), status=status.HTTP_200_OK)


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
        logger.info(
            "Received request to retrieve notification with ID: %s", kwargs.get("id")
        )

        try:
            user_notification = self.get_object()
            logger.debug("User  notification object retrieved: %s", user_notification)

            # Check if the notification belongs to the authenticated user
            if user_notification.user != request.user:
                logger.warning(
                    "Unauthorized access attempt by user: %s for notification ID: %s",
                    request.user.email,
                    kwargs.get("id"),
                )
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "message": "You are not authorized to view this notification.",
                        }
                    ),
                    status=status.HTTP_403_FORBIDDEN,
                )

            ntfn_id = kwargs["id"]
            notification = UserNotification.objects.get(id=ntfn_id)
            logger.info("Notification found: %s", notification)

            response = {
                "status": "success",
                "message": "Notification retrieved successfully!",
                "title": notification.title,
                "data": {
                    "notification_id": ntfn_id,
                    "message": notification.message,
                    "is_read": notification.is_read,
                    "created_at": str(notification.created_at),
                },
            }
            logger.info(
                "Response prepared successfully for notification ID: %s", ntfn_id
            )
            return Response(data=encrypt(response), status=status.HTTP_200_OK)

        except UserNotification.DoesNotExist:
            logger.error("Notification with ID %s not found.", kwargs.get("id"))
            return Response(
                data=encrypt({"status": "fail", "message": "Notification not found."}),
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
        logger.info("Received request to delete notifications for user: %s", user.email)

        notifications = UserNotification.objects.filter(user=user)

        if not notifications.exists():
            logger.info("No notifications found for user: %s to delete.", user.email)
            return Response(
                {"message": "No notifications found to delete."},
                status=status.HTTP_200_OK,
            )

        deleted_count, _ = notifications.delete()
        logger.info("Deleted %d notifications for user: %s", deleted_count, user.email)

        return Response(
            data=encrypt({"message": "Notifications cleared."}),
            status=status.HTTP_200_OK,
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
        logger.info(
            "Received request to mark notifications as read for user: %s", user.email
        )

        notifications = UserNotification.objects.filter(user=user)

        if not notifications.exists():
            logger.info(":User  %s has no notifications to mark as read.", user.email)
            return Response(
                data=encrypt({"message": "You have no notifications to mark as read."}),
                status=status.HTTP_200_OK,
            )

        updated_count = notifications.update(is_read=True)
        logger.info(
            "Marked %d notifications as read for user: %s", updated_count, user.email
        )

        return Response(
            data=encrypt({"message": "All notifications marked as read."}),
            status=status.HTTP_200_OK,
        )


class DeleteNotification(generics.DestroyAPIView):
    """
    DeleteNotification is the DELETE request handler that allows a user to delete their notification.
    """

    queryset = UserNotification.objects.all()
    serializer_class = DeleteNotificationStatusSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    lookup_field = "id"

    def destroy(self, request, *args, **kwargs):
        logger.info(
            "Received request to delete notification with ID: %s", kwargs.get("id")
        )

        try:
            notification = self.get_object()
            logger.debug("Notification object retrieved: %s", notification)

            if notification.user == request.user:
                notification.delete()
                logger.info(
                    "Notification with ID: %s deleted by user: %s",
                    notification.id,
                    request.user.email,
                )
                return Response(
                    data=encrypt({"status": "Notification deleted."}),
                    status=status.HTTP_204_NO_CONTENT,
                )
            else:
                logger.warning(
                    "Unauthorized delete attempt by user: %s for notification ID: %s",
                    request.user.email,
                    notification.id,
                )
                return Response(
                    data=encrypt(
                        {
                            "detail": "You are not authorized to delete this notification."
                        }
                    ),
                    status=status.HTTP_403_FORBIDDEN,
                )

        except UserNotification.DoesNotExist:
            logger.error("Notification with ID %s not found.", kwargs.get("id"))
            return Response(
                data=encrypt({"detail": "Notification not found."}),
                status=status.HTTP_404_NOT_FOUND,
            )
