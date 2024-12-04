import pusher
from decouple import config

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, generics
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication

from .serializers import PusherSerializers


class NotifyView(APIView):
    def post(self, request, *args, **kwargs):
        message = request.data.get("message", "Hello from Pusher!")

        # Initialize Pusher client
        pusher_client = pusher.Pusher(
            app_id=config("PUSHER_APP_ID"),
            key=config("PUSHER_KEY"),
            secret=config("PUSHER_SECRET"),
            cluster=config("PUSHER_CLUSTER"),
            ssl=config("PUSHER_SSL"),
        )

        # Trigger event on the Pusher channel
        pusher_client.trigger("my-channel", "my-event", {"message": message})

        return Response(data={"status": "success", "message": "Message broadcasted"}, status=status.HTTP_200_OK)


class GetSingleTicket(generics.RetrieveAPIView):
    """
    GetSingleTicket is the GET request handler that allows a SuperAdmin to
    check a specific support ticket.
    """

    serializer_class = PusherSerializers
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    lookup_field = "ticket_id"

    def post(request):
        pusher_client = pusher.Pusher(
            app_id=config("PUSHER_APP_ID"),
            key=config("PUSHER_KEY"),
            secret=config("PUSHER_SECRET"),
            cluster=config("PUSHER_CLUSTER"),
            ssl=config("PUSHER_SSL"),
        )

        auth = pusher_client.authenticate(
            channel=request.POST['channel_name'],
            socket_id=request.POST['socket_id']
        )
        return Response(data={"status": "success", "message": "Authentication", "data": auth}, status=status.HTTP_200_OK)
