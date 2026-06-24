import logging
from decimal import Decimal

from django.core.cache import cache
from django.db import transaction
from django.db.models import Count, F, Q, Sum
from django.utils import timezone

# Third party imports
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.pagination import PageNumberPagination

import rest_framework.serializers as s

from drf_spectacular.utils import (
    extend_schema,
    OpenApiParameter,
    OpenApiExample,
    inline_serializer,
)
from drf_spectacular.types import OpenApiTypes

# In project imports.
from .serializers import (
    BrandAdProfileSerializers,
    UpdateBrandAdProfileSerializers,
    CreateAdSerializers,
    AdSerializers,
)

# from mail import send_email
from accounts.models import User, UserNotification, AccountType, TxModel
from permissions import IsBrandAd, IsBrandAdAdmin, IsSuperAdmin
from .models import BrandAdCreditWallet, CreateAd
from .credit import apply_credit, reconcile_credit
from banking.helpers import verify_wallet_auth
from banking.controllers import Wallet
from banking.models import WalletModel
from roles.models import ActivityModel
from security import encrypt, decrypt
from commons import first_validation_error

logger = logging.getLogger(__name__)


class PaginationStyle(PageNumberPagination):
    page_size = 20


_CREATE_AD_DESCRIPTION = """
Creates a new ad campaign and auto-onboards the user as a **BrandAd** if they don't already have that role.

**Idempotency:** Send `Idempotency-Key: <uuid>` header to safely retry on network failure without double-charging.

---

### `task_details` shape per `task_type`

| `task_type` | Required fields in `task_details` |
|---|---|
| `watch_video` | `video_url`, `platform` (`YouTube`\\|`TikTok`\\|`Instagram`\\|`X`), `min_watch_duration` (`15s`\\|`30s`\\|`60s`\\|`full`) |
| `social_engage` | `platform`, `post_url`, `required_actions` (list of `like`\\|`comment`\\|`share`\\|`follow`); optional: `timing` (`15s`\\|`30s`\\|`60s`) |
| `website_visit` | `landing_url`, `min_time_on_page` (`30`\\|`60`\\|`120`\\|`180` seconds) |
| `store_visit` | `store_name`, `store_address` |
| `survey` | `survey_title`, `questions` (list, min 1) |
| `app_download` | `app_name`, `play_store_url` |

---

### Targeting type & pricing multiplier

| `targeting_type` | Label | Multiplier |
|---|---|---|
| `broad` *(default)* | All of Nigeria | ×1.00 |
| `city` | City-Specific | ×1.15 |
| `niche` | Niche Behaviour | ×1.25 |
| `influencer` | Influencer Tier (10k+ followers) | ×1.50 |

**Cost formula:** `slot_cap × cost_per_engagement × targeting_multiplier`
"""

_SUCCESS_RESP = inline_serializer(
    name="AdSuccessResponse",
    fields={"status": s.CharField(), "message": s.CharField()},
)

_ERROR_RESP = inline_serializer(
    name="AdErrorResponse",
    fields={"status": s.CharField(), "message": s.CharField()},
)


