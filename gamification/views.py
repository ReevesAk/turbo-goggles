import logging
from decouple import config as conf

from django.utils import timezone
from django.db import transaction
from django.db.models import F

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
from gamification.points import calculate_points
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
        user = request.user

        serializer = self.get_serializer(data=payload)
        if serializer.is_valid():
            email = serializer.validated_data["email"]
            nextbee = NextBee()
            resp = nextbee.sso_login(
                email=email,
                first_name=user.first_name,
                last_name=user.last_name
            )

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


class JoinCampaignView(generics.CreateAPIView):
    """
    Allows a user to join a step campaign.
    Creates a new session for today if not already joined.
    """
    serializer_class = StepCountSessionSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        logger.info(f"User {request.user.id} attempting to join a step campaign.")

        campaign_id = kwargs.get("campaign_id")
        if not campaign_id:
            return self._error_response("Campaign ID is required.", status.HTTP_400_BAD_REQUEST)

        # Validate campaign
        try:
            campaign = StepCampaignModel.objects.get(campaign_id=campaign_id)
        except StepCampaignModel.DoesNotExist:
            return self._error_response(message="Campaign not found.", status_code=status.HTTP_404_NOT_FOUND)

        if not campaign.is_campaign_active:
            return self._error_response(message="Campaign has expired.", status_code=status.HTTP_400_BAD_REQUEST)

        # Check if user already joined today
        existing_session = StepSessionModel.objects.filter(
            campaign=campaign,
            user=request.user
        ).first()

        if existing_session:
            # Return the existing session instead of error
            serializer = self.get_serializer(existing_session)
            return self._success_response(
                "You are already part of this campaign!",
                {
                    **serializer.data,
                    "total_steps": existing_session.step_count,
                    "completed": existing_session.completed,
                    "time_limit": str(campaign.time_limit),
                    "campaign_end_time": str(campaign.campaign_end_time),
                }
            )

        # Create new session
        step_session = StepSessionModel.objects.create(
            campaign=campaign,
            user=request.user,
            started_at=timezone.now()
        )

        serializer = self.get_serializer(step_session)
        return self._success_response(
            message="Successfully joined the campaign!",
            data={
                **serializer.data,
                "total_steps": step_session.total_steps,
                "completed": step_session.completed,
                "time_limit": str(campaign.time_limit),
                "campaign_end_time": str(campaign.campaign_end_time),
            }
        )

    def _error_response(self, message, status_code):
        return Response(
            encrypt({"status": "error", "message": message}),
            status=status_code
        )

    def _success_response(self, message, data):
        return Response(
            encrypt({"status": "success", "message": message, "data": data}),
            status=status.HTTP_201_CREATED
        )


