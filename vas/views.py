import os
import json
import logging
import requests
from decouple import config
from django.conf import settings

from rest_framework.views import APIView
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication

from drf_spectacular.utils import extend_schema

from .serializers import (
    VasStatusSerializer,
    VerifyMeterSerializer,
    AirtimeTopupSerializer,
    DataSubscriptionSerializer,
    ElectricityBillSerializer,
    VerifyCardNumberSerializer,
    TvSubscriptionSerializer,
    ProductStatusSerializer,
    WaecRegistrationSerializer,
)
from banking.models import AccountCreation
from banking.controllers import Account
from permissions import VasPermission, IsAuthenticatedOrGuestWithValidId
from banking.helpers import Pin
from .controllers import (
    airtime,
    data,
    electricity,
    NewTvSub,
    RenewTvSub,
    waec_reg,
)
from .utility import (
    create_activity,
    create_notification,
    send_token,
    send_token_to_guest_users,
)
from .helpers import VAS
from .models import ELECTRICITY_SERVICE_ID_CHOICES, TV_SERVICE_ID_CHOICES
from commons import Pay, Biometrics
from security import encrypt, decrypt


vtpass_url = config("VT_PASS_BASE_URL")
x_secret = config("VT_PASS_SECRET_KEY")
api_key = config("VT_PASS_API_KEY")
x_token = config("VT_PASS_PUBLIC_KEY")

logger = logging.getLogger(__name__)


