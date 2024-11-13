import logging
from decouple import config

# Third party imports
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.pagination import PageNumberPagination

# In project imports.
from .serializers import (
    CreateBrandAdvertSeriailizers,
    BrandAdProfileSerializers,
    UpdateBrandAdProfileSerializers,
    BrandSurveySerializers,
    AdBudgetSerializer,
)

# from mail import send_email
from accounts.models import User, UserNotification, AccountType
from permissions import IsBrandAd, IsBrandAdAdmin
from .models import CreateAd, AdLocation
from banking.helpers import Pin
from banking.controllers import Account
from banking.models import AccountCreation
from roles.models import ActivityModel


picadailys_email = config("EMAIL_HOST_USER")
app_password = config("EMAIL_HOST_PASSWORD")

logger = logging.getLogger(__name__)


class PaginationStyle(PageNumberPagination):
    page_size = 20


class CreateBrandAdvertsAccount(generics.GenericAPIView):
    serializer_class = CreateBrandAdvertSeriailizers

    def post(self, request):
        # Clean up input data by stripping whitespace from string fields
        user_data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in request.data.items()
        }
        authenticated_user = request.user
        serializer = self.serializer_class(data=user_data)

        logger.info("Attempting to create brand advert account for user: %s", authenticated_user.email)

        if serializer.is_valid(raise_exception=True):
            # Save the new brand advert data
            serializer.save()
            logger.info("Brand advert data saved successfully for user: %s", authenticated_user.email)

            # Create a user notification
            UserNotification.objects.create(
                user=authenticated_user,
                title="Brand Account",
                message="Brand advert account created successfully."
            )
            logger.info("User notification created for brand advert account.")

            # Retrieve the saved brand user and update account type
            brand_user = User.objects.get(email=authenticated_user.email)
            AccountType.objects.create(
                user=brand_user,
                user_type="BrandAd"
            )
            brand_user.active_role = "BrandAd"
            brand_user.save()
            logger.info("User's active role set to 'BrandAd' and AccountType updated.")

            # Log the activity for the user's brand registration
            ActivityModel.objects.create(
                user=brand_user,
                title="Brand Register",
                description=f"{brand_user.first_name} {brand_user.last_name} registered as {brand_user.whoareyou}."
            )
            logger.info("Activity logged for brand registration of user: %s", brand_user.email)

            # Build the response
            response = {
                "status": "success",
                "message": "Brand advert account created successfully.",
                "data": {
                    "whoareyou": request.data.get("whoareyou"),
                    "facebook": request.data.get("facebook"),
                    "twitter": request.data.get("twitter"),
                    "instagram": request.data.get("instagram"),
                    "telegram": request.data.get("telegram"),
                },
            }
            return Response(data=response, status=status.HTTP_201_CREATED)

        # Log errors if serializer is invalid
        logger.error("Failed to create brand advert account: %s", serializer.errors)
        return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ListAllBrandAds(generics.ListAPIView):
    serializer_class = BrandAdProfileSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated & (IsBrandAd | IsBrandAdAdmin)]
    pagination_class = PaginationStyle

    def get_queryset(self):
        # Log the query request for all BrandAds
        logger.info("Retrieving queryset for BrandAd users.")
        return User.objects.filter(active_role="BrandAd")

    def list(self, request, *args, **kwargs):
        logger.info("ListAllBrandAds view accessed by user: %s", request.user.email)

        # Retrieve the queryset
        queryset = self.get_queryset()

        # Paginate the queryset
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.serializer_class(page, many=True)
            logger.info("Paginated response for BrandAd users. Page size: %d", len(page))
            return self.get_paginated_response(serializer.data)

        # If pagination is not applied, return the full response
        serializer = self.serializer_class(queryset, many=True)
        logger.info("Returning full response for BrandAd users. Total count: %d", queryset.count())
        return Response(serializer.data, status=status.HTTP_200_OK)


class GetBrandAdDetails(generics.RetrieveAPIView):
    """GetBrandAdDetails returns the profile details of a brand_Ad user."""

    serializer_class = BrandAdProfileSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated & (IsBrandAd | IsBrandAdAdmin)]

    def retrieve(self, request, *args, **kwargs):
        user = request.user
        logger.info("GetBrandAdDetails accessed by user: %s", user.email)

        # Serialize and return the user's profile details
        serializer = self.get_serializer(user)
        logger.info("Successfully retrieved profile for user: %s", user.email)
        return Response(serializer.data, status=status.HTTP_200_OK)