class AddStepsView(generics.UpdateAPIView):
    """
    Allows a user to add steps to their current campaign session.
    Users can add steps in batches throughout the day.
    """
    serializer_class = StepCountSessionSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        logger.info(f"User {request.user.id} attempting to add steps.")
        decrypted_payload = decrypt(request.data)
        user = request.user

        campaign_id = kwargs.get("campaign_id")
        steps_to_add = decrypted_payload.get("step_count")

        if not campaign_id:
            return self._error_response(message="Campaign ID is required.", status_code=status.HTTP_400_BAD_REQUEST)

        if not steps_to_add:
            return self._error_response(message="Steps are required.", status_code=status.HTTP_400_BAD_REQUEST)

        # Validate steps
        try:
            steps_to_add = int(steps_to_add)
            if steps_to_add <= 0:
                raise ValueError
        except (ValueError, TypeError):
            return self._error_response(
                message="Steps must be a positive integer.",
                status_code=status.HTTP_400_BAD_REQUEST
            )

        # Get all user's sessions for this campaign
        sessions = StepSessionModel.objects.filter(
            campaign__campaign_id=campaign_id,
            user=request.user
        ).order_by('started_at')  # Keep the oldest as main session

        if not sessions.exists():
            return self._error_response(
                message="You haven't joined this campaign. Please join first.",
                status_code=status.HTTP_404_NOT_FOUND
            )

        # Merge sessions into one if multiple exist
        with transaction.atomic():
            main_session = sessions.first()

            # If there are multiple sessions, merge them
            if sessions.count() > 1:
                total_combined_steps = sum(session.step_count for session in sessions)

                # Update main session with combined steps
                main_session.step_count = total_combined_steps
                main_session.last_updated = timezone.now()
                main_session.save()

                # Delete duplicate sessions
                sessions.exclude(id=main_session.id).delete()

                logger.info(f"Merged {sessions.count()} sessions with total {total_combined_steps} steps")

            step_session = main_session

        # Check if campaign is already completed
        if step_session.completed:
            return self._error_response(
                message="You have already completed this campaign. No more steps can be added.",
                status_code=status.HTTP_400_BAD_REQUEST
            )

        # Check if user can still accumulate steps
        if not step_session.can_still_accumulate:
            return self._error_response(
                message="Your personal time limit has expired.",
                status_code=status.HTTP_403_FORBIDDEN
            )

        # Check current progress
        current_total = step_session.step_count
        step_target = step_session.campaign.step_target

        if current_total >= step_target:
            return self._error_response(
                message="You have already reached the step target for this campaign.",
                status_code=status.HTTP_400_BAD_REQUEST
            )

        # Trim steps if it would exceed target, but still accept the request
        steps_accepted = steps_to_add
        steps_trimmed = 0

        if current_total + steps_to_add > step_target:
            steps_accepted = step_target - current_total
            steps_trimmed = steps_to_add - steps_accepted
            logger.info(f"Trimmed {steps_trimmed} excess steps. Accepting {steps_accepted} steps.")

        # Add steps atomically to prevent race conditions
        with transaction.atomic():
            StepSessionModel.objects.filter(
                id=step_session.id
            ).update(step_count=F('step_count') + steps_accepted)

            # Refresh the instance to get updated values
            step_session.refresh_from_db()
            completed = step_session.check_completion()

        logger.info(f"Added {steps_accepted} steps to session {step_session.session_id}")

        # Prepare response message
        if steps_trimmed > 0:
            message = f"Added {steps_accepted} steps and trimmed {steps_trimmed} excess steps. Campaign completed!"
        else:
            just_completed = completed and step_session.step_count == step_target
            completion_message = " Congratulations! You've completed the campaign!" if just_completed else ""
            message = f"Successfully added {steps_accepted} steps!{completion_message}"

        points = calculate_points(activity_type="special_campaign", level=user.level)
        NextBee.member_activity(
            member_email=user.email, activityId="8474", numericValue=str(points)
        )

        serializer = self.get_serializer(step_session)
        return self._success_response(
            message=message,
            data={
                **serializer.data,
                "total_steps": step_session.step_count,
                "completed": completed,
                "steps_requested": steps_to_add,
                "steps_accepted": steps_accepted,
                "steps_trimmed": steps_trimmed,
                "remaining_steps": max(step_target - step_session.step_count, 0),
                "time_limit": str(step_session.campaign.time_limit),
                "campaign_end_time": str(step_session.campaign.campaign_end_time),
            }
        )

    def _error_response(self, message, status_code):
        return Response(
            encrypt({"status": "error", "message": message}),
            status=status_code
        )

    def _success_response(self, message, data):
        return Response(
            encrypt({"status": "success", "message": message, "data": data}),
            status=status.HTTP_200_OK
        )


class CampaignStatusView(generics.RetrieveAPIView):
    """
    Retrieves the current status of a user's campaign session.
    Shows progress, remaining time, and completion status.
    """
    serializer_class = StepCountSessionSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        logger.info(f"User {request.user.id} checking campaign status.")

        campaign_id = kwargs.get("campaign_id")
        if not campaign_id:
            return self._error_response("Campaign ID is required.", status.HTTP_400_BAD_REQUEST)

        try:
            step_session = StepSessionModel.objects.select_related('campaign').get(
                campaign__campaign_id=campaign_id,
                user=request.user,
            )
        except StepSessionModel.DoesNotExist:
            return self._error_response(
                "You haven't joined this campaign today.", 
                status.HTTP_404_NOT_FOUND
            )

        serializer = self.get_serializer(step_session)

        # Calculate progress percentage
        progress_percentage = min(
            (step_session.total_steps / step_session.campaign.step_target) * 100, 100
        ) if step_session.campaign.step_target > 0 else 0

        return self._success_response(
            "Campaign status retrieved successfully.",
            {
                **serializer.data,
                "total_steps": step_session.total_steps,
                "completed": step_session.completed,
                "progress_percentage": round(progress_percentage, 2),
                "can_still_accumulate": step_session.can_still_accumulate,
                "time_limit": step_session.campaign.time_limit,
                "campaign_end_time": step_session.campaign.campaign_end_time,
                "personal_deadline": step_session.personal_deadline,
            }
        )

    def _error_response(self, message, status_code):
        return Response(
            encrypt({"status": "error", "message": message}),
            status=status_code
        )

    def _success_response(self, message, data):
        return Response(
            encrypt({"status": "success", "message": message, "data": data}),
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
