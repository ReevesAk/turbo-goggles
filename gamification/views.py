import logging
from decimal import Decimal
from decouple import config as conf
import rest_framework.serializers as s
from drf_spectacular.utils import (
    extend_schema,
    OpenApiExample,
    inline_serializer,
)
from django.utils import timezone
from django.db import transaction
from django.db.models import F
from django.db.models.functions import Greatest, Least
from django.core.cache import cache

from accounts.models import User, TxModel, UserNotification

from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from rest_framework import generics
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.response import Response

from banking.models import WalletModel
from banking.controllers import Wallet
from banking.helpers import verify_wallet_auth

from .serializers import (
    SSOLoginSerializer,
    StepCountSessionSerializer,
    SocialEngagementSerializer,
    StreakChallengeSerializer,
    UserStreakSerializer,
    StreakHistorySerializer,
    StreakLeaderboardEntrySerializer,
    RedeemPointsToWalletSerializer,
)
from .models import (
    StepCampaignModel,
    StepSessionModel,
    StreakChallenge,
    UserStreak,
    StreakHistory,
    Points as PointsModel,
    TIER_TO_RATE,
)

from gamification.utils import NextBee
from gamification.points import Points, TIER_VALUES, MIN_POINTS_REQUIRED
from commons import generate_txId
from security import encrypt, decrypt
from permissions import IsMember, HasCompletedSurvey
from user_profile.choices import LEVELS

GAMIFICATION_BASE_URL = conf("NEXTBEE_GAMIFICATION_BASE_URL")
REDEEM_CHARGE = Decimal("20.00")

SOCIAL_ACTIVITY_IDS = {
    "facebook": "48624",
    "instagram": "48626",
    "X": "48623",
    "tiktok": "48625",
}

logger = logging.getLogger(__name__)


# Create your views here.
@extend_schema(
    summary="SSO login for NextBee gamification portal",
    tags=["Gamification"],
    description="Initiates a Single Sign-On session for the authenticated member into the NextBee gamification portal, returning a redirect URL and session token.",
    request=SSOLoginSerializer,
    responses={
        200: inline_serializer(
            name="SSOLoginSuccessResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "gamificcation_redirect_url": s.CharField(),
                "token": s.CharField(allow_null=True),
            },
        ),
        400: inline_serializer(
            name="SSOLoginErrorResponse",
            fields={"error": s.CharField()},
        ),
    },
)
class NextBeeGamificationLSSOLogin(generics.GenericAPIView):
    """NextBeeGamificationLSSOLogin is the POST request handler for
    NextBee Gamification SSO login.
    """

    serializer_class = SSOLoginSerializer
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
                email=email, first_name=user.first_name, last_name=user.last_name
            )

            if resp.status_code != 200:
                logger.error(
                    f"NextBee API Error - Status: {resp.status_code}, Response: {resp.text}"
                )
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
                            "token": resp.json().get("token", None),
                        }
                    ),
                    status=status.HTTP_200_OK,
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