class UpdateBrandAdProfile(generics.UpdateAPIView):
    """Update brand_Ad Profile"""

    serializer_class = UpdateBrandAdProfileSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated & (IsBrandAd | IsBrandAdAdmin)]

    def get_object(self):
        return self.request.user

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()

        # Logging the attempt to update profile
        logger.info("User %s is attempting to update their BrandAd profile.", instance.email)

        serializer = self.get_serializer(instance, data=request.data, partial=partial)

        # Checking if data is valid and logging any errors
        if serializer.is_valid():
            self.perform_update(serializer)
            logger.info("Profile updated successfully for user: %s", instance.email)
            return Response(serializer.data, status=status.HTTP_200_OK)
        else:
            logger.error("Failed to update profile for user: %s. Errors: %s", instance.email, serializer.errors)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class BrandSurveyView(generics.CreateAPIView):
    serializer_class = BrandSurveySerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsBrandAd)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)

        if not serializer.is_valid(raise_exception=True):
            # In case of validation errors
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        try:
            # Attach authenticated user to the survey data
            serializer.validated_data["user"] = request.user
            brand_survey = serializer.save()

            # Create survey instance in CreateAd model
            brand_survey_instance = CreateAd.objects.create(
                brand_user=brand_survey.user,
                brand_type=serializer.validated_data["brand_type"],
                product_type=serializer.validated_data["product_type"],
                online_presence=serializer.validated_data["online_presence"],
                online_preferences=serializer.validated_data["online_preferences"],
                metric_to_increase=serializer.validated_data["metric_to_increase"],
                demography=serializer.validated_data["demography"],
                website=serializer.validated_data["website"],
                type=serializer.validated_data["type"],
                category=serializer.validated_data["category"],
                address=serializer.validated_data["address"],
                description=serializer.validated_data["description"],
                duration=serializer.validated_data["duration"],
            )

            # Create AdLocation entry for the survey
            AdLocation.objects.create(
                brand=brand_survey_instance,
                state=serializer.validated_data.get("state"),
                city=serializer.validated_data.get("city"),
            )

            # Log the brand survey activity
            ActivityModel.objects.create(
                user=brand_survey_instance,
                title="Brand Survey",
                description=f"{brand_survey_instance.brand_user} conducted a brand survey successfully.",
            )

            logger.info("Brand survey created successfully for user: %s", request.user.email)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        except Exception as err:
            logger.error("Brand advert survey creation failed: %s", err)
            return Response({"error": "An error occurred while creating the brand survey."},
                            status=status.HTTP_400_BAD_REQUEST)


class BrandPromote(generics.CreateAPIView):
    serializer_class = AdBudgetSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsBrandAd)

    def create(self, request, *args, **kwargs):
        payload = {key: value.strip() if isinstance(value, str) else value for key, value in request.data.items()}
        serializer = self.get_serializer(data=payload)

        if serializer.is_valid(raise_exception=True):
            try:
                authenticated_user = request.user
                pin = request.data.get("pin")

                # Verify PIN
                is_verified = Pin.verify_pin(user=authenticated_user, pin=pin)
                if not is_verified:
                    logger.warning("PIN verification failed for user %s", authenticated_user.email)
                    return Response({"error": "Invalid PIN."}, status=status.HTTP_403_FORBIDDEN)

                # Debit Account
                price = request.data.get("price")
                user_details = AccountCreation.objects.get(user=authenticated_user)
                debit_response = Account.Debit(
                    debitAccount=user_details.account_number,
                    amount=price,
                    description="Debit for brand promotion",
                    transactionReference="",
                )

                # Check debit response
                if debit_response == 200:
                    serializer.save()
                    UserNotification.objects.create(
                        user=authenticated_user,
                        title="Brand Promotion",
                        message=f"Your payment of {price} for brand promotion was successful.",
                    )

                    ActivityModel.objects.create(
                        user=authenticated_user,
                        title="Brand Promotion",
                        description=f"{authenticated_user.whoareyou} promoted their brand successfully.",
                    )

                    logger.info("Brand promotion payment successful for user %s", authenticated_user.email)

                    response_data = {
                        "status": "Success!",
                        "message": "Brand advert promoted successfully.",
                    }
                    return Response(data=response_data, status=status.HTTP_200_OK)

                else:
                    # Handle debit failure
                    logger.error("Debit failed with response: %s", debit_response.json())
                    response_data = {
                        "status": "Failure",
                        "details": debit_response.json(),
                    }
                    return Response(data=response_data, status=status.HTTP_400_BAD_REQUEST)

            except AccountCreation.DoesNotExist:
                logger.error("Account details not found for user %s", authenticated_user.email)
                return Response({"error": "Account details not found."}, status=status.HTTP_404_NOT_FOUND)

            except Exception as err:
                logger.exception("An error occurred during brand promotion for user %s: %s", authenticated_user.email, err)
                return Response({"error": "An error occurred during promotion."}, status=status.HTTP_400_BAD_REQUEST)

        # If serializer errors exist
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)