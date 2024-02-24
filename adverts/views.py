from decouple import config

# Third party imports
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication

# In project imports.
from .serializers import (
    CreateBrandAdvertSeriailizers,
    BrandAdProfileSerializers,
    UpdateBrandAdProfileSerializers,
    BrandSurveySerializers,
    AdBudgetSerializer,
)
from mail import send_email
from accounts.models import User, UserNotification
from permissions import IsBrandAd, IsBrandAdAdmin
from .models import CreateAd, AdLocation
from wallets.controllers import Pin, Debit, Credit
from banking.controllers import Account


picadailys_email = config("EMAIL_HOST_USER")
app_password = config("EMAIL_HOST_PASSWORD")


class CreateBrandAdvertsAccount(generics.GenericAPIView):
    serializer_class = CreateBrandAdvertSeriailizers

    def post(self, request):
        user = request.data
        serializer = self.serializer_class(data=user)
        if serializer.is_valid(raise_exception=True):
            user = serializer.save()

            # # Save the device_id separately using DeviceId model
            # device_id = user_data.get("device_id")
            # if device_id:
            #     DeviceId.objects.create(user=user, device_id=device_id)

            UserNotification.objects.create(
                user=request.user,
                title="Brand Account.",
                messsage="Brand advert account created Successfully."
            )

            user_data = serializer.data
            response = {
                "status": "success",
                "message": "Brand advert account created Successfully.",
                "data": user_data,
            }
            return Response(data=response, status=status.HTTP_201_CREATED)
        else:
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ListAllBrandAds(generics.ListAPIView):
    serializer_class = BrandAdProfileSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated & (IsBrandAd | IsBrandAdAdmin)]

    def get_queryset(self):
        brand_ads = User.objects.filter(account_type="BrandAd")
        return brand_ads

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.serializer_class(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class GetBrandAdDetails(generics.RetrieveAPIView):
    """GetBrandAdDetails returns the profile details of a brand_Ad user."""

    serializer_class = BrandAdProfileSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated & (IsBrandAd | IsBrandAdAdmin)]

    def retrieve(self, request, *args, **kwargs):
        user = self.request.user  # Get the authenticated user
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
                return Response({"error": str(err)}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class BrandPromote(generics.CreateAPIView):
    serializer_class = AdBudgetSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsBrandAd)

    def create(self, request, *args, **kwargs):
        serializer = AdBudgetSerializer(data=request.data)
        if serializer.is_valid(raise_exception=True):
            try:
                authenticated_user = request.user
                pin = request.data.get("pin")

                is_verified = Pin.verify_pin(user=authenticated_user, pin=pin)
                if is_verified:
                    # Inititate a debit on the brand advert's account.
                    price = request.data.get("price")
                    debit_response = Debit.debit_customer(
                        amount=price, description="Debit for brand promotion"
                    )
                    if debit_response == 200:
                        serializer.save()
                        UserNotification.objects.create(
                            user=request.user,
                            title="Brand Promotion.",
                            messsage=f"This is to inform you that your payment of {price} \
                                for brand promotion is successful."
                        )
                        send_email(
                            subject="Debit Transaction.",
                            body=f"This is to inform you that your payment of {price} \
                                for brand promotion is successful.",
                            sender=picadailys_email,
                            recipients=authenticated_user.email,
                            password=app_password,
                        )
                        response_data = {
                            "status": "Success!",
                            "message": "Brand advert promoted successfully",
                        }

                        return Response(data=response_data, status=status.HTTP_200_OK)
                    else:
                        # initiate a credit refund to the customer after failed transaction.
                        resp = Account.credit(
                            first_name=authenticated_user.firstName,
                            lastname=authenticated_user.lastName,
                            accNo=authenticated_user.accountNumber,
                            bankCode="103",
                            amount=price,
                        )
                        if resp.status_code == 200:
                            UserNotification.objects.create(
                                user=request.user,
                                title="Brand Promotion.",
                                messsage=f"This is to inform you that a refund {price} \
                                    for brand promotion has been issued.",
                            )
                            send_email(
                                subject="Creit Transaction.",
                                body=f"This is to inform you that a refund {price} \
                                    for brand promotion has been issued.",
                                sender=picadailys_email,
                                recipients=authenticated_user.email,
                                password=app_password,
                            )
                        response_data = {
                            "status": "fail!",
                            "messsage": "A refund will be issued.",
                            "details": resp,
                        }

                        return Response(data=response_data, status=status.HTTP_200_OK)

            except Exception as err:
                return Response({"error": str(err)}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)
