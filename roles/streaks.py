import logging

from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication

from gamification.models import PointConfig, StreakChallenge, UserStreak
from gamification.serializers import (
    PointConfigSerializer,
    PointConfigUpdateSerializer,
    StreakChallengeCreateSerializer,
    StreakChallengeSerializer,
    StreakChallengeUpdateSerializer,
)
from permissions import IsAdAdminOrSuperAdmin
from security import decrypt, encrypt

logger = logging.getLogger(__name__)


class ListPointConfigsView(generics.GenericAPIView):
    """GET /v1/roles/points/ — list all configurable point values."""

    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsAdAdminOrSuperAdmin)

    def get(self, request):
        configs = PointConfig.objects.all().order_by("key")
        data = PointConfigSerializer(configs, many=True).data
        return Response(
            data=encrypt({"status": "success", "data": data}),
            status=status.HTTP_200_OK,
        )


class UpdatePointConfigView(generics.GenericAPIView):
    """PATCH /v1/roles/points/<key>/ — update a single point value."""

    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsAdAdminOrSuperAdmin)

    def patch(self, request, key):
        try:
            config = PointConfig.objects.get(key=key)
        except PointConfig.DoesNotExist:
            return Response(
                data=encrypt(
                    {
                        "status": "error",
                        "message": f"No point config found for key '{key}'.",
                    }
                ),
                status=status.HTTP_404_NOT_FOUND,
            )

        payload = decrypt(request.data)
        serializer = PointConfigUpdateSerializer(config, data=payload, partial=True)
        if not serializer.is_valid():
            return Response(
                data=encrypt({"status": "error", "errors": serializer.errors}),
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer.save(updated_by=request.user)
        logger.info(
            "PointConfig '%s' updated to %s by %s",
            key,
            serializer.validated_data["value"],
            request.user.email,
        )

        return Response(
            data=encrypt(
                {
                    "status": "success",
                    "message": f"Point value for '{key}' updated successfully.",
                    "data": PointConfigSerializer(config).data,
                }
            ),
            status=status.HTTP_200_OK,
        )


class CreateStreakChallengeView(generics.GenericAPIView):
    """POST /v1/roles/streaks/create/ — create a new streak challenge."""

    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsAdAdminOrSuperAdmin)

    def post(self, request):
        payload = decrypt(request.data)
        serializer = StreakChallengeCreateSerializer(data=payload)
        if not serializer.is_valid():
            return Response(
                data=encrypt({"status": "error", "errors": serializer.errors}),
                status=status.HTTP_400_BAD_REQUEST,
            )

        challenge = serializer.save(created_by=request.user)
        logger.info(
            "StreakChallenge '%s' created by %s", challenge.name, request.user.email
        )

        return Response(
            data=encrypt(
                {
                    "status": "success",
                    "message": "Streak challenge created successfully.",
                    "data": StreakChallengeSerializer(challenge).data,
                }
            ),
            status=status.HTTP_201_CREATED,
        )


class ListStreakChallengesView(generics.GenericAPIView):
    """GET /v1/roles/streaks/ — list all streak challenges (all statuses)."""

    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsAdAdminOrSuperAdmin)

    def get(self, request):
        challenges = StreakChallenge.objects.all().order_by("-created_at")
        data = StreakChallengeSerializer(challenges, many=True).data
        return Response(
            data=encrypt(
                {"status": "success", "total": challenges.count(), "data": data}
            ),
            status=status.HTTP_200_OK,
        )


class UpdateStreakChallengeView(generics.GenericAPIView):
    """PATCH /v1/roles/streaks/<challenge_id>/update/ — edit, pause, or extend a challenge."""

    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsAdAdminOrSuperAdmin)

    def patch(self, request, challenge_id):
        try:
            challenge = StreakChallenge.objects.get(id=challenge_id)
        except StreakChallenge.DoesNotExist:
            return Response(
                data=encrypt(
                    {"status": "error", "message": "Streak challenge not found."}
                ),
                status=status.HTTP_404_NOT_FOUND,
            )

        payload = decrypt(request.data)
        serializer = StreakChallengeUpdateSerializer(
            challenge, data=payload, partial=True
        )
        if not serializer.is_valid():
            return Response(
                data=encrypt({"status": "error", "errors": serializer.errors}),
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer.save()
        logger.info(
            "StreakChallenge '%s' updated by %s", challenge.name, request.user.email
        )

        return Response(
            data=encrypt(
                {
                    "status": "success",
                    "message": "Streak challenge updated.",
                    "data": StreakChallengeSerializer(challenge).data,
                }
            ),
            status=status.HTTP_200_OK,
        )


class StreakChallengeLeaderboardAdminView(generics.GenericAPIView):
    """GET /v1/roles/streaks/<challenge_id>/leaderboard/ — ranked participants."""

    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsAdAdminOrSuperAdmin)

    def get(self, request, challenge_id):
        try:
            challenge = StreakChallenge.objects.get(id=challenge_id)
        except StreakChallenge.DoesNotExist:
            return Response(
                data=encrypt(
                    {"status": "error", "message": "Streak challenge not found."}
                ),
                status=status.HTTP_404_NOT_FOUND,
            )

        user_streaks = (
            UserStreak.objects.filter(challenge=challenge)
            .select_related("user")
            .order_by("-current_count", "-longest_count")
        )

        leaderboard = [
            {
                "rank": idx + 1,
                "user_id": str(us.user.id),
                "email": us.user.email,
                "full_name": getattr(us.user, "full_name", str(us.user)),
                "current_count": us.current_count,
                "longest_count": us.longest_count,
                "completed": us.completed,
                "reward_issued": us.reward_issued,
                "joined_at": us.joined_at.isoformat(),
            }
            for idx, us in enumerate(user_streaks)
        ]

        return Response(
            data=encrypt(
                {
                    "status": "success",
                    "challenge": challenge.name,
                    "total_participants": len(leaderboard),
                    "leaderboard": leaderboard,
                }
            ),
            status=status.HTTP_200_OK,
        )
