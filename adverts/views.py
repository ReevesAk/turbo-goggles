# Third party imports
from rest_framework import generics, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

# In project imports.
from .serializers import (
    AdvertStartSeriailizers, AdvertContdSerializers
)
from .models import BrandAdvertRegistration

from accounts.models import User

# Create your views here.

class StartRegisterAdverts(generics.GenericAPIView):
    permission_classes = (AllowAny,)
    serializer_class = AdvertStartSeriailizers

    def post(self, request):
        user = request.data
        serializer = self.serializer_class(data=user)
        if serializer.is_valid(raise_exception=True):
            serializer.save()
            user_data = serializer.data

        response = {"message": "Details successfully submitted!", "data": user_data}
        return Response(data=response, status=status.HTTP_201_CREATED)
    

class ContdRegisterAdverts(generics.GenericAPIView):
    permission_classes = (AllowAny,)
    serializer_class = AdvertContdSerializers

    def post(self, request):
        user = request.data
        serializer = self.serializer_class(data=user)
        if serializer.is_valid(raise_exception=True):
            serializer.save()
            user_data = serializer.data

        response = {"message": "Details successfully submitted!", "data": user_data}
        return Response(data=response, status=status.HTTP_201_CREATED)
    