@extend_schema(
    summary="Join a step campaign",
    tags=["Gamification"],
    description="Enrolls the authenticated member into a step campaign. If the user has already joined, their existing session details are returned.",
    request=StepCountSessionSerializer,
    responses={
        201: inline_serializer(
            name="JoinCampaignResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "data": StepCountSessionSerializer(),
            },
        ),
        400: inline_serializer(
            name="JoinCampaignErrorResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        404: inline_serializer(
            name="JoinCampaignNotFoundResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class JoinCampaignView(generics.CreateAPIView):
    """
    Allows a user to join a step campaign.
    Creates a new session for today if not already joined.
    """

    serializer_class = StepCountSessionSerializer
    permission_classes = (IsAuthenticated, IsMember, HasCompletedSurvey)

    def post(self, request, *args, **kwargs):
        logger.info(f"User {request.user.id} attempting to join a step campaign.")

        campaign_id = kwargs.get("campaign_id")
        if not campaign_id:
            return self._error_response(
                "Campaign ID is required.", status.HTTP_400_BAD_REQUEST
            )

        # Validate campaign
        try:
            campaign = StepCampaignModel.objects.get(campaign_id=campaign_id)
        except StepCampaignModel.DoesNotExist:
            return self._error_response(
                message="Campaign not found.", status_code=status.HTTP_404_NOT_FOUND
            )

        if not campaign.is_campaign_active:
            return self._error_response(
                message="Campaign has expired.", status_code=status.HTTP_400_BAD_REQUEST
            )

        # Check if user already joined today
        existing_session = StepSessionModel.objects.filter(
            campaign=campaign, user=request.user
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
                },
            )

        # Create new session
        step_session = StepSessionModel.objects.create(
            campaign=campaign, user=request.user, started_at=timezone.now()
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
            },
        )

    def _error_response(self, message, status_code):
        return Response(
            encrypt({"status": "fail", "message": message}), status=status_code
        )

    def _success_response(self, message, data):
        return Response(
            encrypt({"status": "success", "message": message, "data": data}),
            status=status.HTTP_201_CREATED,
        )


