from rest_framework import generics
from rest_framework.response import Response


class WebhookView(generics.GenericAPIView):
    def post(self, request):
        data = request.json()
        response = {"detail": "Webhook received succesfully!", "data": data}
        return Response(data=response)
