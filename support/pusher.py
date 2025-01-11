from datetime import datetime, timezone

import pusher
from decouple import config

from rest_framework.response import Response
from rest_framework import status, generics
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication

from .serializers import PusherSerializers
from security import encrypt, decrypt

# Initialize Pusher client
pusher_client = pusher.Pusher(
    app_id=config("PUSHER_APP_ID"),
    key=config("PUSHER_APP_KEY"),
    secret=config("PUSHER_APP_SECRET"),
    cluster=config("PUSHER_APP_CLUSTER"),
    ssl=True
)


class SupportChat(generics.GenericAPIView):
    serializer_class = PusherSerializers
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def post(self, request, *args, **kwargs):
        decrypted_msg = decrypt(request.data)
        message = decrypted_msg.get("message")
        user_id_1 = kwargs.get('user_id_1')
        user_id_2 = kwargs.get('user_id_2')

        # Create a unique channel name for the two users
        channel_name = f'chat-{min(user_id_1, user_id_2)}-{max(user_id_1, user_id_2)}'

        # Trigger an event on the Pusher channel
        pusher_client.trigger(channel_name, 'new-message', {'message': message})

        return Response(
            data=encrypt({
                "status": "success",
                "message": "Chat intitiated",
                "sender_id": request.user.id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "data": {
                    "api_key": config("PUSHER_APP_KEY"),
                    "cluster": config("PUSHER_APP_CLUSTER"),
                    "channels": channel_name,
                }
            }),
            status=status.HTTP_200_OK
        )


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
        return Response(data=encrypt({"status": "success", "message": "Authentication", "data": auth}), status=status.HTTP_200_OK)