@extend_schema(
    summary="Add steps to an active campaign session",
    tags=["Gamification"],
    description="Records steps taken by the member for an active campaign session. Excess steps beyond the target are trimmed automatically.",
    request=inline_serializer(
        name="AddStepsRequest",
        fields={"step_count": s.IntegerField(min_value=1)},
    ),
    responses={
        200: inline_serializer(
            name="AddStepsResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "data": StepCountSessionSerializer(),
            },
        ),
        400: inline_serializer(
            name="AddStepsErrorResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        403: inline_serializer(
            name="AddStepsForbiddenResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        404: inline_serializer(
            name="AddStepsNotFoundResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class AddStepsView(generics.UpdateAPIView):
    """
    Syncs a user's progress on their current campaign session.

    The client sends its own cumulative step count for this session (i.e.
    "I'm at 42 steps so far"), not an incremental delta. The server only
    ever moves step_count forward to that value (capped at the campaign's
    target) - it never adds on top of it. This makes a resent/duplicate
    sync request (e.g. after a dropped connection) a harmless no-op instead
    of double-counting.
    """

    serializer_class = StepCountSessionSerializer
    permission_classes = (IsAuthenticated, IsMember, HasCompletedSurvey)

    def post(self, request, *args, **kwargs):
        logger.info(f"User {request.user.id} attempting to add steps.")
        decrypted_payload = decrypt(request.data)
        user = request.user

        campaign_id = kwargs.get("campaign_id")
        # The app's cumulative step count for this session so far - not a
        # delta since the last sync. See AddStepsView docstring.
        reported_total = decrypted_payload.get("step_count")

        if not campaign_id:
            return self._error_response(
                message="Campaign ID is required.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        if reported_total is None:
            return self._error_response(
                message="Steps are required.", status_code=status.HTTP_400_BAD_REQUEST
            )

        # Validate steps
        try:
            reported_total = int(reported_total)
            if reported_total < 0:
                raise ValueError
        except (ValueError, TypeError):
            return self._error_response(
                message="Steps must be a non-negative integer.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # Get all user's sessions for this campaign
        sessions = StepSessionModel.objects.filter(
            campaign__campaign_id=campaign_id, user=request.user
        ).order_by(
            "started_at"
        )  # Keep the oldest as main session

        if not sessions.exists():
            return self._error_response(
                message="You haven't joined this campaign. Please join first.",
                status_code=status.HTTP_404_NOT_FOUND,
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

                logger.info(
                    f"Merged {sessions.count()} sessions with total {total_combined_steps} steps"
                )

            step_session = main_session

        # Check if campaign is already completed
        if step_session.completed:
            return self._error_response(
                message="You have already completed this campaign. No more steps can be added.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # Check if user can still accumulate steps
        if not step_session.can_still_accumulate:
            return self._error_response(
                message="Your personal time limit has expired.",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        # Check current progress
        current_total = step_session.step_count
        step_target = step_session.campaign.step_target

        if current_total >= step_target:
            return self._error_response(
                message="You have already reached the step target for this campaign.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        steps_trimmed = max(reported_total - step_target, 0)
        if steps_trimmed:
            logger.info(
                f"Reported total {reported_total} exceeds target {step_target}. Capping at target."
            )

        # Move step_count forward to the reported total (capped at the
        # target), never past it and never adding on top of it. GREATEST
        # keeps a stale/duplicate resend (a value <= the current total) a
        # no-op, and LEAST enforces the cap - both atomically at the DB
        # level so concurrent syncs can't race each other.
        with transaction.atomic():
            StepSessionModel.objects.filter(id=step_session.id).update(
                step_count=Least(Greatest(F("step_count"), reported_total), step_target)
            )

            # Refresh the instance to get updated values
            step_session.refresh_from_db()
            completed = step_session.check_completion()

        steps_accepted = step_session.step_count - current_total

        logger.info(
            f"Session {step_session.session_id} step_count now {step_session.step_count} "
            f"(+{steps_accepted} from this sync)"
        )

        # Prepare response message
        if steps_accepted <= 0:
            message = "No new steps recorded."
        elif steps_trimmed > 0:
            message = f"Recorded {steps_accepted} steps, capped at the {step_target}-step target. Campaign completed!"
        else:
            just_completed = completed and step_session.step_count == step_target
            completion_message = (
                " Congratulations! You've completed the campaign!"
                if just_completed
                else ""
            )
            message = f"Successfully recorded {steps_accepted} new steps!{completion_message}"

        # Award points exactly once, at the moment the session transitions to
        # completed (see the early "already completed" guard above - a
        # resent/duplicate sync can never reach this a second time).
        if completed:
            walk_points = Points.determine(activity_type="walk_to_earn", level=user.level)
            Points.award(
                user=user,
                amount=walk_points,
                reason=f"Completed walk-to-earn campaign '{step_session.campaign.name}'",
                source="walk_to_earn",
                reference_id=str(step_session.campaign.campaign_id),
            )

            if user.has_done_survey:
                special_points = Points.determine(
                    activity_type="special_campaign", level=user.level
                )
                Points.award(
                    user=user,
                    amount=special_points,
                    reason=f"Special campaign bonus for completing '{step_session.campaign.name}'",
                    source="special_campaign",
                    reference_id=str(step_session.campaign.campaign_id),
                )

        serializer = self.get_serializer(step_session)
        return self._success_response(
            message=message,
            data={
                **serializer.data,
                "total_steps": step_session.step_count,
                "completed": completed,
                "steps_requested": reported_total,
                "steps_accepted": steps_accepted,
                "steps_trimmed": steps_trimmed,
                "remaining_steps": max(step_target - step_session.step_count, 0),
                "time_limit": str(step_session.campaign.time_limit),
                "campaign_end_time": str(step_session.campaign.campaign_end_time),
            },
        )

    def _error_response(self, message, status_code):
        return Response(
            encrypt({"status": "fail", "message": message}), status=status_code
        )

    def _success_response(self, message, data):
        return Response(
            encrypt({"status": "success", "message": message, "data": data}),
            status=status.HTTP_200_OK,
        )


@extend_schema(
    summary="Get current status of a campaign session",
    tags=["Gamification"],
    description="Retrieves the member's progress, step totals, and time remaining for a specific campaign session.",
    responses={
        200: inline_serializer(
            name="CampaignStatusResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "data": StepCountSessionSerializer(),
            },
        ),
        400: inline_serializer(
            name="CampaignStatusErrorResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        404: inline_serializer(
            name="CampaignStatusNotFoundResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class CampaignStatusView(generics.RetrieveAPIView):
    """
    Retrieves the current status of a user's campaign session.
    Shows progress, remaining time, and completion status.
    """

    serializer_class = StepCountSessionSerializer
    permission_classes = (IsAuthenticated, IsMember, HasCompletedSurvey)

    def get(self, request, *args, **kwargs):
        logger.info(f"User {request.user.id} checking campaign status.")

        campaign_id = kwargs.get("campaign_id")
        if not campaign_id:
            return self._error_response(
                "Campaign ID is required.", status.HTTP_400_BAD_REQUEST
            )

        try:
            step_session = StepSessionModel.objects.select_related("campaign").get(
                campaign__campaign_id=campaign_id,
                user=request.user,
            )
        except StepSessionModel.DoesNotExist:
            return self._error_response(
                "You haven't joined this campaign today.", status.HTTP_404_NOT_FOUND
            )

        serializer = self.get_serializer(step_session)

        # Calculate progress percentage
        progress_percentage = (
            min(
                (step_session.total_steps / step_session.campaign.step_target) * 100,
                100,
            )
            if step_session.campaign.step_target > 0
            else 0
        )

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
            },
        )

    def _error_response(self, message, status_code):
        return Response(
            encrypt({"status": "fail", "message": message}), status=status_code
        )

    def _success_response(self, message, data):
        return Response(
            encrypt({"status": "success", "message": message, "data": data}),
            status=status.HTTP_200_OK,
        )


@extend_schema(
    summary="Submit social media activity image",
    tags=["Gamification"],
    description="Log a social media post activity for points. Upload the image to Cloudinary first, then send the URL here.",
    request=SocialEngagementSerializer,
    responses={
        200: inline_serializer(
            name="SubmitActivityImageResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        400: inline_serializer(
            name="SubmitActivityImageErrorResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
    examples=[
        OpenApiExample(
            "Facebook post",
            value={
                "platform": "facebook",
                "image_url": "https://res.cloudinary.com/example/image/upload/post.jpg",
            },
        ),
        OpenApiExample(
            "Instagram post",
            value={
                "platform": "instagram",
                "image_url": "https://res.cloudinary.com/example/image/upload/post.jpg",
            },
        ),
        OpenApiExample(
            "Twitter post",
            value={
                "platform": "twitter",
                "image_url": "https://res.cloudinary.com/example/image/upload/post.jpg",
            },
        ),
        OpenApiExample(
            "TikTok post",
            value={
                "platform": "tiktok",
                "image_url": "https://res.cloudinary.com/example/image/upload/post.jpg",
            },
        ),
    ],
)
class SubmitActivityImageView(generics.GenericAPIView):
    serializer_class = SocialEngagementSerializer
    permission_classes = (IsAuthenticated, IsMember, HasCompletedSurvey)

    def post(self, request, *args, **kwargs):
        decrypted_payload = decrypt(request.data)
        user = request.user

        image_url = decrypted_payload.get("image_url")
        platform = decrypted_payload.get("platform", "").lower()

        if not image_url:
            return Response(
                data=encrypt({"status": "fail", "message": "image_url is required."}),
                status=status.HTTP_400_BAD_REQUEST,
            )

        activity_id = SOCIAL_ACTIVITY_IDS.get(platform)
        if not activity_id:
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": f"Invalid platform. Choose from: {', '.join(SOCIAL_ACTIVITY_IDS.keys())}.",
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        points = Points.determine(activity_type="social_engagement", level=user.level)
        Points.award(
            user=user,
            amount=points,
            reason=f"Social engagement post on {platform}",
            source="social_engagement",
        )

        return Response(
            data=encrypt(
                {"status": "success", "message": "Activity submitted successfully."}
            ),
            status=status.HTTP_200_OK,
        )


@extend_schema(
    summary="Get member points summary",
    tags=["Gamification"],
    description="Returns the authenticated member's current points balance, tier, conversion rate, lifetime points, total streaks joined, and a full breakdown of every tier's threshold/rate plus the flat redemption charge and minimum.",
    responses={
        200: inline_serializer(
            name="MemberPointsSummaryResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "data": inline_serializer(
                    name="MemberPointsSummaryData",
                    fields={
                        "points_balance": s.IntegerField(),
                        "tier": s.CharField(),
                        "tier_rate": s.CharField(allow_null=True),
                        "naira_value": s.CharField(),
                        "lifetime_points": s.IntegerField(),
                        "streaks_joined": s.IntegerField(),
                        "tiers": inline_serializer(
                            name="MemberPointsSummaryTier",
                            fields={
                                "tier": s.CharField(),
                                "min_lifetime_points": s.IntegerField(),
                                "rate_per_point": s.CharField(),
                            },
                            many=True,
                        ),
                        "min_points_to_redeem": s.IntegerField(),
                        "redeem_charge": s.CharField(),
                    },
                ),
            },
        ),
    },
)
class GetMemberPointsSummary(generics.GenericAPIView):
    """
    Returns the authenticated user's points balance, tier, and tier rate,
    plus a full breakdown of every tier's threshold, rate, and the flat
    redemption charge/minimum - for use outside the app (mapping, display, etc).
    """

    permission_classes = (IsAuthenticated, IsMember, HasCompletedSurvey)

    def get(self, request, *args, **kwargs):
        user = request.user
        points_obj, _ = PointsModel.objects.get_or_create(user=user)
        tier = points_obj.tier
        rate = TIER_TO_RATE.get(tier)
        streaks_joined = UserStreak.objects.filter(user=user).count()

        tiers_breakdown = [
            {
                "tier": level["title"],
                "min_lifetime_points": level["min_points"],
                "rate_per_point": str(TIER_VALUES.get(level["title"], Decimal("0"))),
            }
            for level in LEVELS
        ]

        return Response(
            data=encrypt(
                {
                    "status": "success",
                    "message": "Points summary retrieved successfully.",
                    "data": {
                        "points_balance": points_obj.balance,
                        "tier": tier,
                        "tier_rate": str(rate) if rate is not None else None,
                        "naira_value": str(points_obj.naira_value),
                        "lifetime_points": user.total_points or 0,
                        "streaks_joined": streaks_joined,
                        "tiers": tiers_breakdown,
                        "min_points_to_redeem": MIN_POINTS_REQUIRED,
                        "redeem_charge": str(REDEEM_CHARGE),
                    },
                }
            ),
            status=status.HTTP_200_OK,
        )


@extend_schema(
    summary="Redeem points for wallet credit",
    tags=["Gamification"],
    description=(
        "Converts the authenticated member's redeemable points into naira and credits "
        "their wallet from the collection account, minus a flat ₦20 redemption charge. "
        "Requires PIN or biometric verification."
    ),
    request=RedeemPointsToWalletSerializer,
    responses={
        200: inline_serializer(
            name="RedeemPointsToWalletSuccessResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "data": inline_serializer(
                    name="RedeemPointsToWalletData",
                    fields={
                        "points_redeemed": s.IntegerField(),
                        "naira_value": s.CharField(),
                        "redeem_charge": s.CharField(),
                        "amount_credited": s.CharField(),
                        "transaction_reference": s.CharField(),
                    },
                ),
            },
        ),
        400: inline_serializer(
            name="RedeemPointsToWalletErrorResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class RedeemPointsToWallet(generics.GenericAPIView):
    """
    Redeems the authenticated member's redeemable points for wallet credit.

    Flow:
      1. Verify PIN/biometrics.
      2. Lock the user's Points row, compute the redeemable amount, and deduct the
         points (only the usable `balance` is touched — lifetime points, used for
         tier, are untouched). The lock is released once the atomic block exits.
      3. Credit the user's wallet via 9PSB (Wallet.Credit) for
         (naira_value - REDEEM_CHARGE). On failure, refund the points.
      4. Record a TxModel entry with the charge stored in `transfer_fee`.
    """

    serializer_class = RedeemPointsToWalletSerializer
    permission_classes = (IsAuthenticated, IsMember)

    def post(self, request, *args, **kwargs):
        user = request.user
        decrypted_payload = decrypt(request.data)

        serializer = self.get_serializer(data=decrypted_payload)
        if not serializer.is_valid():
            return Response(
                data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST
            )

        pin = serializer.validated_data.get("pin")
        use_biometrics = serializer.validated_data.get("use_biometrics", False)

        try:
            wallet = WalletModel.objects.get(user=user, walletType="INDIVIDUAL")
        except WalletModel.DoesNotExist:
            return Response(
                data=encrypt({"status": "fail", "message": "Wallet not found."}),
                status=status.HTTP_404_NOT_FOUND,
            )

        is_verified, error_response = verify_wallet_auth(
            user=user, payment_option="WALLET", pin=pin, use_biometrics=use_biometrics
        )
        if not is_verified:
            return error_response

        # Lock the points row, compute what's redeemable, and deduct it — all
        # inside one atomic block so the lock is released before we call out to 9PSB.
        with transaction.atomic():
            pts_obj, _ = PointsModel.objects.select_for_update().get_or_create(user=user)
            points_used, naira_value, _ = Points.calculate_redeemable(
                pts_obj.balance, user.total_points or 0
            )

            if points_used == 0:
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "message": "You have not reached the points redemption threshold.",
                        }
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )

            amount_to_credit = naira_value - REDEEM_CHARGE
            if amount_to_credit <= Decimal("0"):
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "message": "Redeemable amount is too low to cover the redemption charge.",
                        }
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )

            deducted, msg = Points.deduct(
                user=user,
                amount=points_used,
                reason=f"Redeemed {points_used} points for ₦{amount_to_credit} wallet credit",
                source="points_redemption",
            )
            if not deducted:
                logger.error("Points deduction failed for %s: %s", user.email, msg)
                return Response(
                    data=encrypt({"status": "fail", "message": "Could not deduct points."}),
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Credit the user's wallet — this is the call used to credit a user.
        credit_resp = Wallet.Credit(
            acct_no=wallet.account_number,
            amount=float(amount_to_credit),
            reason=f"Points redemption: {points_used} points redeemed",
        )
        if credit_resp is None or credit_resp.status_code != 200:
            Points.award(
                user=user,
                amount=points_used,
                reason="Refund: points redemption credit failed",
                source="admin_adjustment",
                bypass_credibility=True,
            )
            logger.error("Redeem credit failed for %s", user.email)
            return Response(
                data=encrypt({"status": "fail", "message": "Redemption failed. Please try again."}),
                status=status.HTTP_502_BAD_GATEWAY,
            )

        tx = TxModel.objects.create(
            user=user,
            tx_reference=generate_txId(),
            tx_type="Points Redemption to Wallet",
            amount=float(amount_to_credit),
            transfer_fee=float(REDEEM_CHARGE),
            description=f"Redeemed {points_used} points for ₦{amount_to_credit} wallet credit",
            status="SUCCESS",
        )

        UserNotification.objects.create(
            user=user,
            title="Points Redeemed",
            message=f"You redeemed {points_used} points for ₦{amount_to_credit} (₦{REDEEM_CHARGE} charge applied).",
        )

        logger.info(
            "User %s redeemed %d points for ₦%s (charge ₦%s)",
            user.email, points_used, amount_to_credit, REDEEM_CHARGE,
        )

        return Response(
            data=encrypt(
                {
                    "status": "success",
                    "message": "Points redeemed successfully.",
                    "data": {
                        "points_redeemed": points_used,
                        "naira_value": str(naira_value),
                        "redeem_charge": str(REDEEM_CHARGE),
                        "amount_credited": str(amount_to_credit),
                        "transaction_reference": str(tx.tx_reference),
                    },
                }
            ),
            status=status.HTTP_200_OK,
        )


# ── Streak Challenge views (user-facing) ─────────────────────────────────────
@extend_schema(
    summary="List active streak challenges",
    tags=["Gamification"],
    description="Returns all currently ongoing streak challenges visible to members, ordered by creation date.",
    responses={
        200: inline_serializer(
            name="ActiveStreakChallengesResponse",
            fields={
                "status": s.CharField(),
                "data": StreakChallengeSerializer(many=True),
            },
        ),
    },
)
class ActiveStreakChallengesView(generics.ListAPIView):
    """Returns all ongoing streak challenges. Used in the tasks/gamification feed."""

    serializer_class = StreakChallengeSerializer
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        today = timezone.now().date()
        return StreakChallenge.objects.filter(
            is_active=True,
            is_paused=False,
            start_date__lte=today,
            end_date__gte=today,
        ).order_by("-created_at")

    def list(self, request, *args, **kwargs):
        qs = self.get_queryset()
        data = StreakChallengeSerializer(qs, many=True).data
        return Response(
            data=encrypt({"status": "success", "data": data}),
            status=status.HTTP_200_OK,
        )


@extend_schema(
    summary="Join a streak challenge",
    tags=["Gamification"],
    description="Enrolls the authenticated user in a streak challenge. Returns the existing enrollment record if the user has already joined.",
    responses={
        200: inline_serializer(
            name="JoinStreakAlreadyJoinedResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "data": UserStreakSerializer(),
            },
        ),
        201: inline_serializer(
            name="JoinStreakCreatedResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "data": UserStreakSerializer(),
            },
        ),
        400: inline_serializer(
            name="JoinStreakErrorResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        404: inline_serializer(
            name="JoinStreakNotFoundResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class JoinStreakChallengeView(generics.GenericAPIView):
    serializer_class = UserStreakSerializer
    permission_classes = (IsAuthenticated,)

    def post(self, request, challenge_id):
        try:
            challenge = StreakChallenge.objects.get(id=challenge_id)
        except StreakChallenge.DoesNotExist:
            return Response(
                data=encrypt({"status": "fail", "message": "Challenge not found."}),
                status=status.HTTP_404_NOT_FOUND,
            )

        if not challenge.is_ongoing:
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "This challenge is not currently active.",
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        user_streak, created = UserStreak.objects.get_or_create(
            user=request.user,
            challenge=challenge,
        )

        msg = (
            "Joined successfully!"
            if created
            else "You have already joined this challenge."
        )
        return Response(
            data=encrypt(
                {
                    "status": "success",
                    "message": msg,
                    "data": UserStreakSerializer(user_streak).data,
                }
            ),
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


@extend_schema(
    summary="My streak progress across all joined challenges",
    tags=["Gamification"],
    description="Lists the authenticated user's streak progress records for every challenge they have enrolled in, ordered by most recently joined.",
    responses={
        200: inline_serializer(
            name="MyStreakProgressResponse",
            fields={
                "status": s.CharField(),
                "data": UserStreakSerializer(many=True),
            },
        ),
    },
)
class MyStreakProgressView(generics.ListAPIView):
    serializer_class = UserStreakSerializer
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        return (
            UserStreak.objects.filter(user=self.request.user)
            .select_related("challenge")
            .order_by("-joined_at")
        )

    def list(self, request, *args, **kwargs):
        data = UserStreakSerializer(self.get_queryset(), many=True).data
        return Response(
            data=encrypt({"status": "success", "data": data}),
            status=status.HTTP_200_OK,
        )


@extend_schema(
    summary="Leaderboard for a streak challenge",
    tags=["Gamification"],
    description="Returns the top 50 participants for a given streak challenge, ranked by current streak count then longest streak count.",
    responses={
        200: inline_serializer(
            name="StreakLeaderboardResponse",
            fields={
                "status": s.CharField(),
                "challenge": s.CharField(),
                "leaderboard": StreakLeaderboardEntrySerializer(many=True),
            },
        ),
        404: inline_serializer(
            name="StreakLeaderboardNotFoundResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class StreakLeaderboardView(generics.GenericAPIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request, challenge_id):
        try:
            challenge = StreakChallenge.objects.get(id=challenge_id)
        except StreakChallenge.DoesNotExist:
            return Response(
                data=encrypt({"status": "fail", "message": "Challenge not found."}),
                status=status.HTTP_404_NOT_FOUND,
            )

        user_streaks = (
            UserStreak.objects.filter(challenge=challenge)
            .select_related("user")
            .order_by("-current_count", "-longest_count")[:50]
        )

        leaderboard = [
            {
                "rank": idx + 1,
                "user_id": str(us.user.id),
                "full_name": (
                    us.user.get_full_name()
                    if hasattr(us.user, "get_full_name")
                    else str(us.user)
                ),
                "current_count": us.current_count,
                "longest_count": us.longest_count,
                "completed": us.completed,
            }
            for idx, us in enumerate(user_streaks)
        ]

        return Response(
            data=encrypt(
                {
                    "status": "success",
                    "challenge": challenge.name,
                    "leaderboard": leaderboard,
                }
            ),
            status=status.HTTP_200_OK,
        )


@extend_schema(
    summary="My streak history",
    tags=["Gamification"],
    description="Returns a full historical log of the authenticated user's streak activity across all challenges, ordered by most recent.",
    responses={
        200: inline_serializer(
            name="MyStreakHistoryResponse",
            fields={
                "status": s.CharField(),
                "data": StreakHistorySerializer(many=True),
            },
        ),
    },
)
class MyStreakHistoryView(generics.ListAPIView):
    serializer_class = StreakHistorySerializer
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        return (
            StreakHistory.objects.filter(user=self.request.user)
            .select_related("challenge")
            .order_by("-recorded_at")
        )

    def list(self, request, *args, **kwargs):
        data = StreakHistorySerializer(self.get_queryset(), many=True).data
        return Response(
            data=encrypt({"status": "success", "data": data}),
            status=status.HTTP_200_OK,
        )


@extend_schema(
    summary="All-time points leaderboard",
    tags=["Gamification"],
    description="Returns the top 100 users ranked by all-time earned points. Also includes the requesting user's own rank and points, even if they fall outside the top 100.",
    responses={
        200: inline_serializer(
            name="PointsLeaderboardResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "leaderboard": inline_serializer(
                    name="LeaderboardEntry",
                    fields={
                        "rank": s.IntegerField(),
                        "user_id": s.UUIDField(),
                        "full_name": s.CharField(),
                        "total_points": s.IntegerField(),
                        "tier": s.CharField(),
                    },
                    many=True,
                ),
                "my_rank": inline_serializer(
                    name="MyRankEntry",
                    fields={
                        "rank": s.IntegerField(),
                        "user_id": s.UUIDField(),
                        "full_name": s.CharField(),
                        "total_points": s.IntegerField(),
                        "tier": s.CharField(),
                    },
                ),
            },
        ),
    },
)
class PointsLeaderboardView(generics.GenericAPIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        cache_key = "points_leaderboard_top100"
        leaderboard = cache.get(cache_key)

        if leaderboard is None:
            top_users = (
                User.objects.filter(is_active=True, total_points__gt=0)
                .only("id", "full_name", "total_points")
                .order_by("-total_points")[:100]
            )
            leaderboard = [
                {
                    "rank": idx + 1,
                    "user_id": str(u.id),
                    "full_name": u.first_name + " " + u.last_name,
                    "total_points": u.total_points or 0,
                    "tier": Points.get_user_tier(u.total_points or 0),
                }
                for idx, u in enumerate(top_users)
            ]
            cache.set(cache_key, leaderboard, timeout=300)

        user = request.user
        user_rank = (
            User.objects.filter(
                is_active=True,
                total_points__gt=(user.total_points or 0),
            ).count()
            + 1
        )
        my_entry = {
            "rank": user_rank,
            "user_id": str(user.id),
            "full_name": user.first_name + " " + user.last_name,
            "total_points": user.total_points or 0,
            "tier": Points.get_user_tier(user.total_points or 0),
        }

        return Response(
            data=encrypt(
                {
                    "status": "success",
                    "message": "Leaderboard retrieved successfully.",
                    "leaderboard": leaderboard,
                    "my_rank": my_entry,
                }
            ),
            status=status.HTTP_200_OK,
        )
