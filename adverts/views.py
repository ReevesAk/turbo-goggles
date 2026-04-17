import logging
from decimal import Decimal

from django.core.cache import cache
from django.db import transaction

# Third party imports
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.pagination import PageNumberPagination

# In project imports.
from .serializers import (
    BrandAdProfileSerializers,
    UpdateBrandAdProfileSerializers,
    CreateAdSerializers,
    AdSerializers,
)

# from mail import send_email
from accounts.models import User, UserNotification, AccountType
from permissions import IsBrandAd, IsBrandAdAdmin, IsSuperAdmin
from .models import CreateAd
from banking.helpers import verify_wallet_auth
from banking.controllers import Wallet
from banking.models import WalletModel
from roles.models import ActivityModel
from security import encrypt, decrypt

logger = logging.getLogger(__name__)


class PaginationStyle(PageNumberPagination):
    page_size = 20


class CreateAdAndOnboardBrandView(generics.CreateAPIView):
    serializer_class = CreateAdSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

    def create(self, request, *args, **kwargs):
        try:
            decrypted_data = decrypt(request.data)
            serializer = self.get_serializer(data=decrypted_data)
            serializer.is_valid(raise_exception=True)

            idempotency_key = request.headers.get(
                "Idempotency-Key"
            ) or request.data.get("idempotency_key")

            # Ensure user is a BrandAd (onboarded)
            user = request.user
            if not AccountType.objects.filter(user=user, user_type="BrandAd").exists():
                AccountType.objects.create(user=user, user_type="BrandAd")
                user.active_role = "BrandAd"
                user.save()

            pin = decrypted_data.get("pin")
            amount = decrypted_data.get("amount")
            payment_option = decrypted_data.get("payment_option")
            biometrics = decrypted_data.get("use_biometrics")

            # Generate transaction reference.
            tx_reference = (
                idempotency_key
                if idempotency_key
                else f"brand_promotion_{user.id}_{CreateAd.objects.count() + 1}"
            )

            # Authentication
            is_verified, error_response = verify_wallet_auth(
                user=user,
                payment_option=payment_option,
                pin=pin,
                use_biometrics=biometrics,
            )

            if not is_verified:
                return error_response

            match payment_option:
                case "WALLET":
                    wallet_debit_amount = int(Decimal(str(amount)))

                    # Debit user's account
                    if wallet_debit_amount > 0:
                        try:
                            with transaction.atomic():

                                account = WalletModel.objects.select_for_update().get(
                                    user=user
                                )

                                merchant_fee = "0.00"
                                debit_response = Wallet.Debit(
                                    debitAccount=account.account_number,
                                    amount=wallet_debit_amount,
                                    reason="Debit for brwand promotion.",
                                    merchantFeeAmount=merchant_fee,
                                )

                                if debit_response.status_code == 200:
                                    create_ad = serializer.save()

                                    TxModel.objects.create(
                                        user=user,
                                        tx_reference=tx_reference,
                                        tx_type="Brand Promostion",
                                        amount=wallet_debit_amount,
                                        description="Brand promotion payment",
                                        status="SUCCESS",
                                    )

                                    UserNotification.objects.create(
                                        user=user,
                                        title="Brand Promotion",
                                        message=f"Your payment of {wallet_debit_amount} for brand promotion was successful.",
                                    )

                                    ActivityModel.objects.create(
                                        user=user,
                                        title="Brand Promotion",
                                        description=f"{user} promoted their brand successfully.",
                                    )

                                    logger.info(
                                        "Brand promotion payment successful for user %s",
                                        user.email,
                                    )

                                    response_data = {
                                        "status": "Success!",
                                        "message": "Brand advert promoted successfully.",
                                    }
                                    encrypted_success = encrypt(response_data)
                                    return Response(
                                        data=encrypted_success,
                                        status=status.HTTP_200_OK,
                                    )
                                else:
                                    return Response(
                                        data=encrypt(debit_response.json()),
                                        status=debit_response.status_code,
                                    )
                        except Exception as e:
                            logger.exception(
                                f"Transaction error during wallet bill payment: {e}"
                            )
                            return Response(
                                data=encrypt(
                                    {"status": "fail", "message": "Transaction failed"}
                                ),
                                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            )

                case "CARD":
                    create_ad = serializer.save()
                    TxModel.objects.create(
                        user=user,
                        tx_reference=tx_reference,
                        tx_type="Brand Promotion",
                        amount=wallet_debit_amount,
                        description="Brand promotion payment",
                        status="SUCCESS",
                    )
                    UserNotification.objects.create(
                        user=user,
                        title="Brand Promotion",
                        message=f"Your payment of {wallet_debit_amount} for brand promotion was successful.",
                    )

                    ActivityModel.objects.create(
                        user=user,
                        title="Brand Promotion",
                        description=f"{user} promoted their brand successfully.",
                    )

                    logger.info(
                        "Brand promotion payment successful for user %s",
                        user.email,
                    )

                    response_data = {
                        "status": "Success!",
                        "message": "Brand advert promoted successfully.",
                    }
                    encrypted_success = encrypt(response_data)
                    return Response(data=encrypted_success, status=status.HTTP_200_OK)

                case _:
                    return Response(
                        data=encrypt(
                            {"status": "fail", "message": "Invalid payment option"}
                        ),
                        status=status.HTTP_400_BAD_REQUEST,
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
    permission_classes = [IsAuthenticated & (IsBrandAd | IsBrandAdAdmin | IsSuperAdmin)]
    pagination_class = PaginationStyle

    def get_queryset(self):
        user = self.request.user
        logger.info("Retrieving all ads created by BrandAd users.")
        return (
            CreateAd.objects.filter(user=user)
            .select_related("user")
            .prefetch_related("brand_location")
            .order_by("-created_at")
        )

    def list(self, request, *args, **kwargs):
        logger.info("ListAllBrandAds view created by user: %s", request.user.email)

        user_id = request.user.id
        cache_key = f"user_ads:{user_id}"

        # Try Redis cache first
        cached_ads = cache.get(cache_key)
        if cached_ads:
            logger.info("Returning cached ads for user %s", request.user.email)
            encrypted_response = encrypt(cached_ads)
            return Response(data=encrypted_response, status=status.HTTP_200_OK)

        # If not in cache, fetch from database
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

        # Save to cache (short TTL)
        cache.set(cache_key, response, timeout=120)  # 2 minutes

        encrypted_response = encrypt(response)
        return Response(data=encrypted_response, status=status.HTTP_200_OK)


class GetBrandAdDetails(generics.RetrieveAPIView):
    """Returns the profile details of a BrandAd user."""

    serializer_class = BrandAdProfileSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated & (IsBrandAd | IsBrandAdAdmin)]

    def retrieve(self, request, *args, **kwargs):
        email = request.query_params.get("email")

        if not email:
            return Response(
                {"status": "fail", "error": "Email is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response(
                {"status": "fail", "error": "User not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check if user has BrandAd role
        has_brand_ad_role = AccountType.objects.filter(
            user=user, user_type="BrandAd"
        ).exists()

        if not has_brand_ad_role:
            return Response(
                {"status": "fail", "error": "User is not a BrandAd"},
                status=status.HTTP_403_FORBIDDEN,
            )

        logger.info("GetBrandAdDetails accessed for brand user: %s", user.email)

        cache_key = f"Ad_Details:{user.id}"

        cached_ads = cache.get(cache_key)
        if cached_ads:
            logger.info("Returning cached ad detail for %s", user.email)
            encrypted_response = encrypt(cached_ads)
            return Response(encrypted_response, status=status.HTTP_200_OK)

        serializer = self.get_serializer(user)

        response = {
            "status": "success",
            "message": "Ad detail retrieved successfully!",
            "data": serializer.data,
        }

        cache.set(cache_key, response, timeout=300)

        encrypted_response = encrypt(response)
        return Response(encrypted_response, status=status.HTTP_200_OK)


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

            # clear the user's ads cache after update
            user_id = request.user.id
            cache_key = f"Ad_Details:{user_id}"
            cache.delete(cache_key)
            logger.info(
                "Cleared cache for user %s after profile update.", instance.email
            )
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

        cache_key = f"singleAd_Details:{ad_id}"
        cached_ad = cache.get(cache_key)
        if cached_ad:
            logger.info("Returning cached ad detail for user %s", request.user.email)
            encrypted_response = encrypt(cached_ad)
            return Response(data=encrypted_response, status=status.HTTP_200_OK)

        serializer = self.get_serializer(ad)
        logger.info("Ad serialized successfully: %s", ad_id)

        response = {
            "status": "success",
            "message": "Ad retrieved successfully!",
            "data": serializer.data,
        }

        # Save to cache (short TTL)
        cache.set(cache_key, response, timeout=300)  # 5 minutes

        return Response(data=encrypt(response), status=status.HTTP_200_OK)


# class PromoteBrand(generics.CreateAPIView):
#     serializer_class = AdBudgetSerializer
#     authentication_classes = [JWTAuthentication]
#     permission_classes = (IsAuthenticated, IsBrandAd)

#     def create(self, request, *args, **kwargs):
#         authenticated_user = request.user
#         decrypted_data = decrypt(request.data)
#         payload = {
#             key: value.strip() if isinstance(value, str) else value
#             for key, value in decrypted_data.items()
#         }
#         serializer = self.get_serializer(data=payload)

#         if not serializer.is_valid(raise_exception=True):
#             logger.warning(
#                 f"Serializer validation failed for user {authenticated_user.first_name} {authenticated_user.last_name}: {serializer.errors}"
#             )
#             return Response(
#                 data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST
#             )

#         payment_option = payload.get("payment_option")
#         pin = payload.get("pin")
#         ad_id = kwargs.get("ad_id")
#         biometrics = decrypted_data.get("use_biometrics")

#         advert_id = CreateAd.objects.filter(id=ad_id).first()

#         if not advert_id.is_approved:
#             logger.warning(f"Ad with ID {ad_id} is not approved for promotion.")
#             return Response(
#                 data=encrypt(
#                     {
#                         "status": "fail",
#                         "message": "Ad is not approved and thus cannot be promoted.",
#                     }
#                 ),
#                 status=status.HTTP_400_BAD_REQUEST,
#             )

#         match payment_option:
#             case "WALLET":
#                 verified, error_response = verify_wallet_auth(
#                     user=authenticated_user,
#                     payment_option=payment_option,
#                     pin=pin,
#                     use_biometrics=biometrics,
#                 )

#                 if not verified:
#                     return error_response

#                 # Debit Account
#                 price = payload.get("price")
#                 user_details = WalletModel.objects.get(user=authenticated_user)
#                 debit_response = Wallet.Debit(
#                     debitAccount=user_details.account_number,
#                     amount=price,
#                     description="Debit for brand promotion",
#                     transactionReference="",
#                 )

#                 try:
#                     # Check debit response
#                     if debit_response == 200:
#                         serializer.save()
#                         UserNotification.objects.create(
#                             user=authenticated_user,
#                             title="Brand Promotion",
#                             message=f"Your payment of {price} for brand promotion was successful.",
#                         )

#                         ActivityModel.objects.create(
#                             user=authenticated_user,
#                             title="Brand Promotion",
#                             description=f"{authenticated_user.whoareyou} promoted their brand successfully.",
#                         )

#                         logger.info(
#                             "Brand promotion payment successful for user %s",
#                             authenticated_user.email,
#                         )

#                         response_data = {
#                             "status": "Success!",
#                             "message": "Brand advert promoted successfully.",
#                         }
#                         encrypted_success = encrypt(response_data)
#                         return Response(
#                             data=encrypted_success, status=status.HTTP_200_OK
#                         )

#                     else:
#                         # Handle debit failure
#                         logger.error(
#                             "Debit failed with response: %s", debit_response.json()
#                         )
#                         response_data = {
#                             "status": "Failure",
#                             "details": debit_response.json(),
#                         }
#                         encrypted_response = encrypt(response_data)
#                         return Response(
#                             data=encrypted_response, status=status.HTTP_400_BAD_REQUEST
#                         )

#                 except Exception as err:
#                     logger.exception(
#                         "An error occurred during brand promotion for user %s: %s",
#                         authenticated_user.email,
#                         err,
#                     )
#                     resp = {"error": "An error occurred during promotion."}
#                     encrypted_response = encrypt(resp)
#                     return Response(
#                         data=encrypted_response,
#                         status=status.HTTP_400_BAD_REQUEST,
#                     )

#             case "CARD":
#                 UserNotification.objects.create(
#                     user=authenticated_user,
#                     title="Brand Promotion",
#                     message=f"Your payment of {price} for brand promotion was successful.",
#                 )

#                 ActivityModel.objects.create(
#                     user=authenticated_user,
#                     title="Brand Promotion",
#                     description=f"{authenticated_user.whoareyou} promoted their brand successfully.",
#                 )

#                 # Update and save promotion status.
#                 promoted_ad = AdBudget.objects.update(user=authenticated_user)
#                 promoted_ad.has_made_request = True
#                 promoted_ad.save()

#                 logger.info(
#                     "Brand promotion payment successful for user %s",
#                     authenticated_user.email,
#                 )

#                 response_data = {
#                     "status": "Success!",
#                     "message": "Brand advert promoted successfully.",
#                 }
#                 encrypted_success = encrypt(response_data)
#                 return Response(data=encrypted_success, status=status.HTTP_200_OK)
