from django.shortcuts import get_object_or_404

# Third party imports.
from rest_framework import generics, status
from rest_framework.response import Response

# In_project imports
from . serializers import (BusinessProfileSerializers, UserProfileSerializers)
from accounts.models import User
from . models import BusinessProfile, UserProfile


class BusinessView(generics.GenericAPIView):
    serializer_class = BusinessProfileSerializers
    queryset = BusinessProfile.objects.all()

    def get(self, request, *args, **kwargs):
        user = get_object_or_404(User, pk=kwargs['id'])
        profile_serializer = BusinessProfileSerializers(user.profile)
        return Response(profile_serializer.data)

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    def update(self, request, **kwargs):
        user = get_object_or_404(User, pk=kwargs['id'])
        profile_serializer = BusinessProfileSerializers(user.profile)
        return Response(profile_serializer.data, status=status.HTTP_200_OK)


class UserView(generics.GenericAPIView):
    serializer_class = UserProfileSerializers
    queryset = UserProfile.objects.all()

    def get(self, request, *args, **kwargs):
        user = get_object_or_404(User, pk=kwargs['id'])
        profile_serializer = BusinessProfileSerializers(user.profile)
        return Response(profile_serializer.data)

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    def update(self, request, **kwargs):
        user = get_object_or_404(User, pk=kwargs['id'])
        profile_serializer = UserProfileSerializers(user.profile)
        return Response(profile_serializer.data, status=status.HTTP_200_OK)
