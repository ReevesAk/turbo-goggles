import logging
from urllib.parse import urlparse

from django.core.validators import URLValidator
from django.core.exceptions import ValidationError as DjangoValidationError

# Third party imports
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.pagination import PageNumberPagination

# In project imports.
from .serializers import (
    OnboardBrandSerializer,
    BrandAdProfileSerializers,
    UpdateBrandAdProfileSerializers,
    CreateAdSerializers,
    AdBudgetSerializer,
    AdSerializers,
)

# from mail import send_email
from accounts.models import User, UserNotification, AccountType
from permissions import IsBrandAd, IsBrandAdAdmin
from .models import CreateAd, AdBudget
from banking.helpers import Pin
from banking.controllers import Account
from banking.models import AccountCreation
from roles.models import ActivityModel
from security import encrypt, decrypt


logger = logging.getLogger(__name__)


class PaginationStyle(PageNumberPagination):
    page_size = 20


class OnboardBrandAdvertsAccount(generics.GenericAPIView):
    serializer_class = OnboardBrandSerializer

    def post(self, request):
        decrypted_payload = decrypt(request.data)
        user_data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_payload.items()
        }
        authenticated_user = request.user
        serializer = self.serializer_class(data=user_data)

        logger.info(
            "Attempting to create brand advert account for user: %s",
            authenticated_user.email,
        )

        if serializer.is_valid(raise_exception=True):
            urls = ["facebook", "twitter", "instagram", "telegram"]
            url_validator = URLValidator()

            for field_name in urls:
                url = user_data.get(field_name, "")

                if url:
                    # Check if the URL has a scheme; if not, prepend 'https://'
                    parsed_url = urlparse(url)
                    if not parsed_url.scheme:
                        url = f"https://{url}"

                    try:
                        url_validator(url)
                        logger.debug(f"{field_name} URL validated: {url}")
                    except DjangoValidationError:
                        logger.error(f"Invalid URL format for {field_name}: {url}")
                        response_data = {
                            "status": "fail",
                            "message": f"{field_name}: Invalid URL format",
                        }
                        return Response(
                            data=encrypt(response_data),
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                    user_data[field_name] = url

            # Save the new brand advert data
            try:
                serializer.save()
                logger.info("Brand user Onboarded successfully")
            except Exception as e:
                logger.error(f"Error onboarding brand user: {e}")
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "message": "An error occurred while onboarding the user.",
                        }
                    ),
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

            logger.info(
                "Brand advert data saved successfully for user: %s",
                authenticated_user.email,
            )

            # Create a user notification
            UserNotification.objects.create(
                user=authenticated_user,
                title="Brand Account",
                message="Brand advert account created successfully.",
            )
            logger.info("User notification created for brand advert account.")

            # Retrieve the saved brand user and update account type
            brand_user = User.objects.get(email=authenticated_user.email)
            AccountType.objects.create(user=brand_user, user_type="BrandAd")
            brand_user.active_role = "BrandAd"
            brand_user.save()
            logger.info("User's active role set to 'BrandAd' and AccountType updated.")

            # Log the activity for the user's brand registration
            ActivityModel.objects.create(
                user=brand_user,
                title="Brand Register",
                description=f"{brand_user.first_name} {brand_user.last_name} registered as {brand_user.whoareyou}.",
            )
            logger.info(
                "Activity logged for brand registration of user: %s", brand_user.email
            )

            # Build the response
            response = {
                "status": "success",
                "message": "Brand advert account created successfully.",
                "data": {
                    "whoareyou": user_data.get("whoareyou"),
                    "name": user_data.get("name"),
                    "address": user_data.get("address"),
                    "brand_email": user_data.get("brand_email"),
                    "brand_type": user_data.get("brand_type"),
                    "brand_name": user_data.get("brand_name"),
                    "facebook": user_data.get("facebook"),
                    "twitter": user_data.get("twitter"),
                    "instagram": user_data.get("instagram"),
                    "telegram": user_data.get("telegram"),
                },
            }
            return Response(data=encrypt(response), status=status.HTTP_201_CREATED)
        else:
            # Log errors if serializer is invalid
            logger.error("Failed to create brand advert account: %s", serializer.errors)
            return Response(
                data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST
            )


