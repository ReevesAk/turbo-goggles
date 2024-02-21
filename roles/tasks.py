from exceptions import UserDoesNotExist
from django.shortcuts import get_object_or_404

# Third party imports.
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication

from drf_spectacular.utils import extend_schema

# In project imports.
from .serializers import (
    AssignTaskSerializers,
    GetAllTaskSerializer,
    GetSingleTaskSerializer,
    UpdateTaskSerializer,
)
from accounts.models import User
from .models import GamificationModel
from permissions import IsTaskAdmin


class AssignTask(generics.CreateAPIView):
    """
    AssignTask is the POST request handler that allows a Task Admin
    to assign gamification tasks to users/members.
    """

    serializer_class = AssignTaskSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsTaskAdmin)

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid(raise_exception=True):
            user_id = serializer.validated_data["id"]
            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                raise UserDoesNotExist

            # Assuming your Task model has a 'assigned_to' field for the user
            task_data = {
                "task_id": serializer.validated_data["task_id"],
                "title": serializer.validated_data["title"],
                "description": serializer.validated_data["description"],
                "assigned_to": user,
            }

            # Create a new task
            task = GamificationModel.objects.create(**task_data)

            response_data = {
                "status": "Success",
                "message": "Task assigned successfully.",
                "data": {
                    "task_id": task.task_id,
                    "title": task.title,
                    "assigned_to": user.first_name + user.last_name,
                    "description": task.description,
                },
            }

            return Response(data=response_data, status=status.HTTP_201_CREATED)


class GetAllTasks(generics.ListAPIView):
    """
    GetAllTasks is the GET request handler that allows a Task Admin
    to retrieve all assigned gamification tasks to users/members.
    """

    serializer_class = GetAllTaskSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsTaskAdmin)
    queryset = GamificationModel.objects.all().order_by("-date")

    @extend_schema(
        description="Get tasks",
        responses={200: {"description": "Get all tasks"}},
    )
    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)

        response_data = {
            "status": "Success",
            "message": "Assigned tasks retrieved successfully.",
            "data": serializer.data,
        }

        return Response(data=response_data, status=status.HTTP_200_OK)


class GetSingleTask(generics.RetrieveAPIView):
    """
    GetSingleTask is the GET request handler that allows a Task Admin
    to retrieve an assigned gamification task.
    """

    serializer_class = GetSingleTaskSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsTaskAdmin)

    @extend_schema(
        description="Get task",
        responses={200: {"description": "Get a single task"}},
    )
    def retrieve(self, request, *args, **kwargs):
        instance = get_object_or_404(self.get_queryset(), id=kwargs["task_id"])
        serializer = self.get_serializer(instance)

        response_data = {
            "status": "Success",
            "message": "Task retrieved successfully.",
            "data": serializer.data,
        }

        return Response(data=response_data, status=status.HTTP_200_OK)


class UpdateUserTask(generics.UpdateAPIView):
    """UpdateUserTask is the PATCH request handler for updating
    a users' gamification task.
    """

    serializer_class = UpdateTaskSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsTaskAdmin)

    def get_object(self):
        return self.request.user

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data, status=status.HTTP_200_OK)
