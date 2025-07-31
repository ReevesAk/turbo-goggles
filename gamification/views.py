import logging
from decouple import config as conf

from django.utils import timezone

from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from rest_framework import generics
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.response import Response


from .serializers import (
    SSOLoginSerializer,
    StepCountSessionSerializer
)
from .models import StepCampaignModel, StepSessionModel

from gamification.utils import NextBee
from security import encrypt, decrypt
from permissions import HasCompletedSurvey, IsMember


GAMIFICATION_BASE_URL = conf("NEXTBEE_GAMIFICATION_BASE_URL")

logger = logging.getLogger(__name__)


# Create your views here.
class NextBeeGamificationLSSOLogin(generics.GenericAPIView):
    """NextBeeGamificationLSSOLogin is the POST request handler for
    NextBee Gamification SSO login.
    """

    serializer_class = SSOLoginSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsMember)

    def post(self, request, *args, **kwargs):
        decrypted_payload = decrypt(request.data)
        payload = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_payload.items()
        }

        serializer = self.get_serializer(data=payload)
        if serializer.is_valid():
            email = serializer.validated_data["email"]
            nextbee = NextBee()
            resp = nextbee.sso_login(email=email)

            if resp.status_code != 200:
                logger.error(f"NextBee API Error - Status: {resp.status_code}, Response: {resp.text}")
                print(f"Response headers: {resp.headers}")
                return Response(
                    data=encrypt({"error": "SSO login failed."}),
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if resp.status_code == 200:
                logger.info(
                    f"SSO login successful for user {request.user.first_name} {request.user.last_name}."
                )
                return Response(
                    data=encrypt(
                        {
                            "status": "success",
                            "message": "SSO login successful.",
                            "gamificcation_redirect_url": GAMIFICATION_BASE_URL,
                            "token": resp.json().get("token", None)
                        }
                    ),
                    status=status.HTTP_200_OK
                )
            else:
                logger.error(
                    f"SSO login failed for user {request.user.first_name} {request.user.last_name}: {resp.text}"
                )
                return Response(
                    data=encrypt({"error": "SSO login failed."}),
                    status=status.HTTP_400_BAD_REQUEST,
                )
        return Response(
            data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST
        )


class JoinOrAddStepsView(generics.GenericAPIView):
    """
    A unified view that allows a user to:
    - Join a step campaign (if not already joined today)
    - Continue a campaign session
    - Add steps to the current session (if `steps` is provided)
    """
    serializer_class = StepCountSessionSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        logger.info("User attempting to join or update a step campaign session.")
        decrypted_payload = decrypt(request.data)

        campaign_id = decrypted_payload.get("campaign_id")
        steps_to_add = decrypted_payload.get("steps")

        if not campaign_id:
            return Response(
                encrypt({"status": "error", "message": "Campaign ID is required."}),
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate steps (if provided)
        if steps_to_add is not None:
            try:
                steps_to_add = int(steps_to_add)
                if steps_to_add <= 0:
                    raise ValueError
            except (ValueError, TypeError):
                return Response(
                    encrypt({"status": "error", "message": "Steps must be a positive integer."}),
                    status=status.HTTP_400_BAD_REQUEST
                )

        # Retrieve the campaign
        try:
            campaign = StepCampaignModel.objects.get(campaign_id=campaign_id)
        except StepCampaignModel.DoesNotExist:
            return Response(
                encrypt({"status": "error", "message": "Campaign not found."}),
                status=status.HTTP_404_NOT_FOUND
            )

        if not campaign.is_campaign_active:
            return Response(
                encrypt({"status": "error", "message": "Campaign has expired."}),
                status=status.HTTP_400_BAD_REQUEST
            )

        session_date = timezone.now().date()

        # Get or create the session
        step_session, created = StepSessionModel.objects.get_or_create(
            campaign=campaign,
            user=request.user,
            session_date=session_date,
            defaults={"started_at": timezone.now()},
        )

        # Check personal time limit
        if not step_session.can_still_accumulate:
            return Response(
                encrypt({"status": "error", "message": "Your personal time limit has expired."}),
                status=status.HTTP_403_FORBIDDEN
            )

        # Add steps if provided
        if steps_to_add is not None:
            step_session.step_count += steps_to_add
            step_session.save()
            completed = step_session.check_completion()
            message = "Steps added successfully."
        else:
            completed = step_session.completed
            message = "Session is active."

        # Prepare response
        serializer = self.get_serializer(step_session)
        return Response(
            encrypt({
                "status": "success",
                "message": message,
                "data": {
                    **serializer.data,
                    "total_steps": step_session.total_steps,
                    "completed": completed,
                    "time_limit": campaign.time_limit,
                    "campaign_end_time": campaign.campaign_end_time,
                }
            }),
            status=status.HTTP_200_OK
        )


class GetMemberPointsSummary(generics.GenericAPIView):
    """
    GetMemberPointsSummary is the GET request handler that allows a user to
    retrieve their points summary from NextBee.
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, HasCompletedSurvey)

    def get(self, request, *args, **kwargs):
        member_email = request.user.email
        response = NextBee.points_summary(member_email)

        user = request.user
        user.total_points = response.json().get("points").get("available", 0) if isinstance(response, Response) else 0
        user.update_level()
        user.save()

        if isinstance(response, Response):
            return response
        return Response(
            data=encrypt(
                {
                    "status": "success",
                    "message": "Points summary retrieved successfully.",
                    "data": response.json() if response.status_code == 200 else response.text
                }
            ),
            status=status.HTTP_200_OK
        )
