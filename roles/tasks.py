import logging
from exceptions import UserDoesNotExist
from django.shortcuts import get_object_or_404
from django.db import transaction

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
    GetAllSubittedTasksSerializer,
    GetSingleSubmittedTaskSerializer,
    ReviewTaskSerializer,
)
from accounts.models import User
from .models import GamificationModel, Points
from permissions import IsTaskAdmin, IsSuperAdmin
from security import encrypt, decrypt


logger = logging.getLogger(__name__)


class AssignTask(generics.CreateAPIView):
    """
    AssignTask is the POST request handler that allows a Task Admin
    to assign gamification tasks to users/members.
    """

    serializer_class = AssignTaskSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsTaskAdmin | IsSuperAdmin)

    def post(self, request, *args, **kwargs):
        logger.info("Received POST request to assign a task.")

        decrypted_payload = decrypt(request.data)
        serializer = self.get_serializer(data=decrypted_payload)
        if serializer.is_valid(raise_exception=True):
            user_id = kwargs.get("user_id")
            logger.info(f"Attempting to assign task to user_id: {user_id}")

            try:
                user = User.objects.get(id=user_id)
                logger.info(f"User found: {user.first_name} {user.last_name}")
            except User.DoesNotExist:
                logger.error(f"User with id {user_id} does not exist.")
                raise encrypt(UserDoesNotExist)

            # Prepare task data
            task_data = {
                "task_id": serializer.validated_data["task_id"],
                "title": serializer.validated_data["title"],
                "description": serializer.validated_data["description"],
                "assigned_to": user,
            }
            logger.info(f"Task data prepared for task_id: {task_data['task_id']}")

            try:
                # Create a new task
                task = GamificationModel.objects.create(**task_data)
                logger.info(f"Task created successfully with task_id: {task.task_id}")
            except Exception as e:
                logger.error(f"Error creating task: {str(e)}")
                return Response(
                    data=encrypt(
                        {"status": "error", "message": "Error creating task."}
                    ),
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

            response_data = {
                "status": "Success",
                "message": "Task assigned successfully.",
                "data": {
                    "task_id": task.task_id,
                    "title": task.title,
                    "assigned_to": user.first_name + " " + user.last_name,
                    "description": task.description,
                },
            }
            logger.info(f"Task assigned successfully, task_id: {task.task_id}")

            return Response(data=encrypt(response_data), status=status.HTTP_201_CREATED)


class GetAllTasks(generics.ListAPIView):
    """
    GetAllTasks is the GET request handler that allows a Task Admin
    to retrieve all assigned gamification tasks to users/members.
    """

    serializer_class = GetAllTaskSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsTaskAdmin | IsSuperAdmin)
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

        return Response(data=encrypt(response_data), status=status.HTTP_200_OK)


class GetSingleTask(generics.RetrieveAPIView):
    """
    GetSingleTask is the GET request handler that allows a Task Admin
    to retrieve an assigned gamification task.
    """

    serializer_class = GetSingleTaskSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsTaskAdmin | IsSuperAdmin)

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

        return Response(data=encrypt(response_data), status=status.HTTP_200_OK)


class UpdateUserTask(generics.UpdateAPIView):
    """
    UpdateUserTask is the PATCH request handler for updating
    a users' gamification task.
    """

    serializer_class = UpdateTaskSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsTaskAdmin | IsSuperAdmin)

    def get_object(self):
        return self.request.user

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        decrypted_payload = decrypt(request.data)
        serializer = self.get_serializer(
            instance, data=decrypted_payload, partial=partial
        )
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data, status=status.HTTP_200_OK)


class GetAllSubmittedTasks(generics.ListAPIView):
    """
    GetAllSubmittedTasks is the GET request handler for retrieving
    all submitted gamification tasks.
    """

    serializer_class = GetAllSubittedTasksSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsTaskAdmin | IsSuperAdmin)

    def get_queryset(self):
        return GamificationModel.objects.exclude(task_url__exact="")

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)

        response_data = {
            "status": "Success",
            "message": "All submitted tasks retrieved successfully.",
            "data": serializer.data,
        }

        return Response(data=encrypt(response_data), status=status.HTTP_200_OK)


class GetSingleSubmittedTask(generics.ListAPIView):
    """
    GetSingleSubmittedTask is the GET request handler for retrieving
    a single submitted gamification task.
    """

    serializer_class = GetSingleSubmittedTaskSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsTaskAdmin | IsSuperAdmin)

    def get_queryset(self):
        return GamificationModel.objects.exclude(task_url__exact="")

    def retrieve(self, request, *args, **kwargs):
        instance = get_object_or_404(self.get_queryset(), id=kwargs["task_id"])
        serializer = self.get_serializer(instance)

        response_data = {
            "status": "Success",
            "message": "Submitted task retrieved successfully.",
            "data": serializer.data,
        }

        return Response(data=encrypt(response_data), status=status.HTTP_200_OK)


class ReviewTask(generics.CreateAPIView):
    """
    ReviewTask is the POST request handler for retrieving and reviewing
    a single submitted gamification task with the aim of either awarding
    points if succesful.
    """

    serializer_class = ReviewTaskSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsTaskAdmin | IsSuperAdmin)

    def post(self, request):
        logger.info("Received POST request to review task.")

        decrypted_payload = decrypt(request.data)
        serializer = self.get_serializer(data=decrypted_payload)
        if serializer.is_valid(raise_exception=True):
            user_id = serializer.validated_data["user_id"]
            logger.info(f"Processing task for user_id: {user_id}")

            try:
                user = User.objects.get(id=user_id)
                logger.info(f"User found: {user.full_name}")
            except User.DoesNotExist:
                logger.error(f"User with id {user_id} does not exist.")
                raise UserDoesNotExist

            new_pts = serializer.validated_data["pts"]
            logger.info(f"New points to be added: {new_pts}")

            serializer.save()

            try:
                with transaction.atomic():
                    game = GamificationModel.objects.get(user=user)
                    game.pts = new_pts
                    game.is_done = True
                    game.save()
                    logger.info(
                        f"Gamification points updated for user: {user.full_name}"
                    )

                    pts = Points.objects.get(user=user)
                    pts.balance += new_pts
                    pts.gamification = game
                    pts.save()
                    logger.info(f"Points balance updated for user: {user.full_name}")

            except Exception as e:
                logger.error(f"Database query error while updating points: {str(e)}")

        response_data = {
            "status": "Success",
            "message": "Task reviewed successfully.",
            "data": serializer.data,
        }
        logger.info("Task review successfully completed.")

        return Response(data=encrypt(response_data), status=status.HTTP_200_OK)