@extend_schema(
    summary="Create brand ad and onboard as BrandAd user",
    tags=["Brand Ads"],
    description=_CREATE_AD_DESCRIPTION,
    request=CreateAdSerializers,
    responses={
        200: _SUCCESS_RESP,
        400: _ERROR_RESP,
        500: _ERROR_RESP,
    },
    examples=[
        OpenApiExample(
            "Watch Video — Wallet payment",
            summary="Watch Video task paid via wallet",
            request_only=True,
            value={
                "payment_option": "WALLET",
                "pin": "123456",
                "business_or_brand_name": "Acme Co",
                "type_of_business": "Online",
                "industry": "Technology",
                "brand_objective": "Brand Awareness",
                "campaign_name": "Summer 2025",
                "gender": "All",
                "demography": "26 - 35",
                "campaign_duration": "7",
                "amount": "15000",
                "targeting_type": "broad",
                "location_type": "states",
                "state": ["Lagos", "Abuja"],
                "city": ["Ikeja", "Wuse"],
                "task_type": "watch_video",
                "task_name": "Watch our promo",
                "task_description": "Watch 30 secs of our latest ad.",
                "task_details": {
                    "video_url": "https://youtube.com/watch?v=abc123",
                    "platform": "YouTube",
                    "min_watch_duration": "30s",
                },
                "slot_cap": 200,
                "auto_boost": False,
            },
        ),
        OpenApiExample(
            "Social Engage — Wallet payment",
            summary="Social engagement task paid via wallet",
            request_only=True,
            value={
                "payment_option": "WALLET",
                "pin": "123456",
                "business_or_brand_name": "Acme Co",
                "campaign_name": "Follow & Like Campaign",
                "campaign_duration": "3",
                "amount": "10000",
                "targeting_type": "city",
                "location_type": "cities",
                "state": ["Lagos"],
                "city": ["Ikeja"],
                "task_type": "social_engage",
                "task_name": "Follow us on Instagram",
                "task_details": {
                    "platform": "Instagram",
                    "post_url": "https://instagram.com/p/xyz123",
                    "required_actions": ["like", "follow"],
                    "timing": "30s",
                },
                "slot_cap": 100,
            },
        ),
        OpenApiExample(
            "App Download — Wallet payment",
            summary="App download task paid via wallet",
            request_only=True,
            value={
                "payment_option": "WALLET",
                "pin": "123456",
                "business_or_brand_name": "Acme Co",
                "campaign_name": "Install our App",
                "campaign_duration": "14",
                "amount": "60000",
                "targeting_type": "niche",
                "location_type": "nationwide",
                "task_type": "app_download",
                "task_name": "Download Acme App",
                "task_details": {
                    "app_name": "Acme",
                    "play_store_url": "https://play.google.com/store/apps/details?id=com.acme",
                },
                "slot_cap": 150,
            },
        ),
        OpenApiExample(
            "Survey — Card payment",
            summary="Survey task paid via card",
            request_only=True,
            value={
                "payment_option": "CARD",
                "business_or_brand_name": "Acme Co",
                "campaign_name": "Customer Feedback Q3",
                "campaign_duration": "7",
                "amount": "40000",
                "targeting_type": "broad",
                "location_type": "nationwide",
                "task_type": "survey",
                "task_name": "Quick 2-question survey",
                "task_details": {
                    "survey_title": "Customer Feedback Q3 2025",
                    "questions": [
                        "How did you hear about us?",
                        "Would you recommend us to a friend?",
                    ],
                },
                "slot_cap": 100,
            },
        ),
        OpenApiExample(
            "Website Visit",
            summary="Website visit task",
            request_only=True,
            value={
                "payment_option": "WALLET",
                "pin": "123456",
                "business_or_brand_name": "Acme Co",
                "campaign_name": "Visit our promo page",
                "campaign_duration": "7",
                "amount": "10000",
                "targeting_type": "broad",
                "task_type": "website_visit",
                "task_name": "Visit our promo page",
                "task_details": {
                    "landing_url": "https://acme.com/summer-promo",
                    "min_time_on_page": 60,
                },
                "slot_cap": 200,
            },
        ),
        OpenApiExample(
            "Store Visit",
            summary="Physical store visit task",
            request_only=True,
            value={
                "payment_option": "WALLET",
                "pin": "123456",
                "business_or_brand_name": "Acme Lagos",
                "campaign_name": "Visit our Ikeja store",
                "campaign_duration": "7",
                "amount": "300000",
                "targeting_type": "city",
                "location_type": "cities",
                "state": ["Lagos"],
                "city": ["Ikeja"],
                "task_type": "store_visit",
                "task_name": "Visit Acme Ikeja",
                "task_details": {
                    "store_name": "Acme Ikeja Branch",
                    "store_address": "12 Allen Avenue, Ikeja, Lagos",
                },
                "slot_cap": 50,
            },
        ),
        OpenApiExample(
            "Success",
            response_only=True,
            status_codes=["200"],
            value={
                "status": "Success!",
                "message": "Brand advert promoted successfully.",
            },
        ),
        OpenApiExample(
            "Insufficient Balance",
            response_only=True,
            status_codes=["400"],
            value={"status": "fail", "message": "Insufficient balance."},
        ),
    ],
)
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

            full_charge = Decimal(str(amount))

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
                    try:
                        # 1. Sweep expired-ad credit before checking balance.
                        with transaction.atomic():
                            reconcile_credit(user)

                        credit_wallet, _ = BrandAdCreditWallet.objects.get_or_create(
                            user=user
                        )
                        credit_available = credit_wallet.balance
                        net_charge = max(full_charge - credit_available, Decimal("0"))

                        # 2. Check live wallet balance against the net (post-credit) amount.
                        account = WalletModel.objects.get(user=user)
                        enquiry = Wallet.getWalletDetails(account.account_number)
                        if enquiry and hasattr(enquiry, "json"):
                            enquiry_data = enquiry.json()
                            live_balance = Decimal(
                                str(
                                    enquiry_data.get("data", {}).get(
                                        "availableBalance", 0
                                    )
                                )
                            )
                        else:
                            live_balance = account.balance

                        if live_balance < net_charge:
                            return Response(
                                data=encrypt(
                                    {
                                        "status": "fail",
                                        "message": "Insufficient balance.",
                                    }
                                ),
                                status=status.HTTP_400_BAD_REQUEST,
                            )

                        # 3. Debit only the net amount (full charge minus credit).
                        if net_charge > 0:
                            debit_response = Wallet.Debit(
                                debitAccount=account.account_number,
                                amount=int(net_charge),
                                reason="Debit for brand promotion.",
                                merchantFeeAmount="0.00",
                            )
                            if (
                                debit_response is None
                                or debit_response.status_code != 200
                            ):
                                return Response(
                                    data=encrypt(
                                        {
                                            "status": "fail",
                                            "message": "Debit failed. Please try again.",
                                        }
                                    ),
                                    status=status.HTTP_400_BAD_REQUEST,
                                )

                        # 4. Debit succeeded — persist the ad and consume credit atomically.
                        with transaction.atomic():
                            new_ad = serializer.save()
                            credit_applied, _ = apply_credit(user, new_ad, full_charge)

                            credit_msg = (
                                f" (₦{credit_applied} credit applied)"
                                if credit_applied > 0
                                else ""
                            )

                            TxModel.objects.create(
                                user=user,
                                tx_reference=tx_reference,
                                tx_type="Brand Promotion",
                                amount=int(net_charge),
                                description=f"Brand promotion payment{credit_msg}",
                                status="SUCCESS",
                            )

                            UserNotification.objects.create(
                                user=user,
                                title="Brand Promotion",
                                message=f"Your payment of ₦{int(net_charge)} for brand promotion was successful.{credit_msg}",
                            )

                            ActivityModel.objects.create(
                                user=user,
                                title="Brand Promotion",
                                description=f"{user} promoted their brand successfully.{credit_msg}",
                            )

                        logger.info(
                            "Brand promotion payment successful for user %s "
                            "(charged: %s, credit applied: %s)",
                            user.email,
                            int(net_charge),
                            credit_applied,
                        )

                        return Response(
                            data=encrypt(
                                {
                                    "status": "Success!",
                                    "message": "Brand advert promoted successfully.",
                                }
                            ),
                            status=status.HTTP_200_OK,
                        )

                    except Exception as e:
                        logger.exception(
                            f"Transaction error during wallet payment: {e}"
                        )
                        return Response(
                            data=encrypt(
                                {"status": "fail", "message": "Transaction failed"}
                            ),
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        )

                case "CARD":
                    with transaction.atomic():
                        reconcile_credit(user)
                        new_ad = serializer.save()
                        credit_applied, effective_charge = apply_credit(
                            user, new_ad, full_charge
                        )
                        effective_debit = int(effective_charge)
                    credit_msg = (
                        f" (₦{credit_applied} credit applied)"
                        if credit_applied > 0
                        else ""
                    )
                    TxModel.objects.create(
                        user=user,
                        tx_reference=tx_reference,
                        tx_type="Brand Promotion",
                        amount=effective_debit,
                        description=f"Brand promotion payment{credit_msg}",
                        status="SUCCESS",
                    )
                    UserNotification.objects.create(
                        user=user,
                        title="Brand Promotion",
                        message=f"Your payment of ₦{effective_debit} for brand promotion was successful.{credit_msg}",
                    )
                    ActivityModel.objects.create(
                        user=user,
                        title="Brand Promotion",
                        description=f"{user} promoted their brand successfully.{credit_msg}",
                    )
                    logger.info(
                        "Brand promotion payment successful for user %s "
                        "(charged: %s, credit applied: %s)",
                        user.email,
                        effective_debit,
                        credit_applied,
                    )
                    return Response(
                        data=encrypt(
                            {
                                "status": "Success!",
                                "message": "Brand advert promoted successfully.",
                            }
                        ),
                        status=status.HTTP_200_OK,
                    )

                case _:
                    return Response(
                        data=encrypt(
                            {"status": "fail", "message": "Invalid payment option"}
                        ),
                        status=status.HTTP_400_BAD_REQUEST,
                    )

        except DRFValidationError as exc:
            message = first_validation_error(exc.detail)
            logger.warning("Brand advert validation failed: %s", exc.detail)
            return Response(
                data=encrypt({"status": "error", "message": message}),
                status=status.HTTP_400_BAD_REQUEST,
            )

        except Exception as err:
            logger.error(f"Brand advert creation failed: {str(err)}", exc_info=True)
            return Response(
                encrypt(
                    {
                        "status": "error",
                        "message": "Ad creation failed. Please try again.",
                    }
                ),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


@extend_schema(
    summary="List all BrandAd users",
    tags=["Brand Ads"],
    description="Admin-only. Returns all users who have the **BrandAd** role. Paginated — 20 per page.",
    parameters=[
        OpenApiParameter(
            "page",
            OpenApiTypes.INT,
            OpenApiParameter.QUERY,
            description="Page number (default: 1)",
            required=False,
        ),
    ],
    responses={200: BrandAdProfileSerializers(many=True)},
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


@extend_schema(
    summary="List all ads created by the current BrandAd user",
    tags=["Brand Ads"],
    description=(
        "Returns all ad campaigns created by the authenticated user. "
        "Results are cached for **2 minutes**. "
        "`remaining_time` returns `'Expired'` once the campaign duration elapses."
    ),
    parameters=[
        OpenApiParameter(
            "page",
            OpenApiTypes.INT,
            OpenApiParameter.QUERY,
            description="Page number (default: 1)",
            required=False,
        ),
    ],
    responses={200: AdSerializers(many=True)},
)
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
            if page is not None
            else self.serializer_class(queryset, many=True)
        )
        response = {
            "status": "success",
            "message": "All created ads retrieved successfully!",
            "data": list(serializer.data),
        }

        # Save to cache (short TTL)
        cache.set(cache_key, response, timeout=120)  # 2 minutes

        encrypted_response = encrypt(response)
        return Response(data=encrypted_response, status=status.HTTP_200_OK)


@extend_schema(
    summary="Get BrandAd profile details by email",
    tags=["Brand Ads"],
    description="Returns the BrandAd profile for any user by email. Cached for **5 minutes**.",
    parameters=[
        OpenApiParameter(
            "email",
            OpenApiTypes.EMAIL,
            OpenApiParameter.QUERY,
            description="Email address of the BrandAd user to look up.",
            required=True,
        ),
    ],
    responses={
        200: BrandAdProfileSerializers,
        400: inline_serializer(
            name="ProfileMissingEmailError",
            fields={"status": s.CharField(), "error": s.CharField()},
        ),
        403: inline_serializer(
            name="ProfileNotBrandAdError",
            fields={"status": s.CharField(), "error": s.CharField()},
        ),
        404: inline_serializer(
            name="ProfileNotFoundError",
            fields={"status": s.CharField(), "error": s.CharField()},
        ),
    },
    examples=[
        OpenApiExample(
            "Not a BrandAd",
            response_only=True,
            status_codes=["403"],
            value={"status": "fail", "error": "User is not a BrandAd"},
        ),
        OpenApiExample(
            "User not found",
            response_only=True,
            status_codes=["404"],
            value={"status": "fail", "error": "User not found"},
        ),
    ],
)
class GetBrandAdDetails(generics.RetrieveAPIView):
    """Returns the profile details of a BrandAd user."""

    serializer_class = BrandAdProfileSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated & (IsBrandAd | IsBrandAdAdmin | IsSuperAdmin)]

    def retrieve(self, request, *args, **kwargs):
        email = kwargs.get("email") or request.query_params.get("email")

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

        now = timezone.now()
        user_ads = CreateAd.objects.filter(user=user)

        total_ads_placed = user_ads.count()

        active_qs = user_ads.filter(is_active=True, expiry_date__gt=now)
        active_ads = active_qs.count()

        completed_qs = user_ads.filter(
            Q(is_active=False)
            | Q(expiry_date__lte=now)
            | Q(slots_filled__gte=F("slot_cap"))
        ).distinct()
        completed_ads = completed_qs.count()
        completed_reach = (
            completed_qs.aggregate(total=Sum("slots_filled"))["total"] or 0
        )
        completed_cap = completed_qs.aggregate(total=Sum("slot_cap"))["total"] or 0
        conversion_pct = (
            round((completed_reach / completed_cap) * 100, 1) if completed_cap else 0
        )

        ongoing_reach = active_qs.aggregate(total=Sum("slots_filled"))["total"] or 0

        response = {
            "status": "success",
            "message": "Ad detail retrieved successfully!",
            "data": {
                **serializer.data,
                "ads_dashboard": {
                    "total_ads_placed": total_ads_placed,
                    "active_ads": active_ads,
                    "completed_ads": {
                        "count": completed_ads,
                        "reach": completed_reach,
                        "conversion_pct": conversion_pct,
                    },
                    "ongoing_ads": {
                        "count": active_ads,
                        "reach": ongoing_reach,
                    },
                },
            },
        }

        cache.set(cache_key, response, timeout=300)

        encrypted_response = encrypt(response)
        return Response(encrypted_response, status=status.HTTP_200_OK)