class ListAllBrandAdsUsers(generics.ListAPIView):
    serializer_class = BrandAdProfileSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, IsBrandAdAdmin]
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
            logger.info(
                "Paginated response for BrandAd users. Page size: %d", len(page)
            )
            response_data = self.get_paginated_response(serializer.data).data
            return Response(data=encrypt(response_data), status=status.HTTP_200_OK)

        # If pagination is not applied, return the full response
        serializer = self.serializer_class(queryset, many=True)
        logger.info(
            "Returning full response for BrandAd users. Total count: %d",
            queryset.count(),
        )
        response = {
            "status": "success",
            "message": "All brand ad users retrieved successfully!",
            "data": serializer.data,
        }
        encrypted_response = encrypt(response)
        return Response(data=encrypted_response, status=status.HTTP_200_OK)


class ListAllBrandAds(generics.ListAPIView):
    serializer_class = AdSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated & (IsBrandAd | IsBrandAdAdmin)]
    pagination_class = PaginationStyle

    def get_queryset(self):
        user = self.request.user
        logger.info("Retrieving all ads created by BrandAd users.")
        return (
            CreateAd.objects.filter(user=user)
            .select_related("user")
            .prefetch_related("brand_location")
        )

    def list(self, request, *args, **kwargs):
        logger.info("ListAllBrandAds view created by user: %s", request.user.email)
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        serializer = (
            self.serializer_class(page, many=True)
            if page
            else self.serializer_class(queryset, many=True)
        )
        response_data = (
            self.get_paginated_response(serializer.data).data
            if page
            else serializer.data
        )
        response = {
            "status": "success",
            "message": "All created ads retrieved successfully!",
            "data": response_data,
        }
        encrypted_response = encrypt(response)
        return Response(data=encrypted_response, status=status.HTTP_200_OK)


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
        response = {
            "status": "success",
            "message": "Ad detail retrieved successfully!",
            "data": serializer.data,
        }
        encrypted_response = encrypt(response)
        return Response(data=encrypted_response, status=status.HTTP_200_OK)


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
        logger.info(
            "User %s is attempting to update their BrandAd profile.", instance.email
        )
        decrypted_payload = decrypt(request.data)
        serializer = self.get_serializer(
            instance, data=decrypted_payload, partial=partial
        )

        # Checking if data is valid and logging any errors
        if serializer.is_valid():
            self.perform_update(serializer)
            logger.info("Profile updated successfully for user: %s", instance.email)
            return Response(encrypt(serializer.data), status=status.HTTP_200_OK)
        else:
            logger.error(
                "Failed to update profile for user: %s. Errors: %s",
                instance.email,
                serializer.errors,
            )
            return Response(
                encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST
            )


