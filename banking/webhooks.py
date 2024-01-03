from rest_framework import generics
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status


class WebhookView(generics.GenericAPIView):
    def post(self, request):
        data = request.json()
        response = {
            "detail": "Webhook received succesfully!",
            "data": data
        }
        return Response(data=response)