@extend_schema(
    summary="Update BrandAd profile",
    tags=["Brand Ads"],
    description=(
        "Update the authenticated user's BrandAd profile. "
        "Use **PATCH** to update individual fields without sending the full object."
    ),
    request=UpdateBrandAdProfileSerializers,
    responses={
        200: UpdateBrandAdProfileSerializers,
        400: inline_serializer(
            name="BrandAdUpdateProfileError", fields={"detail": s.CharField()}
        ),
    },
)
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


@extend_schema(
    summary="Get details of a single brand ad",
    tags=["Brand Ads"],
    description="Fetch one ad campaign by its numeric ID. Cached for **5 minutes**.",
    responses={
        200: AdSerializers,
        404: inline_serializer(
            name="SingleAdNotFound",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
    examples=[
        OpenApiExample(
            "Not found",
            response_only=True,
            status_codes=["404"],
            value={"status": "fail", "message": "Ad not found."},
        ),
    ],
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


_COST_PREVIEW_RESPONSE = inline_serializer(
    name="CostPreviewResponse",
    fields={
        "status": s.CharField(),
        "data": inline_serializer(
            name="CostPreviewData",
            fields={
                "ledger_balance": s.CharField(
                    help_text="Available credit from unused slots on past expired ads"
                ),
                "credit_to_apply": s.CharField(
                    help_text="Credit the user can apply against their next ad"
                ),
            },
        ),
    },
)


@extend_schema(
    summary="Get available ad credit",
    tags=["Brand Ads"],
    description=(
        "Call this **before** creating an ad. Returns the brand's available ledger credit "
        "(from unused slots on expired ads). Frontend subtracts this from the ad total to "
        "get the actual charge."
    ),
    responses={200: _COST_PREVIEW_RESPONSE},
    examples=[
        OpenApiExample(
            "Credit available",
            response_only=True,
            status_codes=["200"],
            value={
                "status": "success",
                "data": {"ledger_balance": "3000", "credit_to_apply": "3000"},
            },
        ),
        OpenApiExample(
            "No credit available",
            response_only=True,
            status_codes=["200"],
            value={
                "status": "success",
                "data": {"ledger_balance": "0", "credit_to_apply": "0"},
            },
        ),
    ],
)
class AdCostPreviewView(generics.GenericAPIView):
    """
    GET /v1/brands/ads/cost-preview/

    Returns the brand's available ledger credit after reconciling expired ads.
    Frontend uses credit_to_apply to calculate the actual charge on their side.
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        with transaction.atomic():
            reconcile_credit(user)

        wallet, _ = BrandAdCreditWallet.objects.get_or_create(user=user)
        ledger_balance = wallet.balance

        return Response(
            data=encrypt(
                {
                    "status": "success",
                    "data": {
                        "ledger_balance": str(ledger_balance),
                        "credit_to_apply": str(ledger_balance),
                    },
                }
            ),
            status=status.HTTP_200_OK,
        )


@extend_schema(
    summary="Brand ad analytics (ongoing & finished)",
    tags=["Brand Ads"],
    description=(
        "Returns full analytics for a single brand ad owned by the authenticated user. "
        "The `is_finished` flag drives which screen the mobile renders. "
        "Ongoing ads include `location_perimeter`; finished ads include "
        "`performance_breakdown` and `performance_demographic`."
    ),
    responses={
        200: inline_serializer(
            "BrandAdAnalyticsResponse",
            fields={
                "status": s.CharField(),
                "data": s.DictField(),
            },
        ),
        403: inline_serializer(
            "BrandAdAnalyticsForbidden",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        404: inline_serializer(
            "BrandAdAnalyticsNotFound",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class BrandAdAnalyticsView(generics.GenericAPIView):
    """
    GET /v1/brands/ads/analytics/<ad_id>/

    Brand-user-facing ad analytics. Owned ads only.
    is_finished = slots exhausted OR ad expired OR is_active==False.
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, ad_id):
        try:
            ad = CreateAd.objects.prefetch_related(
                "ad_media",
                "brand_location",
                "brand_submissions__user__social_profile",
            ).get(id=ad_id)
        except CreateAd.DoesNotExist:
            return Response(
                data=encrypt({"status": "error", "message": "Ad not found."}),
                status=status.HTTP_404_NOT_FOUND,
            )

        if ad.user_id != request.user.id:
            return Response(
                data=encrypt({"status": "error", "message": "Not your ad."}),
                status=status.HTTP_403_FORBIDDEN,
            )

        now = timezone.now()
        slots_exhausted = bool(ad.slot_cap and ad.slots_filled >= ad.slot_cap)
        expired = bool(ad.expiry_date and ad.expiry_date <= now)
        is_finished = slots_exhausted or expired or not ad.is_active

        duration_days = int(ad.campaign_duration) if ad.campaign_duration else None
        if is_finished:
            task_duration = (
                f"{duration_days} Days (Completed)" if duration_days else None
            )
            current_day = None
        else:
            current_day = (now - ad.created_at).days + 1 if ad.created_at else None
            task_duration = None

        media = [{"images": m.images, "videos": m.videos} for m in ad.ad_media.all()]

        base = {
            "id": ad.id,
            "is_finished": is_finished,
            "ad_media": media,
            "objective": ad.brand_objective,
            "task_type": ad.task_type,
            "task_type_display": ad.get_task_type_display() if ad.task_type else None,
            "platform": ad.task_details.get("platform") if ad.task_details else None,
            "slots_filled": ad.slots_filled,
            "slot_cap": ad.slot_cap,
            "current_day": current_day,
            "duration_days": duration_days,
            "task_duration_label": task_duration,
            "task_name": ad.task_name,
            "task_description": ad.task_description,
            "campaign_budget": ad.amount,
            "reward_points": ad.reward_points,
            "brand_name": ad.business_or_brand_name,
            "business_type": ad.type_of_business,
            "industry": ad.industry,
            "user_action": ad.engagement_type,
            "comment_prompt": (
                ad.task_details.get("comment_prompt") if ad.task_details else None
            ),
            "timing": ad.task_details.get("timing") if ad.task_details else None,
            "auto_boost": ad.auto_boost,
            "auto_boost_points": ad.auto_boost_points,
        }

        if not is_finished:
            locations = [loc.state for loc in ad.brand_location.all() if loc.state]
            base["location_perimeter"] = {
                "gender": ad.gender,
                "demography": ad.demography,
                "states": locations,
                "slot_cap": ad.slot_cap,
                "reward_points": ad.reward_points,
            }
            base["performance_breakdown"] = None
            base["performance_demographic"] = None
        else:
            approved = ad.brand_submissions.filter(status="Approved")

            cpe = ad.cost_per_engagement
            budget_spent = Decimal(str(ad.slots_filled or 0)) * cpe
            if budget_spent == 0 and ad.amount:
                budget_spent = Decimal(str(ad.amount))

            total_points_rewarded = (ad.slots_filled or 0) * (ad.reward_points or 0)

            sex_qs = (
                approved.values("user__social_profile__sex")
                .annotate(count=Count("id"))
                .order_by("-count")
            )
            age_qs = (
                approved.values("user__social_profile__age_bracket")
                .annotate(count=Count("id"))
                .order_by("-count")
            )
            state_qs = (
                approved.values("user__social_profile__state")
                .annotate(count=Count("id"))
                .order_by("-count")
            )

            base["location_perimeter"] = None
            base["performance_breakdown"] = {
                "campaign_budget": ad.amount,
                "budget_spent": str(budget_spent),
                "ads_credit": str(ad.ads_credit),
                "total_points_rewarded": total_points_rewarded,
                "reward_per_person": ad.reward_points,
                "auto_boost_points": ad.auto_boost_points,
            }
            base["performance_demographic"] = {
                "by_sex": {
                    row["user__social_profile__sex"]: row["count"]
                    for row in sex_qs
                    if row["user__social_profile__sex"]
                },
                "by_age_bracket": {
                    row["user__social_profile__age_bracket"]: row["count"]
                    for row in age_qs
                    if row["user__social_profile__age_bracket"]
                },
                "by_state": {
                    row["user__social_profile__state"]: row["count"]
                    for row in state_qs
                    if row["user__social_profile__state"]
                },
            }

        return Response(
            data=encrypt(
                {
                    "status": "success",
                    "message": "Ad analytics retrieved successfully",
                    "data": base,
                }
            ),
            status=status.HTTP_200_OK,
        )