class CreateAdView(generics.CreateAPIView):
    serializer_class = CreateAdSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsBrandAd)

    def create(self, request, *args, **kwargs):
        try:
            decrypted_data = decrypt(request.data)
            serializer = self.get_serializer(data=decrypted_data)
            serializer.is_valid(raise_exception=True)

            serializer.validated_data["user"] = request.user
            create_ad = serializer.save()

            ActivityModel.objects.create(
                user=request.user,
                title="Brand Survey",
                description=f"{request.user} created an Ad successfully.",
            )

            return Response(
                encrypt(CreateAdSerializers(create_ad).data),
                status=status.HTTP_201_CREATED,
            )

        except Exception as err:
            logger.error(f"Brand advert creation failed: {str(err)}", exc_info=True)
            return Response(
                encrypt(
                    {"error": f"An error occurred while creating the ad: {str(err)}"}
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )


class SingleAdDetailView(generics.RetrieveAPIView):
    """SingleAdDetailView is the GET request handler to get the details of a single
    brandAd of any authenticated Brand advertiser.
    """

    queryset = CreateAd.objects.all()
    serializer_class = AdSerializers
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    lookup_field = "ad_id"

    def get(self, request, *args, **kwargs):
        ad_id = kwargs.get("ad_id")
        logger.info("Received request to retrieve ad details with ID: %s", ad_id)

        try:
            ad = self.get_queryset().get(id=ad_id)
        except CreateAd.DoesNotExist:
            logger.error("Ad with ID %s not found.", ad_id)
            return Response(
                data=encrypt({"status": "fail", "message": "Ad not found."}),
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = self.get_serializer(ad)
        logger.info("Ad serialized successfully: %s", ad_id)

        response = {
            "status": "success",
            "message": "Ad retrieved successfully!",
            "data": serializer.data,
        }
        return Response(data=encrypt(response), status=status.HTTP_200_OK)


class PromoteBrand(generics.CreateAPIView):
    serializer_class = AdBudgetSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsBrandAd)

    def create(self, request, *args, **kwargs):
        authenticated_user = request.user
        decrypted_data = decrypt(request.data)
        payload = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_data.items()
        }
        serializer = self.get_serializer(data=payload)

        if not serializer.is_valid(raise_exception=True):
            logger.warning(
                f"Serializer validation failed for user {authenticated_user.first_name} {authenticated_user.last_name}: {serializer.errors}"
            )
            return Response(
                data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST
            )

        payment_option = payload.get("payment_option")
        pin = payload.get("pin")
        ad_id = kwargs.get("ad_id")
        # biometrics = decrypted_data.get("use_biometrics")

        advert_id = CreateAd.objects.filter(id=ad_id).first()

        if not advert_id.is_approved:
            logger.warning(f"Ad with ID {ad_id} is not approved for promotion.")
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "Ad is not approved and thus cannot be promoted.",
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        match payment_option:
            case "WALLET":
                pass

                try:
                    pin = payload.get("pin")

                    # Verify PIN
                    is_verified = Pin.verify_pin(user=authenticated_user, pin=pin)
                    if not is_verified:
                        logger.warning(
                            "PIN verification failed for user %s",
                            authenticated_user.email,
                        )
                        return Response(
                            encrypt({"error": "Invalid PIN."}),
                            status=status.HTTP_403_FORBIDDEN,
                        )

                    # Debit Account
                    price = payload.get("price")
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

                        logger.info(
                            "Brand promotion payment successful for user %s",
                            authenticated_user.email,
                        )

                        response_data = {
                            "status": "Success!",
                            "message": "Brand advert promoted successfully.",
                        }
                        encrypted_success = encrypt(response_data)
                        return Response(
                            data=encrypted_success, status=status.HTTP_200_OK
                        )

                    else:
                        # Handle debit failure
                        logger.error(
                            "Debit failed with response: %s", debit_response.json()
                        )
                        response_data = {
                            "status": "Failure",
                            "details": debit_response.json(),
                        }
                        encrypted_response = encrypt(response_data)
                        return Response(
                            data=encrypted_response, status=status.HTTP_400_BAD_REQUEST
                        )

                # except AccountCreation.DoesNotExist:
                #     logger.error(
                #         "Account details not found for user %s", authenticated_user.email
                #     )
                #     resp = {"error": "Account details not found."}
                #     encrypted_response = encrypt(resp)
                #     return Response(
                #         data=encrypted_response,
                #         status=status.HTTP_404_NOT_FOUND,
                #     )

                except Exception as err:
                    logger.exception(
                        "An error occurred during brand promotion for user %s: %s",
                        authenticated_user.email,
                        err,
                    )
                    resp = {"error": "An error occurred during promotion."}
                    encrypted_response = encrypt(resp)
                    return Response(
                        data=encrypted_response,
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            case "CARD":
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

                # Update and save promotion status.
                promoted_ad = AdBudget.objects.update(user=authenticated_user)
                promoted_ad.has_made_request = True
                promoted_ad.save()

                logger.info(
                    "Brand promotion payment successful for user %s",
                    authenticated_user.email,
                )

                response_data = {
                    "status": "Success!",
                    "message": "Brand advert promoted successfully.",
                }
                encrypted_success = encrypt(response_data)
                return Response(data=encrypted_success, status=status.HTTP_200_OK)