class AirTimeTopUp(generics.GenericAPIView):
    """
    AirTimeTopUp is a POST request handler for purchasing airtime for
    service providers in Nigeria.
    """

    serializer_class = AirtimeTopupSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticatedOrGuestWithValidId]

    def post(self, request):
        decrypted_payload = decrypt(request.data)
        user_data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_payload.items()
        }
        user = request.user if request.user.is_authenticated else None

        pin = decrypted_payload.get("pin")
        guest_id = decrypted_payload.get("guest_id")
        payment_option = decrypted_payload.get("payment_option")
        use_bonus = user_data.get("use_bonus")
        use_points = user_data.get("use_points")
        phone = user_data.get("phone")
        use_rewards = user_data.get("use_rewards")
        amount = user_data.get("amount")

        if not user:  # Guest user flow
            if not guest_id:
                return Response(
                    data=encrypt({"status": "fail", "message": "Guest ID required"}),
                    status=status.HTTP_400_BAD_REQUEST
                )

            if payment_option != "CARD":
                return Response(
                    data=encrypt({
                        "status": "fail", 
                        "message": "Guests can only use card payments"
                    }),
                    status=status.HTTP_400_BAD_REQUEST
                )

        serializer = self.serializer_class(data=user_data)
        if not serializer.is_valid(raise_exception=True):
            logger.warning(
                f"Serializer validation failed for user {user.first_name} {user.last_name}: {serializer.errors}"
            )
            return Response(
                data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST
            )

        biometrics = decrypted_payload.get("use_biometrics")

        try:
            if payment_option != "CARD":
                account = AccountCreation.objects.get(user=user)
                logger.info(
                    f"Account found for user {user.first_name} {user.last_name}."
                )
        except AccountCreation.DoesNotExist:
            logger.error(
                f"Account not found for user {user.first_name} {user.last_name}."
            )
            return Response(
                data=encrypt({"status": "fail", "error": "Account not found for user"}),
                status=status.HTTP_404_NOT_FOUND,
            )

        if biometrics:
            verification = Biometrics.authenticate(user.phone_number)

        elif payment_option == "WALLET":
            if account and account.pin is not None:
                verification = Pin.verify(user=user, pin=pin, hashed_pin=account.pin)
                logger.info(
                    f"User {user.first_name} {user.last_name} is using PIN for authentication."
                )
            else:
                logger.error(
                    f"Account or PIN not found for user {user.first_name} {user.last_name}."
                )
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "error": "Account or PIN not found for user",
                        }
                    ),
                    status=status.HTTP_404_NOT_FOUND,
                )
        else:
            verification = True

        if not verification:
            logger.warning(
                f"Invalid credentials provided for user {user.first_name} {user.last_name}."
            )
            return Response(
                data=encrypt({"status": "fail", "error": "Invalid credentials"}),
                status=status.HTTP_401_UNAUTHORIZED,
            )

        airtime_response = None

        if use_bonus:
            logger.info(
                f"User {user.first_name} {user.last_name} is attempting to use bonus for purchase."
            )
            if user.welcome_bonus >= float(amount):
                airtime_response = airtime(
                    user=user,
                    serializer=serializer,
                    reason="Debit for airtime recharge.",
                    user_data=user_data,
                )
                if airtime_response["code"] == "000":
                    response_data = {
                        "status": "success",
                        "message": f"Airtime purchase of {float(amount)} was successful.",
                        "bonus balance": user.welcome_bonus,
                        "airtime_response": airtime_response,
                    }
                    logger.info(
                        f"User {user.first_name} {user.last_name} successfully purchased airtime using bonus."
                    )
                    title = ("Airtime purchase",)
                    message = (
                        f"This is to inform you that you have made a purchase of {amount} naira airtime on {phone}.",
                    )
                    description = (
                        f"{user.first_name} {user.last_name} has made a purchase of {amount} naira airtime on {phone}.",
                    )
                    create_notification(user=request.user, title=title, message=message)
                    create_activity(
                        user=request.user, title=title, description=description
                    )
                    return Response(
                        data=encrypt(response_data), status=status.HTTP_200_OK
                    )
                elif airtime_response["code"] == "014":
                    request_id = airtime_response.get("requestId")
                    if request_id:
                        status_query = VAS.check_status(req_id=request_id)
                        if (
                            status_query["content"]["transactions"]["status"]
                            == "delivered"
                        ):
                            response_data = {
                                "status": "success",
                                "message": f"Airtime purchase of {amount} was successful.",
                                "bonus balance": user.welcome_bonus,
                                "airtime_response": airtime_response,
                            }
                            create_notification(
                                user=request.user,
                                title="Airtime purchase",
                                message=f"This is to inform you that you have made a purchase of {amount} naira airtime on {phone}.",
                            )
                            create_activity(
                                user=request.user,
                                title="Airtime purchase",
                                description=f"{user.first_name} {user.last_name} has made a purchase of {amount} naira airtime on {phone}.",
                            )
                            logger.info(
                                f"User {user.first_name} {user.last_name} successfully purchased airtime with WALLET option."
                            )
                            return Response(
                                data=encrypt(response_data), status=status.HTTP_200_OK
                            )
                    else:
                        response_data = {
                            "status": "fail",
                            "message": airtime_response["response_description"],
                        }
                        return Response(
                            data=encrypt(response_data),
                            status=status.HTTP_400_BAD_REQUEST,
                        )
            logger.warning(
                f"Airtime top-up failed for user {user.first_name} {user.last_name} due to insufficient bonus."
            )
            create_notification(
                user=request.user,
                title="Airtime purchase",
                message=f"This is to inform you the purchase of {amount} naira airtime on {phone} failed due to insufficient bonus.",
            )
            create_activity(
                user=request.user,
                title="Airtime purchase",
                description=f"{user.first_name} {user.last_name}'s purchase of {amount} naira airtime on {phone} failed due to insufficient bonus.",
            )
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "Airtime top-up failed due to insufficient bonus.",
                        "error": airtime_response,
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        match payment_option:
            case "WALLET":
                logger.info(
                    f"User {user.first_name} {user.last_name} selected WALLET as payment option."
                )
                if use_points:
                    _, pts_amt = Pay.with_pts(user=user, amount=amount)
                    logger.info(
                        f"User {user.first_name} {user.last_name} used points amounting to {pts_amt}."
                    )
                else:
                    pts_amt = 0

                if use_rewards:
                    _, rwd_amt = Pay.with_rwd(user=user, amount=amount)
                    logger.info(
                        f"User {user.first_name} {user.last_name} used rewards amounting to {rwd_amt}."
                    )
                else:
                    rwd_amt = 0

                new_amount = int(amount) - pts_amt - rwd_amt
                user_details = AccountCreation.objects.get(user=user)

                # Initiate a debit on the customer's account.
                debit_response = Account.Debit(
                    debitAccount=user_details.account_number,
                    amount=new_amount,
                    reason="Debit for airtime recharge.",
                    transactionReference="",
                )

                if debit_response.status_code == 200:
                    airtime_response = airtime(
                        user=user,
                        serializer=serializer,
                        reason="Debit for airtime recharge",
                        user_data=user_data,
                    )
                    if airtime_response["code"] == "000":
                        response_data = {
                            "status": "success",
                            "message": f"Airtime purchase of {new_amount} was successful.",
                            "bonus balance": user.welcome_bonus,
                            "airtime_response": airtime_response,
                        }
                        logger.info(
                            f"User {user.first_name} {user.last_name} successfully purchased airtime with WALLET option."
                        )
                        create_notification(
                            user=request.user,
                            title="Airtime purchase",
                            message=f"This is to inform you that you have made a purchase of {amount} naira airtime on {phone}.",
                        )
                        create_activity(
                            user=request.user,
                            title="Airtime purchase",
                            description=f"{user.first_name} {user.last_name} has made a purchase of {amount} naira airtime on {phone}.",
                        )
                        return Response(
                            data=encrypt(response_data), status=status.HTTP_200_OK
                        )
                    elif airtime_response["code"] == "014":
                        request_id = airtime_response.get("requestId")
                        if request_id:
                            status_query = VAS.check_status(req_id=request_id)
                            if (
                                status_query["content"]["transactions"]["status"]
                                == "delivered"
                            ):
                                response_data = {
                                    "status": "success",
                                    "message": f"Airtime purchase of {new_amount} was successful.",
                                    "bonus balance": user.welcome_bonus,
                                    "airtime_response": airtime_response,
                                }
                                logger.info(
                                    f"User {user.first_name} {user.last_name} successfully purchased airtime with WALLET option."
                                )
                                create_notification(
                                    user=request.user,
                                    title="Airtime purchase",
                                    message=f"This is to inform you that you have made a purchase of {new_amount} naira airtime on {phone}.",
                                )
                                create_activity(
                                    user=request.user,
                                    title="Airtime purchase",
                                    description=f"{user.first_name} {user.last_name} has made a purchase of {new_amount} naira airtime on {phone}.",
                                )
                                return Response(
                                    data=encrypt(response_data),
                                    status=status.HTTP_200_OK,
                                )
                        else:
                            response_data = {
                                "status": "fail",
                                "message": airtime_response["response_description"],
                            }
                            return Response(
                                data=encrypt(response_data),
                                status=status.HTTP_400_BAD_REQUEST,
                            )
                    else:
                        logger.warning(
                            f"Airtime top-up failed for user {user.first_name} {user.last_name} with WALLET option due to insufficient balance."
                        )
                        return Response(
                            data=encrypt(
                                {
                                    "status": "fail",
                                    "message": "Airtime top-up failed due to insufficient balance.",
                                    "error": airtime_response,
                                }
                            ),
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                else:
                    logger.error(
                        f"Debit failed for user {user.first_name} {user.last_name} with WALLET option: {debit_response.json()}."
                    )
                    return Response(
                        data=encrypt(debit_response.json()),
                        status=debit_response.status_code,
                    )
            case "CARD":
                if user:
                    logger.info(
                        f"User {user.first_name} {user.last_name} selected CARD as payment option."
                    )

                    airtime_response = airtime(
                        user=user,
                        guest_id=guest_id,
                        serializer=serializer,
                        reason="Debit for airtime recharge.",
                        user_data=user_data,
                    )
                    if airtime_response["code"] == "000":
                        response_data = {
                            "status": "success",
                            "message": f"Airtime purchase of {amount} was successful.",
                            "bonus balance": user.welcome_bonus,
                            "airtime_response": airtime_response,
                        }
                        logger.info(
                            f"User {user.first_name} {user.last_name} successfully purchased airtime with CARD option."
                        )

                        create_notification(
                            user=request.user,
                            title="Airtime purchase",
                            message=f"This is to inform you that you have made a purchase of {amount} naira airtime on {phone}.",
                        )
                        create_activity(
                            user=request.user,
                            title="Airtime purchase",
                            description=f"{user.first_name} {user.last_name} has made a purchase of {amount} naira airtime on {phone}.",
                        )
                    elif airtime_response["code"] == "014":
                        request_id = airtime_response.get("requestId")
                        if request_id:
                            status_query = VAS.check_status(req_id=request_id)
                            if (
                                status_query["content"]["transactions"]["status"]
                                == "delivered"
                            ):
                                response_data = {
                                    "status": "success",
                                    "message": f"Airtime purchase of {amount} was successful.",
                                    "bonus balance": user.welcome_bonus,
                                    "airtime_response": airtime_response,
                                }

                                logger.info(
                                    f"User {user.first_name} {user.last_name} successfully purchased airtime with CARD option."
                                )
                                create_notification(
                                    user=request.user,
                                    title="Airtime purchase",
                                    message=f"This is to inform you that you have made a purchase of {amount} naira airtime on {phone}.",
                                )
                                create_activity(
                                    user=request.user,
                                    title="Airtime purchase",
                                    description=f"{user.first_name} {user.last_name} has made a purchase of {amount} naira airtime on {phone}.",
                                )
                                return Response(
                                    data=encrypt(response_data), status=status.HTTP_200_OK
                                )
                        else:
                            response_data = {
                                "status": "fail",
                                "message": airtime_response["response_description"],
                            }
                            return Response(
                                data=encrypt(response_data),
                                status=status.HTTP_400_BAD_REQUEST,
                            )
                    else:
                        logger.warning(
                            f"Airtime top-up failed for user {user.first_name} {user.last_name} with CARD option."
                        )
                        return Response(
                            data=encrypt(
                                {
                                    "status": "fail",
                                    "message": "Airtime top-up failed.",
                                    "error": airtime_response,
                                }
                            ),
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                else:
                    try:
                        airtime_response = airtime(
                            user=None,
                            guest_id=guest_id,
                            serializer=serializer,
                            reason="Guest airtime purchase",
                            user_data=user_data
                        )

                        if airtime_response["code"] == "000":
                            logger.info(f"Guest {guest_id} purchase successful")
                            create_activity(
                                user=None,
                                guest_id=guest_id,
                                title="Airtime purchase",
                                description=f"Guest {guest_id} purchased {user_data['amount']} airtime"
                            )
                            return Response(
                                data=encrypt({
                                    "status": "success",
                                    "message": f"Airtime purchase of {user_data['amount']} was successful",
                                    "airtime_response": airtime_response
                                }),
                                status=status.HTTP_200_OK
                            )

                        elif airtime_response["code"] == "014":
                            request_id = airtime_response.get("requestId")
                            if request_id and VAS.check_status(req_id=request_id)["content"]["transactions"]["status"] == "delivered":
                                logger.info(f"Guest {guest_id} purchase eventually succeeded")
                                create_activity(
                                    user=None,
                                    guest_id=guest_id,
                                    title="Airtime purchase",
                                    description=f"Guest {guest_id} purchased {user_data['amount']} airtime"
                                )
                                return Response(
                                    data=encrypt({
                                        "status": "success",
                                        "message": "Airtime purchase was successful",
                                        "airtime_response": airtime_response
                                    }),
                                    status=status.HTTP_200_OK
                                )

                        logger.warning(f"Guest {guest_id} purchase failed: {airtime_response}")
                        create_activity(
                            user=None,
                            guest_id=guest_id,
                            title="Failed airtime purchase",
                            description=f"Guest {guest_id} failed to purchase airtime"
                        )
                        return Response(
                            data=encrypt({
                                "status": "fail",
                                "message": airtime_response.get("response_description", "Purchase failed"),
                                "error": airtime_response
                            }),
                            status=status.HTTP_400_BAD_REQUEST
                        )

                    except Exception as e:
                        logger.error(f"Guest {guest_id} processing error: {str(e)}")
                        return Response(
                            data=encrypt({
                                "status": "error",
                                "message": "Processing error occurred"
                            }),
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR
                        )
            case _:
                logger.error(
                    f"Invalid payment option selected by user {user.first_name} {user.last_name}: {payment_option}."
                )
                return Response(
                    data=encrypt(
                        {"status": "fail", "message": "Invalid payment option"}
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )


class GetNetworkProvidersVariationCodes(generics.RetrieveAPIView):
    serializer_class = VasStatusSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticatedOrGuestWithValidId,)

    @extend_schema(
        description="Variation codes from local JSON files",
        responses={200: {"description": "Network Providers Variation Codes"}},
    )
    def get(self, request, *args, **kwargs):
        user = request.user if request.user.is_authenticated else None
        service_id = kwargs.get("service_ID")

        if not user:
            return Response(
                data=encrypt({"error": "User not authenticated"}),
                status=status.HTTP_401_UNAUTHORIZED,
            )

        service_id_raw = kwargs.get("service_ID", "").lower()
        service_id = service_id_raw.split("-")[0]  # extract prefix before '-'

        filename_map = {
            "mtn": "mtn-data_sorted.json",
            "glo": "glo-data_sorted.json",
            "etisalat": "etisalat-data_sorted.json",
            "airtel": "airtel-data_sorted.json",
        }

        filename = filename_map.get(service_id)
        if not filename:
            return Response(
                data=encrypt({"error": f"Unknown service_ID '{service_id_raw}'"}),
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Compose the path to the JSON file inside variation_codes folder
        json_path = os.path.join(settings.BASE_DIR, "variation_codes", filename)

        if not os.path.isfile(json_path):
            return Response(
                data=encrypt({
                    "status": "error",
                    "message": f"Variation codes not found for {service_id}"
                }),
                status=status.HTTP_404_NOT_FOUND
            )

        try:
            with open(json_path, "r") as f:
                data = json.load(f)

            return Response(
                data=encrypt({
                    "status": "success",
                    "message": f"Variation codes for {service_id} retrieved successfully.",
                    "service": service_id,
                    "data": data
                }),
                status=status.HTTP_200_OK
            )

        except json.JSONDecodeError:
            return Response(
                data=encrypt({
                    "status": "error",
                    "message": "Invalid variation codes format"
                }),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except Exception as e:
            return Response(
                data=encrypt({
                    "status": "error",
                    "message": f"Failed to load variation codes: {str(e)}"
                }),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class DataSubscriptionView(generics.GenericAPIView):
    """
    DataSubscriptionView is a POST request handler for data
    subscription.
    """

    serializer_class = DataSubscriptionSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticatedOrGuestWithValidId]

    def post(self, request):
        decrypted_payload = decrypt(request.data)
        user_data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_payload.items()
        }
        user = request.user if request.user.is_authenticated else None

        pin = user_data.get("pin")
        guest_id = user_data.get("guest_id")
        use_bonus = user_data.get("use_bonus")
        amount = user_data.get("amount")
        phone = user_data.get("phone")
        use_points = user_data.get("use_points")
        use_rewards = user_data.get("use_rewards")
        payment_option = user_data.get("payment_option")

        if not user:  # Guest user flow
            if not guest_id:
                return Response(
                    data=encrypt({"status": "fail", "message": "Guest ID required"}),
                    status=status.HTTP_400_BAD_REQUEST
                )

            if payment_option != "CARD":
                return Response(
                    data=encrypt({
                        "status": "fail", 
                        "message": "Guests can only use card payments"
                    }),
                    status=status.HTTP_400_BAD_REQUEST
                )

            logger.info(f"Guest {guest_id} attempting data subscription")

        serializer = self.serializer_class(data=user_data)
        if not serializer.is_valid(raise_exception=True):
            logger.warning(
                f"Serializer validation failed for user {user.first_name} {user.last_name}: {serializer.errors}"
            )
            return Response(
                data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST
            )

        biometrics = user_data.get("use_biometrics")

        try:
            if payment_option != "CARD":
                account = AccountCreation.objects.get(user=user)
                logger.info(
                    f"Account found for user {user.first_name} {user.last_name}."
                )
        except AccountCreation.DoesNotExist:
            logger.error(
                f"Account not found for user {user.first_name} {user.last_name}."
            )
            return Response(
                data=encrypt({"status": "fail", "error": "Account not found for user"}),
                status=status.HTTP_404_NOT_FOUND,
            )

        if biometrics:
            verification = Biometrics.authenticate(user.phone_number)
            logger.info(
                f"User {user.first_name} {user.last_name} is using biometrics for authentication."
            )
        elif payment_option == "WALLET":
            if account and account.pin is not None:
                verification = Pin.verify(user=user, pin=pin, hashed_pin=account.pin)
                logger.info(
                    f"User {user.first_name} {user.last_name} is using PIN for authentication."
                )
            else:
                logger.error(
                    f"Account or PIN not found for user {user.first_name} {user.last_name}."
                )
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "error": "Account or PIN not found for user",
                        }
                    ),
                    status=status.HTTP_404_NOT_FOUND,
                )
        else:
            verification = True

        if not verification:
            logger.warning(
                f"Invalid credentials provided for user {user.first_name} {user.last_name}."
            )
            return Response(
                data=encrypt({"status": "fail", "error": "Invalid credentials"}),
                status=status.HTTP_401_UNAUTHORIZED,
            )

        data_response = None

        if use_bonus:
            logger.info(
                f"User {user.first_name} {user.last_name} is attempting to use bonus for data purchase."
            )
            if user.welcome_bonus >= float(amount):
                data_response = data(
                    user=user,
                    serializer=serializer,
                    reason="Debit for data subscription.",
                    user_data=user_data,
                )
                if data_response["code"] == "000":
                    logger.debug(f"response data: {data_response}")
                    response_data = {
                        "status": "success",
                        "message": f"Data purchase of {float(amount)} was successful.",
                        "bonus balance": user.welcome_bonus,
                        "data_response": data_response,
                    }
                    logger.info(
                        f"User {user.first_name} {user.last_name} successfully purchased data using bonus."
                    )
                    create_notification(
                        user=request.user,
                        title="Data subscription",
                        message=f"This is to inform you that you have made a purchase of {amount} naira data subscription on {phone}.",
                    )
                    create_activity(
                        user=request.user,
                        title="Data subscription",
                        description=f"{user.first_name} {user.last_name} has made a purchase of {amount} naira data subscription on {phone}",
                    )
                    return Response(
                        data=encrypt(response_data), status=status.HTTP_200_OK
                    )
                elif data_response["code"] == "014":
                    logger.debug(f"response data: {data_response}")
                    request_id = data_response.get("requestId")
                    if request_id:
                        status_query = VAS.check_status(req_id=request_id)
                        if (
                            status_query["content"]["transactions"]["status"]
                            == "delivered"
                        ):
                            response_data = {
                                "status": "pending",
                                "message": f"Data purchase of {float(amount)} was successful.",
                                "bonus balance": user.welcome_bonus,
                                "data_response": data_response,
                            }
                            logger.info(
                                f"User {user.first_name} {user.last_name} successfully purchased data using bonus."
                            )
                            create_notification(
                                user=request.user,
                                title="Data subscription",
                                message=f"This is to inform you that you have made a purchase of {amount} naira data subscription on {phone}.",
                            )
                            create_activity(
                                user=request.user,
                                title="Data subscription",
                                description=f"{user.first_name} {user.last_name} has made a purchase of {amount} naira data subscription on {phone}",
                            )
                            return Response(
                                data=encrypt(response_data), status=status.HTTP_200_OK
                            )
                    else:
                        response_data = {
                            "status": "fail",
                            "data_response": data_response,
                        }
                        return Response(
                            data=encrypt(response_data),
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                else:
                    response_data = {
                        "status": "fail",
                        "message": f"Data purchase of {float(amount)} failed.",
                        "bonus balance": user.welcome_bonus,
                        "data_response": data_response,
                    }
                    logger.info(
                        f"User {user.first_name} {user.last_name} purchase of data using bonus failed."
                    )
                    return Response(
                        data=encrypt(response_data), status=status.HTTP_400_BAD_REQUEST
                    )
            logger.warning(
                f"Data subscription failed for user {user.first_name} {user.last_name} due to insufficient bonus."
            )
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "Data subscription failed due to insufficient bonus.",
                        "error": data_response,
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        match payment_option:
            case "WALLET":
                logger.info(
                    f"User {user.first_name} {user.last_name} selected WALLET as payment option."
                )
                if use_points:
                    _, pts_amt = Pay.with_pts(user=user, amount=amount)
                    logger.info(
                        f"User {user.first_name} {user.last_name} used points amounting to {pts_amt}."
                    )
                else:
                    pts_amt = 0

                if use_rewards:
                    _, rwd_amt = Pay.with_rwd(user=user, amount=amount)
                    logger.info(
                        f"User {user.first_name} {user.last_name} used rewards amounting to {rwd_amt}."
                    )
                else:
                    rwd_amt = 0

                new_amount = int(amount) - pts_amt - rwd_amt
                user_details = AccountCreation.objects.get(user=user)
                logger.info(
                    f"Initiating debit for user {user.first_name} {user.last_name}. New amount after points and rewards: {new_amount}."
                )

                # Initiate a debit on the customer's account.
                debit_response = Account.Debit(
                    debitAccount=user_details.account_number,
                    amount=new_amount,
                    reason="Debit for data subscription.",
                    transactionReference="",
                )

                if debit_response.status_code == 200:
                    data_response = data(
                        user=user,
                        serializer=serializer,
                        reason="Debit for data subscription.",
                        user_data=user_data,
                    )
                    if data_response["code"] == "000":
                        response_data = {
                            "status": "success",
                            "message": f"Data purchase of {new_amount} was successful.",
                            "bonus balance": user.welcome_bonus,
                            "data_response": data_response,
                        }
                        logger.info(
                            f"User {user.first_name} {user.last_name} successfully purchased data with WALLET payment option."
                        )
                        create_notification(
                            user=request.user,
                            title="Data subscription",
                            message=f"This is to inform you that you have made a purchase of {new_amount} naira data subscription on {phone}.",
                        )
                        create_activity(
                            user=request.user,
                            title="Data subscription",
                            description=f"{user.first_name} {user.last_name} has made a purchase of {new_amount} naira data subscription on {phone}",
                        )
                        return Response(
                            data=encrypt(response_data), status=status.HTTP_200_OK
                        )
                    if data_response["code"] == "014":
                        request_id = data_response.get("requestId")
                        if request_id:
                            status_query = VAS.check_status(req_id=request_id)
                            if (
                                status_query["content"]["transactions"]["status"]
                                == "delivered"
                            ):
                                response_data = {
                                    "status": "pending",
                                    "message": f"Data purchase of {new_amount} was successful.",
                                    "bonus balance": user.welcome_bonus,
                                    "data_response": data_response,
                                }
                            logger.info(
                                f"User {user.first_name} {user.last_name} successfully purchased data with WALLET payment option."
                            )
                            create_notification(
                                user=request.user,
                                title="Data subscription",
                                message=f"This is to inform you that you have made a purchase of {amount} naira data subscription on {phone}.",
                            )
                            create_activity(
                                user=request.user,
                                title="Data subscription",
                                description=f"{user.first_name} {user.last_name} has made a purchase of {amount} naira data subscription on {phone}",
                            )
                            return Response(
                                data=encrypt(response_data), status=status.HTTP_200_OK
                            )
                        else:
                            response_data = {
                                "status": "fail",
                                "message": data_response["response_description"],
                            }
                            return Response(
                                data=encrypt(response_data),
                                status=status.HTTP_400_BAD_REQUEST,
                            )
                    else:
                        logger.warning(
                            f"Data subscription failed for user {user.first_name} {user.last_name} with WALLET option due to insufficient balance."
                        )
                        return Response(
                            data=encrypt(
                                {
                                    "status": "fail",
                                    "message": "Data subscription failed due to insufficient balance.",
                                    "error": data_response,
                                }
                            ),
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                else:
                    logger.error(
                        f"Debit failed for user {user.first_name} {user.last_name} with WALLET option: {debit_response.json()}."
                    )
                    return Response(
                        data=encrypt(debit_response.json()),
                        status=debit_response.status_code,
                    )
            case "CARD":
                if user:
                    logger.info(
                        f"User {user.first_name} {user.last_name} selected CARD as payment option."
                    )

                    data_response = data(
                        user=user,
                        guest_id=guest_id,
                        serializer=serializer,
                        reason="Debit for data subscription.",
                        user_data=user_data,
                    )
                    if data_response["code"] == "000":
                        response_data = {
                            "status": "success",
                            "message": f"Data purchase of {amount} was successful.",
                            "bonus balance": user.welcome_bonus,
                            "data_response": data_response,
                        }

                        create_notification(
                            user=request.user,
                            title="Data subscription",
                            message=f"This is to inform you that you have made a purchase of {amount} naira data subscription on {phone}.",
                        )
                        create_activity(
                            user=request.user,
                            title="Data subscription",
                            description=f"{user.first_name} {user.last_name} has made a purchase of {amount} naira data subscription on {phone}",
                        )
                        return Response(
                            data=encrypt(response_data), status=status.HTTP_200_OK
                        )
                    if data_response["code"] == "014":
                        request_id = data_response.get("requestId")
                        if request_id:
                            status_query = VAS.check_status(req_id=request_id)
                            if (
                                status_query["content"]["transactions"]["status"]
                                == "delivered"
                            ):
                                response_data = {
                                    "status": "pending",
                                    "message": f"Data purchase of {amount} was successful.",
                                    "bonus balance": user.welcome_bonus,
                                    "data_response": data_response,
                                }
                            logger.info(
                                f"User {user.first_name} {user.last_name} successfully purchased data with WALLET payment option."
                            )
                            create_notification(
                                user=request.user,
                                title="Data subscription",
                                message=f"This is to inform you that you have made a purchase of {amount} naira data subscription on {phone}.",
                            )
                            create_activity(
                                user=request.user,
                                title="Data subscription",
                                description=f"{user.first_name} {user.last_name} has made a purchase of {amount} naira data subscription on {phone}",
                            )
                            return Response(
                                data=encrypt(response_data), status=status.HTTP_200_OK
                            )
                        else:
                            response_data = {
                                "status": "fail",
                                "message": data_response["response_description"],
                            }
                            return Response(
                                data=encrypt(response_data),
                                status=status.HTTP_400_BAD_REQUEST,
                            )
                    else:
                        logger.warning(
                            f"Data subscription failed for user {user.first_name} {user.last_name} with CARD option."
                        )
                        return Response(
                            data=encrypt(
                                {
                                    "status": "fail",
                                    "message": "Data subscription failed.",
                                    "error": data_response,
                                }
                            ),
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                else:
                    try:
                        data_response = data(
                            user=None,
                            guest_id=guest_id,
                            serializer=serializer,
                            reason="Guest data subscription",
                            user_data=user_data
                        )

                        if data_response["code"] == "000":
                            logger.info(f"Guest {guest_id} data subscription successful")
                            create_activity(
                                user=None,
                                guest_id=guest_id,
                                title="Data subscription",
                                description=f"Guest {guest_id} subscribed to {user_data['amount']} data plan"
                            )
                            return Response(
                                data=encrypt({
                                    "status": "success",
                                    "message": f"Data subscription of {user_data['amount']} was successful",
                                    "data_response": data_response
                                }),
                                status=status.HTTP_200_OK
                            )

                        elif data_response["code"] == "014":
                            request_id = data_response.get("requestId")
                            if request_id and VAS.check_status(req_id=request_id)["content"]["transactions"]["status"] == "delivered":
                                logger.info(f"Guest {guest_id} subscription eventually succeeded")
                                create_activity(
                                    user=None,
                                    guest_id=guest_id,
                                    title="Data subscription",
                                    description=f"Guest {guest_id} subscribed to {user_data['amount']} data plan"
                                )
                                return Response(
                                    data=encrypt({
                                        "status": "success",
                                        "message": "Data subscription was successful",
                                        "data_response": data_response
                                    }),
                                    status=status.HTTP_200_OK
                                )

                        logger.warning(f"Guest {guest_id} subscription failed: {data_response}")
                        create_activity(
                            user=None,
                            guest_id=guest_id,
                            title="Failed data subscription",
                            description=f"Guest {guest_id} failed to subscribe to data plan"
                        )
                        return Response(
                            data=encrypt({
                                "status": "fail",
                                "message": data_response.get("response_description", "Subscription failed"),
                                "error": data_response
                            }),
                            status=status.HTTP_400_BAD_REQUEST
                        )

                    except Exception as e:
                        logger.error(f"Guest {guest_id} processing error: {str(e)}")
                        return Response(
                            data=encrypt({
                                "status": "error",
                                "message": "Processing error occurred"
                            }),
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR
                        )
            case _:
                logger.error(
                    f"Invalid payment option selected by user {user.first_name} {user.last_name}: {payment_option}."
                )
                return Response(
                    data=encrypt(
                        {"status": "fail", "message": "Invalid payment option"}
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )


class ElectricityServiceIDListView(APIView):
    """
    ElectricityServiceIDListView is the GET request handler that returns a list of electricity service ids.
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticatedOrGuestWithValidId]

    def get(self, request):
        electricity_service_ids = [
            service_id[1] for service_id in ELECTRICITY_SERVICE_ID_CHOICES
        ]
        return Response(
            data=encrypt(
                {
                    "status": "success.",
                    "message": "Electricity service Ids retrieved successfully.",
                    "categories": electricity_service_ids,
                }
            ),
            status=status.HTTP_200_OK,
        )


class VerifyMeterNumber(generics.RetrieveAPIView):
    """
    VerifySmartCardNumber is a POST request handler for verifying
    electricity meter number.
    """

    serializer_class = VerifyMeterSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, VasPermission)

    @extend_schema(
        description="Meter number",
        responses={200: {"description": "Verify meter number"}},
    )
    def post(self, request):
        decrypted_payload = decrypt(request.data)
        user_data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_payload.items()
        }

        logger.info(
            f"User {request.user.first_name} {request.user.last_name} is attempting to verify meter number with data: {user_data}"
        )

        resource = "merchant-verify"
        payload = {
            "serviceID": user_data["serviceID"],
            "type": user_data["type"],
            "billersCode": user_data["billersCode"],
        }

        verify_meter_headers = {
            "accept": "application/json",
            "api-key": api_key,
            "secret-key": x_secret,
        }

        try:
            logger.info(
                f"Sending POST request to {vtpass_url + resource} with payload: {payload}"
            )
            response = requests.post(
                url=vtpass_url + resource,
                json=payload,
                headers=verify_meter_headers,
            )

            if response.status_code == 200:
                response_data = {
                    "data": response.json(),
                }
                logger.info(
                    f"Meter verification successful for user {request.user.first_name} {request.user.last_name}: {response_data}"
                )
                return Response(data=encrypt(response_data), status=status.HTTP_200_OK)
            else:
                logger.warning(
                    f"Meter verification failed for user {request.user.first_name} {request.user.last_name}: {response.json()}"
                )
                return Response(
                    data=encrypt(response.json()), status=response.status_code
                )

        except requests.exceptions.RequestException as e:
            logger.error(
                f"RequestException occurred for user {request.user.first_name} {request.user.last_name}: {str(e)}"
            )
            return Response(
                data=encrypt({"error": str(e)}),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class ElectrcityBillPayment(generics.GenericAPIView):
    """
    ElectrcityBillPayment is a POST request handler for payment of electricity
    bills for both prepaid and postpaid account types.
    """

    serializer_class = ElectricityBillSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticatedOrGuestWithValidId]

    def post(self, request):
        decrypted_payload = decrypt(request.data)
        user_data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_payload.items()
        }
        user = request.user if request.user.is_authenticated else None

        pin = user_data.get("pin")
        guest_id = user_data.get("guest_id")
        use_bonus = user_data.get("use_bonus")
        amount = user_data.get("amount")
        use_points = user_data.get("use_points")
        use_rewards = user_data.get("use_rewards")
        payment_option = user_data.get("payment_option")

        if user:
            logger.info(
                f"User {user.first_name} {user.last_name} is attempting to make an electricity payment of {amount}."
            )

        if not user:
            if not guest_id:
                return Response(
                    data=encrypt({"status": "fail", "message": "Guest ID required"}),
                    status=status.HTTP_400_BAD_REQUEST
                )

            if payment_option != "CARD":
                return Response(
                    data=encrypt({
                        "status": "fail", 
                        "message": "Guests can only use card payments"
                    }),
                    status=status.HTTP_400_BAD_REQUEST
                )

            logger.info(f"Guest {guest_id} attempting electricity payment")

        serializer = self.serializer_class(data=user_data)
        if not serializer.is_valid(raise_exception=True):
            logger.warning(
                f"Serializer validation failed for user {user.first_name} {user.last_name}: {serializer.errors}"
            )
            return Response(
                data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST
            )

        biometrics = user_data.get("use_biometrics")

        try:
            if payment_option != "CARD":
                account = AccountCreation.objects.get(user=user)
                logger.info(
                    f"Account found for user {user.first_name} {user.last_name}."
                )
        except AccountCreation.DoesNotExist:
            logger.error(
                f"Account not found for user {user.first_name} {user.last_name}."
            )
            return Response(
                data=encrypt({"status": "fail", "error": "Account not found for user"}),
                status=status.HTTP_404_NOT_FOUND,
            )

        if biometrics:
            verification = Biometrics.authenticate(user.phone_number)
            logger.info(
                f"User {user.first_name} {user.last_name} is using biometrics for authentication."
            )
        elif payment_option == "WALLET":
            if account and account.pin is not None:
                verification = Pin.verify(user=user, pin=pin, hashed_pin=account.pin)
                logger.info(
                    f"User {user.first_name}  {user.last_name} is using PIN for authentication."
                )
            else:
                logger.error(
                    f"Account or PIN not found for user {user.first_name} {user.last_name}."
                )
                return Response(
                    data={
                        "status": "fail",
                        "error": "Account or PIN not found for user",
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )
        else:
            verification = True

        if not verification:
            logger.warning(
                f"Invalid credentials provided for user {user.first_name} {user.last_name}."
            )
            return Response(
                data={"status": "fail", "error": "Invalid credentials"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        electricity_response = None

        if use_bonus:
            logger.info(
                f"User {user.first_name} {user.last_name} is attempting to use bonus for electricity payment."
            )
            if user.welcome_bonus >= float(amount):
                electricity_response = electricity(
                    user=user,
                    serializer=serializer,
                    reason="Debit for electricity bill payment.",
                    user_data=user_data,
                )
                if electricity_response["code"] == "000":
                    response_data = {
                        "status": "success",
                        "message": f"Electricity purchase of {float(amount)} was successful.",
                        "bonus balance": user.welcome_bonus,
                        "electricity_response": electricity_response,
                    }
                    logger.info(
                        f"User {user.first_name} {user.last_name} successfully purchased electricity using bonus."
                    )

                    token = electricity_response.get("purchased_code")
                    send_token(user=user, msg=f"Token purchase was successful. {token}")
                    create_notification(
                        user=request.user,
                        title="Electricity payment",
                        message=f"This is to inform you that your payment of {amount} for electricity is successful.",
                    )
                    create_activity(
                        user=request.user,
                        title="Electricity payment",
                        description=f"{user.first_name} {user.last_name} has made a payment of {amount} for electricity bill.",
                    )
                    return Response(
                        data=encrypt(response_data), status=status.HTTP_200_OK
                    )
                elif electricity_response["code"] == "014":
                    request_id = electricity_response.get("requestId")
                    status_query = VAS.check_status(req_id=request_id)
                    if status_query["content"]["transactions"]["status"] == "delivered":
                        response_data = {
                            "status": "success",
                            "message": f"Request for Electricity purchase of {float(amount)} was successful.",
                            "bonus balance": user.welcome_bonus,
                            "electricity_response": electricity_response,
                        }
                        logger.info(
                            f"User {user.first_name} {user.last_name} successfully purchased electricity using bonus."
                        )
                        create_notification(
                            user=request.user,
                            title="Electricity payment",
                            message=f"This is to inform you that your payment of {amount} for electricity is successful.",
                        )
                        create_activity(
                            user=request.user,
                            title="Electricity payment",
                            description=f"{user.first_name} {user.last_name} has made a payment of {amount} for electricity bill.",
                        )
                        return Response(
                            data=encrypt(response_data), status=status.HTTP_200_OK
                        )
            logger.warning(
                f"Electricity purchase failed for user {user.first_name} {user.last_name} due to insufficient bonus."
            )
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "Electricity purchase failed due to insufficient bonus.",
                        "error": electricity_response,
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        match payment_option:
            case "WALLET":
                logger.info(
                    f"User {user.first_name} {user.last_name} selected WALLET as payment option."
                )
                if use_points:
                    _, pts_amt = Pay.with_pts(user=user, amount=amount)
                    logger.info(
                        f"User {user.first_name} {user.last_name} used points amounting to {pts_amt}."
                    )
                else:
                    pts_amt = 0

                if use_rewards:
                    _, rwd_amt = Pay.with_rwd(user=user, amount=amount)
                    logger.info(
                        f"User {user.first_name} {user.last_name} used rewards amounting to {rwd_amt}."
                    )
                else:
                    rwd_amt = 0

                new_amount = int(amount) - pts_amt - rwd_amt

                user_details = AccountCreation.objects.get(user=user)
                logger.info(
                    f"Initiating debit for user {user.first_name} {user.last_name}. New amount after points and rewards: {new_amount}."
                )

                # Initiate a debit on the customer's account.
                debit_response = Account.Debit(
                    debitAccount=user_details.account_number,
                    amount=new_amount,
                    reason="Debit for electricity bill payment.",
                    transactionReference="",
                )

                if debit_response.status_code == 200:
                    electricity_response = electricity(
                        user=user,
                        serializer=serializer,
                        reason="Debit for electricity bill payment.",
                        user_data=user_data,
                    )
                    if electricity_response["code"] == "000":
                        response_data = {
                            "status": "success",
                            "message": f"Electricity purchase of {new_amount} was successful.",
                            "bonus balance": user.welcome_bonus,
                            "electricity_response": electricity_response,
                        }
                        logger.info(
                            f"User {user.first_name} {user.last_name} successfully purchased electricity with WALLET option."
                        )

                        token = electricity_response.get("purchased_code")
                        send_token(
                            user=user, msg=f"Token purchase was successful. {token}"
                        )

                        create_notification(
                            user=request.user,
                            title="Electricity payment",
                            message=f"This is to inform you that your payment of {new_amount} for electricity is successful.",
                        )
                        create_activity(
                            user=request.user,
                            title="Electricity payment",
                            description=f"{user.first_name} {user.last_name} has made a payment of {new_amount} for electricity bill.",
                        )
                        return Response(
                            data=encrypt(response_data), status=status.HTTP_200_OK
                        )
                    elif electricity_response["code"] == "014":
                        request_id = electricity_response.get("requestId")
                        if request_id:
                            status_query = VAS.check_status(req_id=request_id)
                            if (
                                status_query["content"]["transactions"]["status"]
                                == "delivered"
                            ):
                                response_data = {
                                    "status": "success",
                                    "message": f"Electricity purchase of {new_amount} was successful.",
                                    "bonus balance": user.welcome_bonus,
                                    "electricity_response": electricity_response,
                                }
                            logger.info(
                                f"User {user.first_name} {user.last_name} successfully purchased electricity with WALLET option."
                            )

                            token = electricity_response.get("purchased_code")
                            send_token(
                                user=user, msg=f"Token purchase was successful. {token}"
                            )

                            create_notification(
                                user=request.user,
                                title="Electricity payment",
                                message=f"This is to inform you that your payment of {amount} for electricity is successful.",
                            )
                            create_activity(
                                user=request.user,
                                title="Electricity payment",
                                description=f"{user.first_name} {user.last_name} has made a payment of {amount} for electricity bill.",
                            )
                            return Response(
                                data=encrypt(response_data), status=status.HTTP_200_OK
                            )
                        else:
                            response_data = {
                                "status": "fail",
                                "message": electricity_response["response_description"],
                            }
                            return Response(
                                data=encrypt(response_data),
                                status=status.HTTP_400_BAD_REQUEST,
                            )
                    else:
                        logger.warning(
                            f"Electricity purchase failed for user {user.first_name} {user.last_name}."
                        )
                        return Response(
                            data=encrypt(
                                {
                                    "status": "fail",
                                    "message": electricity_response[
                                        "response_description"
                                    ],
                                }
                            ),
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                else:
                    logger.error(
                        f"Debit failed for user {user.first_name} {user.last_name}: {debit_response.json()}"
                    )
                    return Response(
                        data=encrypt(debit_response.json()),
                        status=debit_response.status_code,
                    )

            case "CARD":
                if user:
                    logger.info(
                        f"User {user.first_name} {user.last_name} selected CARD as payment option."
                    )
                    electricity_response = electricity(
                        user=user,
                        serializer=serializer,
                        reason="Debit for electricity bill payment.",
                        user_data=user_data,
                    )
                    logger.debug(f"response data: {electricity_response}")
                    if electricity_response["code"] == "000":
                        response_data = {
                            "status": "success",
                            "message": f"Electricity purchase of {amount} was successful.",
                            "bonus balance": user.welcome_bonus,
                            "electricity_response": electricity_response,
                        }
                        token = electricity_response.get("purchased_code")
                        logger.info(
                            f"User {user.first_name} {user.last_name} successfully purchased electricity with CARD option."
                        )

                        # Send token to user's email and phone number
                        send_token(
                            user=user,
                            msg=f"Electricity token purchase was successful. {token}",
                        )

                        create_notification(
                            user=request.user,
                            title="Electricity payment",
                            message=f"This is to inform you that your payment of {amount} for electricity is successful.",
                        )
                        create_activity(
                            user=request.user,
                            title="Electricity payment",
                            description=f"{user.first_name} {user.last_name} has made a payment of {amount} for electricity bill.",
                        )

                        return Response(
                            data=encrypt(response_data), status=status.HTTP_200_OK
                        )
                    elif electricity_response["code"] == "014":
                        request_id = electricity_response.get("requestId")
                        if request_id:
                            status_query = VAS.check_status(req_id=request_id)
                            if (
                                status_query["content"]["transactions"]["status"]
                                == "delivered"
                            ):
                                response_data = {
                                    "status": "success",
                                    "message": f"Electricity purchase of {amount} was successful.",
                                    "bonus balance": user.welcome_bonus,
                                    "electricity_response": electricity_response,
                                }
                            logger.info(
                                f"User {user.first_name} {user.last_name} successfully purchased electricity with CARD option."
                            )

                            token = electricity_response.get("purchased_code")
                            send_token(
                                user=user, msg=f"Token purchase was successful. {token}"
                            )

                            create_notification(
                                user=request.user,
                                title="Electricity payment",
                                message=f"This is to inform you that your payment of {amount} for electricity is successful.",
                            )
                            create_activity(
                                user=request.user,
                                title="Electricity payment",
                                description=f"{user.first_name} {user.last_name} has made a payment of {amount} for electricity bill.",
                            )
                            return Response(
                                data=encrypt(response_data), status=status.HTTP_200_OK
                            )
                        else:
                            response_data = {
                                "status": "fail",
                                "message": electricity_response["response_description"],
                            }
                            return Response(
                                data=encrypt(response_data),
                                status=status.HTTP_400_BAD_REQUEST,
                            )
                    else:
                        logger.warning(
                            f"Electricity purchase failed for user {user.first_name} {user.last_name}."
                        )
                        return Response(
                            data=encrypt(
                                {
                                    "status": "fail",
                                    "message": electricity_response["response_description"],
                                }
                            ),
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                else:  # Guest user processing
                    try:
                        electricity_response = electricity(
                            user=None,
                            guest_id=guest_id,
                            serializer=serializer,
                            reason="Guest electricity payment",
                            user_data=user_data
                        )

                        if electricity_response["code"] == "000":
                            token = electricity_response.get("purchased_code")
                            logger.info(f"Guest {guest_id} payment successful")

                            # Send token to guest
                            send_token_to_guest_users(
                                guest_phone=user_data.get("phone"),
                                msg=f"Electricity token: {token}"
                            )

                            create_activity(
                                user=None,
                                guest_id=guest_id,
                                title="Electricity payment",
                                description=f"Guest {guest_id} paid {user_data['amount']} for electricity"
                            )

                            return Response(
                                data=encrypt({
                                    "status": "success",
                                    "message": f"Electricity payment of {user_data['amount']} was successful",
                                    "token": token,
                                    "electricity_response": electricity_response
                                }),
                                status=status.HTTP_200_OK
                            )

                        elif electricity_response["code"] == "014":
                            request_id = electricity_response.get("requestId")
                            if request_id and VAS.check_status(req_id=request_id)["content"]["transactions"]["status"] == "delivered":
                                token = electricity_response.get("purchased_code")
                                send_token_to_guest_users(
                                    guest_phone=user_data.get("phone"),
                                    msg=f"Electricity token: {token}"
                                )

                                create_activity(
                                    user=None,
                                    guest_id=guest_id,
                                    title="Electricity payment",
                                    description=f"Guest {guest_id} paid {user_data['amount']} for electricity"
                                )

                                return Response(
                                    data=encrypt({
                                        "status": "success",
                                        "message": "Electricity payment was successful",
                                        "token": token,
                                        "electricity_response": electricity_response
                                    }),
                                    status=status.HTTP_200_OK
                                )

                        # If payment failed
                        logger.warning(f"Guest {guest_id} payment failed: {electricity_response}")
                        create_activity(
                            user=None,
                            guest_id=guest_id,
                            title="Failed electricity payment",
                            description=f"Guest {guest_id} failed electricity payment"
                        )

                        return Response(
                            data=encrypt({
                                "status": "fail",
                                "message": electricity_response.get("response_description", "Payment failed"),
                                "error": electricity_response
                            }),
                            status=status.HTTP_400_BAD_REQUEST
                        )

                    except Exception as e:
                        logger.error(f"Guest {guest_id} processing error: {str(e)}")
                        return Response(
                            data=encrypt({
                                "status": "error",
                                "message": "Processing error occurred"
                            }),
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR
                        )
            case _:
                logger.warning(
                    f"Invalid payment option selected by user {user.first_name} {user.last_name}."
                )
                return Response(
                    data=encrypt(
                        {"status": "fail", "message": "Invalid payment option"}
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )


class CableServiceIDListView(APIView):
    """
    CableServiceIDListView is the GET request handler that returns a list of cable TV service ids.
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        cableTv_service_ids = [service_id[1] for service_id in TV_SERVICE_ID_CHOICES]
        return Response(
            data=encrypt(
                {
                    "status": "success.",
                    "message": "Electricity service Ids retrieved successfully.",
                    "categories": cableTv_service_ids,
                }
            ),
            status=status.HTTP_200_OK,
        )


class ProductStatus(APIView):
    """
    ProductStatus is the POST request handler for checking the status
    of any Value Added Services product purchased. It takes in the
    request_id of the request and returns the status.
    """

    serializer_class = ProductStatusSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, VasPermission)

    @extend_schema(
        description="Product status",
        responses={200: {"description": "Get product purchase status"}},
    )
    def post(self, request):
        user = self.request.user
        user_data = request.data

        logger.info(
            f"User {user.first_name} {user.last_name} is attempting to requery with request_id: {user_data['request_id']}"
        )

        resource = "requery"
        payload = {
            "request_id": user_data.get("request_id"),
        }

        status_headers = {
            "accept": "application/json",
            "api-key": api_key,
            "secret-key": x_secret,
        }
        try:
            response = requests.get(
                url=vtpass_url + resource, headers=status_headers, json=payload
            )
            logger.info(
                f"API call to {vtpass_url + resource} made by user {user.first_name} {user.last_name}."
            )
            if response.status_code == 200:
                resp = response.json()
                logger.info(
                    f"Successful response received for user {user.first_name} {user.last_name}: {resp}"
                )
                response_data = {
                    "data": resp,
                }
                return Response(data=encrypt(response_data), status=status.HTTP_200_OK)
            else:
                logger.error(
                    f"Failed response for user {user.first_name} {user.last_name}: {response.status_code} - {response.text}"
                )
                return Response(
                    data=encrypt({"error": "Failed to retrieve data"}),
                    status=status.HTTP_400_BAD_REQUEST,
                )
        except requests.exceptions.RequestException as e:
            logger.error(
                f"RequestException for user {user.first_name} {user.last_name}: {str(e)}"
            )
            return Response(
                data=encrypt({"error": str(e)}),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class GetTvVaritaionCodes(generics.RetrieveAPIView):
    """
    GetTvVaritaionCodes is the GET request handler for retrieving
    the variation codes for tv subscription. Take key note of the
    variation codes as they are required to chose a tv plan.
    """

    serializer_class = VasStatusSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, VasPermission)

    @extend_schema(
        description="Variation codes",
        responses={200: {"description": "TV Varitaion Codes"}},
    )
    def get(self, request, *args, **kwargs):
        user = self.request.user  # Get the authenticated user.
        param_value = kwargs.get("service_ID")

        logger.info(
            f"User {user.first_name} {user.last_name} is requesting service variations for service ID: {param_value}"
        )

        if user:
            resource = (
                "https://vtpass.com/api/service-variations?serviceID=" + param_value
            )
            fetch_all_variation_codes_headers = {
                "accept": "application/json",
                "api-key": api_key,
                "secret-key": x_secret,
            }
            try:
                logger.info(
                    f"Sending GET request to {resource} with headers: {fetch_all_variation_codes_headers}"
                )
                response = requests.get(
                    url=resource,
                    headers=fetch_all_variation_codes_headers,
                )
                if response.status_code == 200:
                    resp = response.json().get("content", [])
                    response_data = {
                        "data": resp,
                    }
                    logger.info(
                        f"Successfully fetched service variations for user {user.first_name} {user.last_name}: {resp}"
                    )
                    return Response(
                        data=encrypt(response_data), status=status.HTTP_200_OK
                    )
                else:
                    logger.error(
                        f"Failed to fetch service variations for user {user.first_name} {user.last_name}: {response.json()}"
                    )
                    return Response(
                        data=encrypt(response.json()), status=response.status_code
                    )
            except requests.exceptions.RequestException as e:
                logger.error(
                    f"RequestException occurred for user {user.first_name} {user.last_name}: {str(e)}"
                )
                return Response(
                    data=encrypt({"error": str(e)}),
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
        else:
            logger.warning("User  is not authenticated.")
            return Response(
                data=encrypt({"error": "User  is not authenticated."}),
                status=status.HTTP_401_UNAUTHORIZED,
            )


class VerifySmartCardNumber(generics.GenericAPIView):
    """
    VerifySmartCardNumber is a POST request handler for verifying smart
    card or registration number for tv operators(e.g dstv, gotv).
    """

    serializer_class = VerifyCardNumberSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, VasPermission)

    def get_queryset(self):
        return None

    @extend_schema(
        description="Smart card",
        responses={200: {"description": "Verify smart cards"}},
    )
    def post(self, request):
        decrypted_payload = decrypt(request.data)
        user_data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_payload.items()
        }

        logger.info(f"User   is attempting to verify smart card with data: {user_data}")

        resource = "merchant-verify"
        payload = {
            "serviceID": user_data["serviceID"],
            "billersCode": user_data["billersCode"],
        }

        verify_smart_card_headers = {
            "accept": "application/json",
            "api-key": api_key,
            "secret-key": x_secret,
        }

        try:
            logger.info(
                f"Sending POST request to {vtpass_url + resource} with payload: {payload}"
            )
            response = requests.post(
                url=vtpass_url + resource,
                json=payload,
                headers=verify_smart_card_headers,
            )

            if response.status_code == 200:
                response_data = {
                    "data": response.json(),
                }
                logger.info(f"Smart card verification successful: {response_data}")
                return Response(data=encrypt(response_data), status=status.HTTP_200_OK)
            else:
                logger.warning(f"Smart card verification failed: {response.json()}")
                return Response(
                    data=encrypt(response.json()), status=response.status_code
                )

        except requests.exceptions.RequestException as e:
            logger.error(f"RequestException occurred: {str(e)}")
            return Response(
                data=encrypt({"error": str(e)}),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class NewTvSubscription(generics.GenericAPIView):
    """
    NewTvSubscription is a POST request handler for new
    tv plan subscription.
    """

    serializer_class = TvSubscriptionSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, VasPermission)

    def post(self, request):
        decrypted_payload = decrypt(request.data)
        user_data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_payload.items()
        }
        user = request.user if request.user.is_authenticated else None

        pin = user_data.get("pin")
        guest_id = decrypted_payload.get("guest_id")
        use_points = user_data.get("use_points")
        use_rewards = user_data.get("use_rewards")
        amount = user_data.get("amount")
        payment_option = user_data.get("payment_option")

        if not user:
            if not guest_id:
                return Response(
                    data=encrypt({"status": "fail", "message": "Guest ID required"}),
                    status=status.HTTP_400_BAD_REQUEST
                )

            if payment_option != "CARD":
                return Response(
                    data=encrypt({
                        "status": "fail", 
                        "message": "Guests can only use card payments"
                    }),
                    status=status.HTTP_400_BAD_REQUEST
                )

            logger.info(f"Guest {guest_id} attempting TV subscription")
        else:
            logger.info(
                f"User {user.first_name} {user.last_name} attempting TV subscription"
            )

        serializer = self.serializer_class(data=user_data)
        if not serializer.is_valid(raise_exception=True):
            logger.warning(
                f"Serializer validation failed for user {user.first_name} {user.last_name}: {serializer.errors}"
            )
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        biometrics = user_data.get("use_biometrics")

        try:
            if payment_option != "CARD":
                account = AccountCreation.objects.get(user=user)
                logger.info(
                    f"Account found for user {user.first_name} {user.last_name}."
                )
        except AccountCreation.DoesNotExist:
            logger.error(
                f"Account not found for user {user.first_name} {user.last_name}."
            )
            return Response(
                data=encrypt({"status": "fail", "error": "Account not found for user"}),
                status=status.HTTP_404_NOT_FOUND,
            )

        if biometrics:
            logger.info(
                f"User {user.first_name} {user.last_name} is using biometrics for authentication."
            )
            verification = Biometrics.authenticate(user.phone_number)
        else:
            if account and account.pin is not None:
                logger.info(
                    f"User {user.first_name} {user.last_name} is using PIN for authentication."
                )
                verification = Pin.verify(user=user, pin=pin, hashed_pin=account.pin)
            else:
                logger.error(
                    f"Account or PIN not found for user {user.first_name} {user.last_name}."
                )
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "error": "Account or PIN not found for user",
                        }
                    ),
                    status=status.HTTP_404_NOT_FOUND,
                )

        if not verification:
            logger.warning(
                f"Invalid credentials provided for user {user.first_name} {user.last_name}."
            )
            return Response(
                data={"status": "fail", "error": "Invalid credentials"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        new_tv_response = None

        match payment_option:
            case "WALLET":
                logger.info(
                    f"User {user.first_name} {user.last_name} selected WALLET as payment option."
                )
                if use_points:
                    _, pts_amt = Pay.with_pts(user=user, amount=amount)
                    logger.info(
                        f"User {user.first_name} {user.last_name} used points amounting to {pts_amt}."
                    )
                else:
                    pts_amt = 0

                if use_rewards:
                    _, rwd_amt = Pay.with_rwd(user=user, amount=amount)
                    logger.info(
                        f"User {user.first_name} {user.last_name} used rewards amounting to {rwd_amt}."
                    )
                else:
                    rwd_amt = 0

                new_amount = int(amount) - pts_amt - rwd_amt
                logger.info(
                    f"New amount after applying points and rewards for user {user.first_name} {user.last_name}: {new_amount}"
                )

                user_details = AccountCreation.objects.get(user=user)
                debit_response = Account.Debit(
                    debitAccount=user_details.account_number,
                    amount=new_amount,
                    reason="Debit for TV subscription.",
                    transactionReference="",
                )

                if debit_response.status_code == 200:
                    new_tv_response = NewTvSub(
                        user=user,
                        serializer=serializer,
                        reason="Debit for TV subscription.",
                        user_data=user_data,
                    )
                    if new_tv_response["code"] == "000":
                        response_data = {
                            "status": "success",
                            "message": f"TV subscription purchase of {new_amount} was successful.",
                            "cable_tv_response": new_tv_response,
                        }
                        logger.info(
                            f"User {user.first_name} {user.last_name} successfully purchased TV subscription."
                        )
                        create_notification(
                            user=request.user,
                            title="New TV subscription",
                            message=f"This is to inform you that your payment of {new_amount} for TV subscription is successful.",
                        )
                        create_activity(
                            user=request.user,
                            title="New TV subscription",
                            description=f"{user.first_name} {user.last_name} made a payment of {new_amount} for a new Cable TV subscription.",
                        )
                        return Response(
                            data=encrypt(response_data), status=status.HTTP_200_OK
                        )
                    elif new_tv_response["code"] == "014":
                        request_id = new_tv_response.get("requestId")
                        if request_id:
                            status_query = VAS.check_status(req_id=request_id)
                            if (
                                status_query["content"]["transactions"]["status"]
                                == "delivered"
                            ):
                                response_data = {
                                    "status": "success",
                                    "message": f"TV subscription purchase of {new_amount} was successful.",
                                    "cable_tv_response": new_tv_response,
                                }
                            logger.info(
                                f"User {user.first_name} {user.last_name} successfully purchased TV subscription."
                            )
                            create_notification(
                                user=request.user,
                                title="New TV subscription",
                                message=f"This is to inform you that your payment of {new_amount} for TV subscription is successful.",
                            )
                            create_activity(
                                user=request.user,
                                title="New TV subscription",
                                description=f"{user.first_name} {user.last_name} made a payment of {new_amount} for a new Cable TV subscription.",
                            )
                            return Response(
                                data=encrypt(response_data), status=status.HTTP_200_OK
                            )
                        else:
                            response_data = {
                                "status": "fail",
                                "message": new_tv_response["response_description"],
                            }
                            return Response(
                                data=encrypt(response_data),
                                status=status.HTTP_400_BAD_REQUEST,
                            )
                    else:
                        logger.warning(
                            f"TV subscription purchase failed for user {user.first_name} {user.last_name}."
                        )
                        return Response(
                            data=encrypt(
                                {
                                    "status": "fail",
                                    "message": new_tv_response["response_description"],
                                }
                            ),
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                else:
                    logger.error(
                        f"Debit failed for user {user.first_name} {user.last_name}: {debit_response.json()}"
                    )
                    return Response(
                        data=encrypt(debit_response.json()),
                        status=debit_response.status_code,
                    )

            case "CARD":
                if user:
                    logger.info(
                        f"User {user.first_name} {user.last_name} selected CARD as payment option.")

                    new_tv_response = NewTvSub(
                        user=user,
                        serializer=serializer,
                        reason="Debit for TV subscription.",
                        user_data=user_data,
                    )
                    if new_tv_response["code"] == "000":
                        logger.info(f"Tv response: {new_tv_response}")
                        response_data = {
                            "status": "success",
                            "message": f"TV subscription purchase of {amount} was successful.",
                            "cable_tv_response": new_tv_response,
                        }
                        logger.info(
                            f"User {user.first_name} {user.last_name} successfully purchased TV subscription."
                        )
                        create_notification(
                            user=request.user,
                            title="New TV subscription",
                            message=f"This is to inform you that your payment of {amount} for TV subscription is successful.",
                        )
                        create_activity(
                            user=request.user,
                            title="New TV subscription",
                            description=f"{user.first_name} {user.last_name} made a payment of {amount} for a new Cable TV subscription.",
                        )
                        return Response(
                            data=encrypt(response_data), status=status.HTTP_200_OK
                        )
                    elif new_tv_response["code"] == "014":
                        logger.info(f"Tv response: {new_tv_response}")
                        request_id = new_tv_response.get("requestId")
                        if request_id:
                            status_query = VAS.check_status(req_id=request_id)
                            if (
                                status_query["content"]["transactions"]["status"]
                                == "delivered"
                            ):
                                response_data = {
                                    "status": "success",
                                    "message": f"TV subscription purchase of {new_amount} was successful.",
                                    "cable_tv_response": new_tv_response,
                                }

                            logger.info(
                                f"User {user.first_name} {user.last_name} successfully purchased TV subscription."
                            )
                            create_notification(
                                user=request.user,
                                title="New TV subscription",
                                message=f"This is to inform you that your payment of {amount} for TV subscription is successful.",
                            )
                            create_activity(
                                user=request.user,
                                title="New TV subscription",
                                description=f"{user.first_name} {user.last_name} made a payment of {amount} for a new Cable TV subscription.",
                            )

                            return Response(
                                data=encrypt(response_data), status=status.HTTP_200_OK
                            )
                        else:
                            response_data = {
                                "status": "fail",
                                "cable_tv_response": new_tv_response,
                            }
                            return Response(
                                data=encrypt(response_data),
                                status=status.HTTP_400_BAD_REQUEST,
                            )
                    else:
                        logger.warning(
                            f"TV subscription purchase failed for user {user.first_name} {user.last_name} via CARD."
                        )
                        return Response(
                            data=encrypt(
                                {
                                    "status": "fail",
                                    "message": new_tv_response["response_description"],
                                }
                            ),
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                else:  # Guest user processing
                    try:
                        new_tv_response = NewTvSub(
                            user=None,
                            guest_id=guest_id,
                            serializer=serializer,
                            reason="Guest TV subscription",
                            user_data=user_data
                        )

                        if new_tv_response["code"] == "000":
                            logger.info(f"Guest {guest_id} TV subscription successful")
                            create_activity(
                                user=None,
                                guest_id=guest_id,
                                title="TV subscription",
                                description=f"Guest {guest_id} subscribed to {user_data['amount']} TV plan"
                            )
                            return Response(
                                data=encrypt({
                                    "status": "success",
                                    "message": f"TV subscription of {user_data['amount']} was successful",
                                    "cable_tv_response": new_tv_response
                                }),
                                status=status.HTTP_200_OK
                            )

                        elif new_tv_response["code"] == "014":
                            request_id = new_tv_response.get("requestId")
                            if request_id and VAS.check_status(req_id=request_id)["content"]["transactions"]["status"] == "delivered":
                                logger.info(f"Guest {guest_id} subscription eventually succeeded")
                                create_activity(
                                    user=None,
                                    guest_id=guest_id,
                                    title="TV subscription",
                                    description=f"Guest {guest_id} subscribed to {user_data['amount']} TV plan"
                                )
                                return Response(
                                    data=encrypt({
                                        "status": "success",
                                        "message": "TV subscription was successful",
                                        "cable_tv_response": new_tv_response
                                    }),
                                    status=status.HTTP_200_OK
                                )

                        # If subscription failed
                        logger.warning(f"Guest {guest_id} subscription failed: {new_tv_response}")
                        create_activity(
                            user=None,
                            guest_id=guest_id,
                            title="Failed TV subscription",
                            description=f"Guest {guest_id} failed to subscribe to TV plan"
                        )
                        return Response(
                            data=encrypt({
                                "status": "fail",
                                "message": new_tv_response.get("response_description", "Subscription failed"),
                                "error": new_tv_response
                            }),
                            status=status.HTTP_400_BAD_REQUEST
                        )

                    except Exception as e:
                        logger.error(f"Guest {guest_id} processing error: {str(e)}")
                        return Response(
                            data=encrypt({
                                "status": "error",
                                "message": "Processing error occurred"
                            }),
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR
                        )
            case _:
                logger.error(
                    f"Invalid payment option selected by user {user.first_name} {user.last_name}."
                )
                return Response(
                    data=encrypt(
                        {"status": "fail", "message": "Invalid payment option"}
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )


class RenewTvSubscription(generics.GenericAPIView):
    """
    RenewTvSubscription is a POST request handler for
    tv plan subscription renewal.
    """

    serializer_class = TvSubscriptionSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, VasPermission)

    def post(self, request):
        decrypted_data = decrypt(request.data)
        user_data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_data.items()
        }
        user = request.user if request.user.is_authenticated else None

        pin = user_data.get("pin")
        use_points = user_data.get("use_points")
        use_rewards = user_data.get("use_rewards")
        amount = user_data.get("amount")
        billersCode = user_data.get("billersCode")
        payment_option = user_data.get("payment_option")

        logger.info(
            f"User {user.first_name} {user.last_name} attempting TV subscription renewal"
        )

        serializer = self.serializer_class(data=user_data)
        if not serializer.is_valid(raise_exception=True):
            logger.warning(
                f"Serializer validation failed for user {user.first_name} {user.last_name}: {serializer.errors}"
            )
            return Response(
                data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST
            )

        biometrics = user_data.get("use_biometrics")

        try:
            if payment_option != "CARD":
                account = AccountCreation.objects.get(user=user)
                logger.info(
                    f"Account found for user {user.first_name} {user.last_name}."
                )
        except AccountCreation.DoesNotExist:
            logger.error(
                f"Account not found for user {user.first_name} {user.last_name}."
            )
            return Response(
                data=encrypt({"status": "fail", "error": "Account not found for user"}),
                status=status.HTTP_404_NOT_FOUND,
            )

        if biometrics:
            logger.info(
                f"User {user.first_name} {user.last_name} is using biometrics for authentication."
            )
            verification = Biometrics.authenticate(user.phone_number)
        elif payment_option == "WALLET":
            if account and account.pin is not None:
                logger.info(
                    f"User {user.first_name} {user.last_name} is using PIN for authentication."
                )
                verification = Pin.verify(user=user, pin=pin, hashed_pin=account.pin)
            else:
                logger.error(
                    f"Account or PIN not found for user {user.first_name} {user.last_name}."
                )
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "error": "Account or PIN not found for user",
                        }
                    ),
                    status=status.HTTP_404_NOT_FOUND,
                )
        else:
            verification = True

        if not verification:
            logger.warning(
                f"Invalid credentials provided for user {user.first_name} {user.last_name}."
            )
            return Response(
                data=encrypt({"status": "fail", "error": "Invalid credentials"}),
                status=status.HTTP_401_UNAUTHORIZED,
            )

        renew_tv_response = None
        logger.info(
            f"User {user.first_name} {user.last_name} selected payment option: {payment_option}"
        )

        match payment_option:
            case "WALLET":
                logger.info(
                    f"User {user.first_name} {user.last_name} selected WALLET as payment option."
                )
                if use_points:
                    _, pts_amt = Pay.with_pts(user=user, amount=amount)
                    logger.info(
                        f"User {user.first_name} {user.last_name} used points amounting to {pts_amt}."
                    )
                else:
                    pts_amt = 0

                if use_rewards:
                    _, rwd_amt = Pay.with_rwd(user=user, amount=amount)
                    logger.info(
                        f"User {user.first_name} {user.last_name} used rewards amounting to {rwd_amt}."
                    )
                else:
                    rwd_amt = 0

                new_amount = int(amount) - pts_amt - rwd_amt
                logger.info(
                    f"New amount after applying points and rewards for user {user.first_name} {user.last_name}: {new_amount}"
                )

                user_details = AccountCreation.objects.get(user=user)
                debit_response = Account.Debit(
                    debitAccount=user_details.account_number,
                    amount=new_amount,
                    reason="Debit for TV subscription renewal.",
                    transactionReference="",
                )

                if debit_response.status_code == 200:
                    renew_tv_response = RenewTvSub(
                        user=user,
                        serializer=serializer,
                        reason="Debit for TV subscription renewal.",
                        user_data=user_data,
                    )
                    if renew_tv_response["code"] == "000":
                        response_data = {
                            "status": "success",
                            "message": f"TV subscription purchase of {new_amount} was successful.",
                            "cable_tv_response": renew_tv_response,
                        }
                        logger.info(
                            f"User {user.first_name} {user.last_name} successfully renewed TV subscription."
                        )
                        create_notification(
                            user=request.user,
                            title="Renew Tv subscription",
                            message=f"This is to inform you that your payment of {new_amount} to renew tv subscription is successful.",
                        )
                        create_activity(
                            user=request.user,
                            title="Renew Tv subscription",
                            description=f"{user.first_name} {user.last_name} just made a payment of {new_amount} for Cable TV renewal on {billersCode}.",
                        )
                        return Response(
                            data=encrypt(response_data), status=status.HTTP_200_OK
                        )
                    elif renew_tv_response["code"] == "014":
                        request_id = renew_tv_response.get("requestId")
                        if request_id:
                            status_query = VAS.check_status(req_id=request_id)
                            if (
                                status_query["content"]["transactions"]["status"]
                                == "delivered"
                            ):
                                response_data = {
                                    "status": "success",
                                    "message": f"TV subscription purchase of {new_amount} was successful.",
                                    "cable_tv_response": renew_tv_response,
                                }
                            logger.info(
                                f"User {user.first_name} {user.last_name} successfully renewed TV subscription."
                            )
                            create_notification(
                                user=request.user,
                                title="Renew Tv subscription",
                                message=f"This is to inform you that your payment of {new_amount} to renew tv subscription is successful.",
                            )
                            create_activity(
                                user=request.user,
                                title="Renew Tv subscription",
                                description=f"{user.first_name} {user.last_name} just made a payment of {new_amount} for Cable TV renewal on {billersCode}.",
                            )
                            return Response(
                                data=encrypt(response_data), status=status.HTTP_200_OK
                            )
                        else:
                            response_data = {
                                "status": "fail",
                                "cable_tv_response": renew_tv_response,
                            }
                            return Response(
                                data=encrypt(response_data),
                                status=status.HTTP_400_BAD_REQUEST,
                            )
                    else:
                        logger.warning(
                            f"TV subscription renewal failed for user {user.first_name} {user.last_name}."
                        )
                        return Response(
                            data=encrypt(
                                {
                                    "status": "fail",
                                    "message": renew_tv_response[
                                        "response_description"
                                    ],
                                }
                            ),
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                else:
                    logger.error(
                        f"Debit failed for user {user.first_name} {user.last_name}: {debit_response.json()}"
                    )
                    return Response(
                        data=encrypt(debit_response.json()),
                        status=debit_response.status_code,
                    )

            case "CARD":
                logger.info(
                    f"User {user.first_name} {user.last_name} selected CARD as payment option."
                )
                renew_tv_response = RenewTvSub(
                    user=user,
                    serializer=serializer,
                    reason="Debit for TV subscription renewal.",
                    user_data=user_data,
                )
                if renew_tv_response["code"] == "000":
                    response_data = {
                        "status": "success",
                        "message": f"TV subscription purchase of {amount} was successful.",
                        "cable_tv_response": renew_tv_response,
                    }
                    logger.info(
                        f"User {user.first_name} {user.last_name} successfully renewed TV subscription."
                    )
                    create_notification(
                        user=request.user,
                        title="Renew Tv subscription",
                        message=f"This is to inform you that your payment of {amount} to renew tv subscription is successful.",
                    )
                    create_activity(
                        user=request.user,
                        title="Renew Tv subscription",
                        description=f"{user.first_name} {user.last_name} just made a payment of {amount} for Cable TV renewal on {billersCode}.",
                    )

                    return Response(
                        data=encrypt(response_data), status=status.HTTP_200_OK
                    )
                elif renew_tv_response["code"] == "014":
                    request_id = renew_tv_response.get("requestId")
                    if request_id:
                        status_query = VAS.check_status(req_id=request_id)
                        if (
                            status_query["content"]["transactions"]["status"]
                            == "delivered"
                        ):
                            response_data = {
                                "status": "success",
                                "message": f"TV subscription purchase of {amount} was successful.",
                                "cable_tv_response": renew_tv_response,
                            }
                        logger.info(
                            f"User {user.first_name} {user.last_name} successfully renewed TV subscription."
                        )
                        create_notification(
                            user=request.user,
                            title="Renew Tv subscription",
                            message=f"This is to inform you that your payment of {amount} to renew tv subscription is successful.",
                        )
                        create_activity(
                            user=request.user,
                            title="Renew Tv subscription",
                            description=f"{user.first_name} {user.last_name} just made a payment of {amount} for Cable TV renewal on {billersCode}.",
                        )
                        return Response(
                            data=encrypt(response_data), status=status.HTTP_200_OK
                        )
                    else:
                        response_data = {
                            "status": "fail",
                            "message": renew_tv_response["response_description"],
                        }
                        return Response(
                            data=encrypt(response_data),
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                else:
                    logger.warning(
                        f"TV subscription renewal failed for user {user.first_name} {user.last_name} via CARD."
                    )
                    return Response(
                        data=encrypt(
                            {
                                "status": "fail",
                                "message": renew_tv_response["response_description"],
                            }
                        ),
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            case _:
                logger.error(
                    f"Invalid payment option selected by user {user.first_name} {user.last_name}."
                )
                return Response(
                    data=encrypt(
                        {"status": "fail", "message": "Invalid payment option"}
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )


class GetWaecVaritaionCodes(generics.RetrieveAPIView):
    """
    GetWaecVaritaionCodes is the GET request handler for
    retrieving the variation codes for WAEC registration.
    Take key note of the variation codes as they
    are required to chose a registration plan.
    """

    serializer_class = VasStatusSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, VasPermission)

    @extend_schema(
        description="Variation codes",
        responses={200: {"description": "Waec Varitaion Codes"}},
    )
    def get(self, request):
        user = request.user  # Get the authenticated user.

        if user:
            resource = "service-variations?serviceID=waec-registration"
            waec_variation_codes_headers = {
                "accept": "application/json",
                "api-key": api_key,
                "secret-key": x_secret,
            }

            try:
                response = requests.get(
                    url=vtpass_url + resource,
                    headers=waec_variation_codes_headers,
                )
                if response.status_code == 200:
                    resp = response.json()["content"]
                    response_data = {
                        "data": resp,
                    }
                    return Response(data=response_data, status=status.HTTP_200_OK)
            except requests.exceptions.RequestException as e:
                return Response(
                    {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )


class WaecRegistration(generics.GenericAPIView):
    """
    WaecRegistration is the POST request handler for WAEC
    registration.
    """

    serializer_class = WaecRegistrationSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, VasPermission)

    def post(self, request):
        user_data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in request.data.items()
        }
        user = request.user if request.user.is_authenticated else None

        pin = user_data.get("pin")
        guest_id = user_data.get("guest_id")
        payment_option = request.data.get("payment_option")
        amount = user_data.get("amount")

        serializer = self.serializer_class(data=user_data)
        if not serializer.is_valid(raise_exception=True):
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        biometrics = request.data.get("use_biometrics")

        try:
            account = AccountCreation.objects.get(user=user)
        except AccountCreation.DoesNotExist:
            return Response(
                data={"status": "fail", "error": "Account not found for user"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if biometrics:
            verification = Biometrics.authenticate(user.phone_number)
        else:
            if account and account.pin is not None:
                verification = Pin.verify(user=user, pin=pin, hashed_pin=account.pin)
            else:
                return Response(
                    data={
                        "status": "fail",
                        "error": "Account or PIN not found for user",
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )

        if not verification:
            return Response(
                data={"status": "fail", "error": "Invalid credentials"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        waec_response = None

        payment_option = request.data.get("payment_option")
        match payment_option:
            case "WALLET":
                user_details = AccountCreation.objects.get(user=user)
                debit_response = Account.Debit(
                    debitAccount=user_details.account_number,
                    amount=amount,
                    reason="Debit for waec registration.",
                    transactionReference="",
                )
                if debit_response.status_code == 200:
                    waec_response = waec_reg(
                        user=user,
                        serializer=serializer,
                        reason="Debit for waec registration.",
                        user_data=user_data,
                    )
                    if waec_response["code"] == 200:
                        response_data = {
                            "status": "success",
                            "message": f"Waec registration of {amount} was successful.",
                            "bonus balance": user.welcome_bonus,
                            "waec_response": waec_response,
                        }
                        return Response(data=response_data, status=status.HTTP_200_OK)
                    return Response(
                        data={
                            "status": "fail",
                            "message": "Waec registration failed due to insufficient balance.",
                            "error": waec_response,
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                else:
                    return Response(
                        data=debit_response.json(),
                        status=debit_response.status_code,
                    )
            case "CARD":
                if user:
                    logger.info(
                        f"User {user.first_name} {user.last_name} selected CARD as payment option."
                    )
                elif guest_id:
                    logger.info(
                        f"Guest user with ID {guest_id} selected CARD as payment option."
                    )
                waec_response = waec_reg(
                    user=user,
                    serializer=serializer,
                    reason="Debit for waec registration.",
                    user_data=user_data,
                )
                if waec_response["code"] == 200:
                    response_data = {
                        "status": "success",
                        "message": f"Waec registration of {amount} was successful.",
                        "bonus balance": user.welcome_bonus,
                        "waec_response": waec_response,
                    }
                    return Response(data=response_data, status=status.HTTP_200_OK)
                return Response(
                    data={
                        "status": "fail",
                        "message": "Waec registration failed.",
                        "error": waec_response,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            case _:
                return Response(
                    data={"status": "fail", "message": "Invalid payment option"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
