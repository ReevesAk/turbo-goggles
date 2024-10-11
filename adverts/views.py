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


picadailys_email = config("EMAIL_HOST_USER")
app_password = config("EMAIL_HOST_PASSWORD")


class PaginationStyle(PageNumberPagination):
    page_size = 20


class CreateBrandAdvertsAccount(generics.GenericAPIView):
    serializer_class = CreateBrandAdvertSeriailizers

    def post(self, request):
        user = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in request.data.items()
        }
        authenticated_user = request.user
        serializer = self.serializer_class(data=user)
        if serializer.is_valid(raise_exception=True):
            serializer.save()

            # # Save the device_id separately using DeviceId model
            # device_id = user_data.get("device_id")
            # if device_id:
            #     DeviceId.objects.create(user=user, device_id=device_id)

            UserNotification.objects.create(
                user=authenticated_user,
                title="Brand Account.",
                message="Brand advert account created Successfully.",
            )
            brand_user = User.objects.get(email=authenticated_user.email)

            AccountType.objects.create(
                user=brand_user,
                user_type="BrandAd",
            )
            brand_user.active_role = "BrandAd"
            brand_user.save()

            response = {
                "status": "success",
                "message": "Brand advert account created Successfully.",
                "data": {
                    "whoareyou": request.data.get("whoareyou"),
                    "facebook": request.data.get("facebook"),
                    "twitter": request.data.get("twitter"),
                    "instagram": request.data.get("instagram"),
                    "telegram": request.data.get("telegram"),
                },
            }
            return Response(data=response, status=status.HTTP_201_CREATED)
        else:
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ListAllBrandAds(generics.ListAPIView):
    serializer_class = BrandAdProfileSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated & (IsBrandAd | IsBrandAdAdmin)]
    pagination_class = PaginationStyle

    def get_queryset(self):
        brand_ads = User.objects.filter(active_role="BrandAd")
        return brand_ads

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.serializer_class(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.serializer_class(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class GetBrandAdDetails(generics.RetrieveAPIView):
    """GetBrandAdDetails returns the profile details of a brand_Ad user."""

    serializer_class = BrandAdProfileSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated & (IsBrandAd | IsBrandAdAdmin)]

    def retrieve(self, request, *args, **kwargs):
        user = self.request.user
        serializer = self.get_serializer(user)
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
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data, status=status.HTTP_200_OK)


class BrandSurveyView(generics.CreateAPIView):
    serializer_class = BrandSurveySerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsBrandAd)

    def create(self, request, *args, **kwargs):
        serializer = BrandSurveySerializers(data=request.data)
        if serializer.is_valid(raise_exception=True):
            try:
                serializer.validated_data["user"] = request.user
                brand_survey = serializer.save()

                brand_survey_instance = CreateAd.objects.create(
                    brand_user=brand_survey.user,
                    brand_type=request.data["brand_type"],
                    product_type=request.data["product_type"],
                    online_presence=request.data["online_presence"],
                    online_preferences=request.data["online_preferences"],
                    metric_to_increase=request.data["metric_to_increase"],
                    demography=request.data["demography"],
                    website=request.data["website"],
                    type=request.data["type"],
                    category=request.data["category"],
                    address=request.data["address"],
                    description=request.data["description"],
                    duration=request.data["duration"],
                )

                AdLocation.objects.create(
                    brand=brand_survey_instance,
                    state=request.data.get("state"),
                    city=request.data.get("city"),
                )

                return Response(serializer.data, status=status.HTTP_201_CREATED)
            except Exception as err:
                logging.error(f"brand advert survey failed with {err}")
                return Response({"error": str(err)}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class BrandPromote(generics.CreateAPIView):
    serializer_class = AdBudgetSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsBrandAd)

    def create(self, request, *args, **kwargs):
        payload = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in request.data.items()
        }
        serializer = AdBudgetSerializer(data=payload)
        if serializer.is_valid(raise_exception=True):
            try:
                authenticated_user = request.user
                pin = request.data.get("pin")

                is_verified = Pin.verify_pin(user=authenticated_user, pin=pin)
                if is_verified:
                    # Inititate a debit on the brand advert's account.
                    price = request.data.get("price")
                    user_details = AccountCreation.objects.get(user=authenticated_user)
                    debit_response = Account.Debit(
                        debitAccount=user_details.account_number,
                        amount=price, description="Debit for brand promotion",
                        transactionReference=""
                    )
                    if debit_response == 200:
                        serializer.save()
                        UserNotification.objects.create(
                            user=request.user,
                            title="Brand Promotion.",
                            message=f"This is to inform you that your payment of {price} \
                                for brand promotion is successful.",
                        )
                        # send_email(
                        #     subject="Debit Transaction.",
                        #     body=f"This is to inform you that your payment of {price} \
                        #         for brand promotion is successful.",
                        #     sender=picadailys_email,
                        #     recipients=authenticated_user.email,
                        #     password=app_password,
                        # )
                        response_data = {
                            "status": "Success!",
                            "message": "Brand advert promoted successfully",
                        }

                        return Response(data=response_data, status=status.HTTP_200_OK)
                    else:
                        response_data = {
                            "status": "fail!",
                            "details": debit_response.json(),
                        }

                        return Response(data=response_data, status=status.HTTP_200_OK)

            except Exception as err:
                return Response({"error": str(err)}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)
