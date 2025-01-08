import logging
import requests
import threading
from decouple import config
from cloudinary import uploader as cloud

from rest_framework.views import APIView
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.parsers import MultiPartParser, JSONParser

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
    VehicleInsuranceSerializer,
    AccidentInsuranceSerializer,
    HealthInsuranceSerializer,
)
from banking.models import AccountCreation
from banking.controllers import Account
from permissions import VasPermission
from banking.helpers import Pin
from .controllers import (
    airtime,
    data,
    electricity,
    NewTvSub,
    RenewTvSub,
    waec_reg,
    AccidentInsurance,
    VehicleInsurance,
    HealthInsurance,
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
    permission_classes = (IsAuthenticated, VasPermission)

    def post(self, request):
        decrypted_payload = decrypt(request.data)
        user_data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_payload.items()
        }
        user = request.user

        pin = decrypted_payload.get("pin")
        payment_option = decrypted_payload.get("payment_option")
        use_bonus = user_data.get("use_bonus")
        use_points = user_data.get("use_points")
        use_rewards = user_data.get("use_rewards")
        amount = user_data.get("amount")

        logger.info(
            f"User {user.first_name} {user.last_name} is attempting to make a purchase with amount: {amount}, payment option: {payment_option}"
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
                if airtime_response.status_code == 0:
                    response_data = {
                        "status": "success",
                        "message": f"Airtime purchase of {float(amount)} was successful.",
                        "bonus balance": user.welcome_bonus,
                        "airtime_response": airtime_response,
                    }
                    logger.info(
                        f"User {user.first_name} {user.last_name} successfully purchased airtime using bonus."
                    )
                    return Response(
                        data=encrypt(response_data), status=status.HTTP_200_OK
                    )
                elif airtime_response["code"] == 14:
                    request_id = airtime_response["requestId"]
                    status_query = VAS.check_status(req_id=request_id)
                    if status_query["content"]["transactions"]["status"] == "delivered":
                        response_data = {
                            "status": "success",
                            "message": f"Airtime purchase of {amount} was successful.",
                            "bonus balance": user.welcome_bonus,
                            "airtime_response": airtime_response,
                        }
                        logger.info(
                            f"User {user.first_name} {user.last_name} successfully purchased airtime with WALLET option."
                        )
                        return Response(
                            data=encrypt(response_data), status=status.HTTP_200_OK
                        )
            logger.warning(
                f"Airtime top-up failed for user {user.first_name} {user.last_name} due to insufficient bonus."
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
                        reason="Debit for airtime recharge .",
                        user_data=user_data,
                    )
                    if airtime_response["code"] == 0:
                        response_data = {
                            "status": "success",
                            "message": f"Airtime purchase of {new_amount} was successful.",
                            "bonus balance": user.welcome_bonus,
                            "airtime_response": airtime_response,
                        }
                        logger.info(
                            f"User {user.first_name} {user.last_name} successfully purchased airtime with WALLET option."
                        )
                        return Response(
                            data=encrypt(response_data), status=status.HTTP_200_OK
                        )
                    elif airtime_response["code"] == 14:
                        request_id = airtime_response["requestId"]
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
                            return Response(
                                data=encrypt(response_data), status=status.HTTP_200_OK
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
                logger.info(
                    f"User  {user.first_name} {user.last_name} selected CARD as payment option."
                )
                airtime_response = airtime(
                    user=user,
                    serializer=serializer,
                    reason="Debit for airtime recharge.",
                    user_data=user_data,
                )
                if airtime_response["code"] == 0:
                    response_data = {
                        "status": "success",
                        "message": f"Airtime purchase of {amount} was successful.",
                        "bonus balance": user.welcome_bonus,
                        "airtime_response": airtime_response,
                    }
                    logger.info(
                        f"User {user.first_name} {user.last_name} successfully purchased airtime with CARD option."
                    )
                    return Response(
                        data=encrypt(response_data), status=status.HTTP_200_OK
                    )
                elif airtime_response["code"] == 14:
                    request_id = airtime_response["requestId"]
                    status_query = VAS.check_status(req_id=request_id)
                    if status_query["content"]["transactions"]["status"] == "delivered":
                        response_data = {
                            "status": "success",
                            "message": f"Airtime purchase of {new_amount} was successful.",
                            "bonus balance": user.welcome_bonus,
                            "airtime_response": airtime_response,
                        }
                        logger.info(
                            f"User {user.first_name} {user.last_name} successfully purchased airtime with WALLET option."
                        )
                        return Response(
                            data=encrypt(response_data), status=status.HTTP_200_OK
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


class GetNetworkProvidersVaritaionCodes(generics.RetrieveAPIView):
    """
    GetNetworkProvidersVaritaionCodes is a GET request handler for retrieving variation
    codes of different network providers. It takes in the service_ID(mtn, airtel etc)
    as url param.
    """

    serializer_class = VasStatusSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, VasPermission)

    @extend_schema(
        description="Variation codes",
        responses={200: {"description": "Network Providers Varitaion Codes"}},
    )
    def get(self, request, *args, **kwargs):
        user = self.request.user  # Get the authenticated user.

        param_value = kwargs.get("service_ID")
        logger.info(
            f"User {user.first_name} {user.last_name} is requesting service variations for service ID: {param_value}"
        )

        if user:
            resource = f"service-variations?serviceID={param_value}"
            fetch_all_variation_codes_headers = {
                "accept": "application/json",
                "api-key": api_key,
                "secret-key": x_secret,
            }

            try:
                logger.info(
                    f"Making API call to {vtpass_url + resource} for user {user.first_name} {user.last_name}."
                )
                response = requests.get(
                    url=vtpass_url + resource,
                    headers=fetch_all_variation_codes_headers,
                )

                if response.status_code == 200:
                    resp = response.json().get("content", {}).get("variations", [])
                    logger.info(
                        f"Successful response received for user {user.first_name} {user.last_name}: {resp}"
                    )
                    response_data = {
                        "data": resp,
                    }
                    return Response(
                        data=encrypt(response_data), status=status.HTTP_200_OK
                    )
                else:
                    logger.error(
                        f"Failed response for user {user.first_name} {user.last_name}: {response.status_code} - {response.text}"
                    )
                    return Response(
                        data=encrypt(
                            {"error": "Failed to retrieve service variations"}
                        ),
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
        else:
            logger.warning(
                "Unauthenticated user attempted to access service variations."
            )
            return Response(
                data=encrypt({"error": "User  not authenticated"}),
                status=status.HTTP_401_UNAUTHORIZED,
            )


class DataSubscriptionView(generics.GenericAPIView):
    """
    DataSubscriptionView is a POST request handler for data
    subscription.
    """

    serializer_class = DataSubscriptionSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, VasPermission)

    def post(self, request):
        decrypted_payload = decrypt(request.data)
        user_data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_payload.items()
        }
        user = request.user

        pin = user_data.get("pin")
        use_bonus = user_data.get("use_bonus")
        amount = user_data.get("amount")
        use_points = user_data.get("use_points")
        use_rewards = user_data.get("use_rewards")
        payment_option = user_data.get("payment_option")

        logger.info(
            f"User {user.first_name} {user.last_name} is attempting to make a data purchase of amount: {amount}."
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
                logger.debug(f"data_response: {data_response}")
                if data_response["code"] == 0:
                    response_data = {
                        "status": "success",
                        "message": f"Data purchase of {float(amount)} was successful.",
                        "bonus balance": user.welcome_bonus,
                        "data_response": data_response,
                    }
                    logger.info(
                        f"User {user.first_name} {user.last_name} successfully purchased data using bonus."
                    )
                    return Response(
                        data=encrypt(response_data), status=status.HTTP_200_OK
                    )
                elif data_response["code"] == 14:
                    request_id = data_response["requestId"]
                    status_query = VAS.check_status(req_id=request_id)
                    if status_query["content"]["transactions"]["status"] == "delivered":
                        response_data = {
                            "status": "pending",
                            "message": f"Data purchase of {float(amount)} was successful.",
                            "bonus balance": user.welcome_bonus,
                            "data_response": data_response,
                        }
                        logger.info(
                            f"User {user.first_name} {user.last_name} successfully purchased data using bonus."
                        )
                        return Response(
                            data=encrypt(response_data), status=status.HTTP_200_OK
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
                    if data_response["code"] == 0:
                        response_data = {
                            "status": "success",
                            "message": f"Data purchase of {new_amount} was successful.",
                            "bonus balance": user.welcome_bonus,
                            "data_response": data_response,
                        }
                        logger.info(
                            f"User {user.first_name} {user.last_name} successfully purchased data with WALLET payment option."
                        )
                        return Response(
                            data=encrypt(response_data), status=status.HTTP_200_OK
                        )
                    if data_response["code"] == 14:
                        request_id = data_response["requestId"]
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
                        return Response(
                            data=encrypt(response_data), status=status.HTTP_200_OK
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
                logger.info(
                    f"User {user.first_name} {user.last_name} selected CARD as payment option."
                )
                data_response = data(
                    user=user,
                    serializer=serializer,
                    reason="Debit for data subscription.",
                    user_data=user_data,
                )
                if data_response["code"] == 0:
                    response_data = {
                        "status": "success",
                        "message": f"Data purchase of {amount} was successful.",
                        "bonus balance": user.welcome_bonus,
                        "data_response": data_response,
                    }
                    logger.info(
                        f"User {user.first_name} {user.last_name} successfully purchased data with CARD option."
                    )
                    return Response(
                        data=encrypt(response_data), status=status.HTTP_200_OK
                    )
                if data_response["code"] == 14:
                    request_id = data_response["requestId"]
                    status_query = VAS.check_status(req_id=request_id)
                    if status_query["content"]["transactions"]["status"] == "delivered":
                        response_data = {
                            "status": "pending",
                            "message": f"Data purchase of {new_amount} was successful.",
                            "bonus balance": user.welcome_bonus,
                            "data_response": data_response,
                        }
                    logger.info(
                        f"User {user.first_name} {user.last_name} successfully purchased data with WALLET payment option."
                    )
                    return Response(
                        data=encrypt(response_data), status=status.HTTP_200_OK
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
    permission_classes = (IsAuthenticated,)

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
    permission_classes = (IsAuthenticated, VasPermission)

    def post(self, request):
        decrypted_payload = decrypt(request.data)
        user_data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_payload.items()
        }
        user = request.user

        pin = user_data.get("pin")
        use_bonus = user_data.get("use_bonus")
        amount = user_data.get("amount")
        use_points = user_data.get("use_points")
        use_rewards = user_data.get("use_rewards")
        payment_option = user_data.get("payment_option")

        logger.info(
            f"User {user.first_name} {user.last_name} is attempting to make an electricity payment of {amount}."
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
                if electricity_response["code"] == 0:
                    response_data = {
                        "status": "success",
                        "message": f"Electricity purchase of {float(amount)} was successful.",
                        "bonus balance": user.welcome_bonus,
                        "electricity_response": electricity_response,
                    }
                    logger.info(
                        f"User {user.first_name} {user.last_name} successfully purchased electricity using bonus."
                    )
                    return Response(
                        data=encrypt(response_data), status=status.HTTP_200_OK
                    )
                elif electricity_response["code"] == 14:
                    request_id = electricity_response["requestId"]
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
                    if electricity_response["code"] == 0:
                        response_data = {
                            "status": "success",
                            "message": f"Electricity purchase of {new_amount} was successful.",
                            "bonus balance": user.welcome_bonus,
                            "electricity_response": electricity_response,
                        }
                        logger.info(
                            f"User {user.first_name} {user.last_name} successfully purchased electricity with WALLET option."
                        )
                        return Response(
                            data=encrypt(response_data), status=status.HTTP_200_OK
                        )
                    elif electricity_response["code"] == 14:
                        request_id = electricity_response["requestId"]
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
                        return Response(
                            data=encrypt(response_data), status=status.HTTP_200_OK
                        )
                    else:
                        logger.warning(
                            f"Electricity purchase failed for user {user.first_name} {user.last_name}."
                        )
                        return Response(
                            data=encrypt(
                                {
                                    "status": "fail",
                                    "message": "Electricity purchase failed due to insufficient balance.",
                                    "error": electricity_response,
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
                electricity_response = electricity(
                    user=user,
                    serializer=serializer,
                    reason="Debit for electricity bill payment.",
                    user_data=user_data,
                )
                if electricity_response["code"] == 0:
                    response_data = {
                        "status": "success",
                        "message": f"Electricity purchase of {amount} was successful.",
                        "bonus balance": user.welcome_bonus,
                        "electricity_response": electricity_response,
                    }
                    logger.info(
                        f"User {user.first_name} {user.last_name} successfully purchased electricity with CARD option."
                    )
                    return Response(
                        data=encrypt(response_data), status=status.HTTP_200_OK
                    )
                elif electricity_response["code"] == 14:
                    request_id = electricity_response["requestId"]
                    status_query = VAS.check_status(req_id=request_id)
                    if status_query["content"]["transactions"]["status"] == "delivered":
                        response_data = {
                            "status": "success",
                            "message": f"Electricity purchase of {new_amount} was successful.",
                            "bonus balance": user.welcome_bonus,
                            "electricity_response": electricity_response,
                        }
                    logger.info(
                        f"User {user.first_name} {user.last_name} successfully purchased electricity with CARD option."
                    )
                    return Response(
                        data=encrypt(response_data), status=status.HTTP_200_OK
                    )
                else:
                    logger.warning(
                        f"Electricity purchase failed for user {user.first_name} {user.last_name}."
                    )
                    return Response(
                        data=encrypt(
                            {
                                "status": "fail",
                                "message": "Electricity purchase failed.",
                                "error": electricity_response,
                            }
                        ),
                        status=status.HTTP_400_BAD_REQUEST,
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


class ProductStatus(generics.RetrieveAPIView):
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

        logger.info(
            f"User {user.first_name} {user.last_name} is attempting to requery with request_id: {user['request_id']}"
        )

        resource = "requery"
        payload = {
            "request_id": user["request_id"],
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
        user = request.user

        logger.info(
            f"User {user.first_name} {user.last_name} is attempting to make a TV subscription purchase with data: {user_data}"
        )

        pin = user_data.get("pin")
        use_points = user_data.get("use_points")
        use_rewards = user_data.get("use_rewards")
        amount = user_data.get("amount")
        payment_option = user_data.get("payment_option")

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
                    if new_tv_response["code"] == 0:
                        response_data = {
                            "status": "success",
                            "message": f"TV subscription purchase of {new_amount} was successful.",
                            "cable_tv_response": new_tv_response,
                        }
                        logger.info(
                            f"User {user.first_name} {user.last_name} successfully purchased TV subscription."
                        )
                        return Response(
                            data=encrypt(response_data), status=status.HTTP_200_OK
                        )
                    elif new_tv_response["code"] == 14:
                        request_id = new_tv_response["requestId"]
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
                        return Response(
                            data=encrypt(response_data), status=status.HTTP_200_OK
                        )
                    else:
                        logger.warning(
                            f"TV subscription purchase failed for user {user.first_name} {user.last_name}."
                        )
                        return Response(
                            data=encrypt(
                                {
                                    "status": "fail",
                                    "message": "Cable TV subscription purchase failed.",
                                    "error": new_tv_response,
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
                new_tv_response = NewTvSub(
                    user=user,
                    serializer=serializer,
                    reason="Debit for TV subscription.",
                    user_data=user_data,
                )
                if new_tv_response["code"] == 0:
                    response_data = {
                        "status": "success",
                        "message": f"TV subscription purchase of {new_amount} was successful.",
                        "cable_tv_response": new_tv_response,
                    }
                    logger.info(
                        f"User {user.first_name} {user.last_name} successfully purchased TV subscription."
                    )
                    return Response(
                        data=encrypt(response_data), status=status.HTTP_200_OK
                    )
                elif new_tv_response["code"] == 14:
                    request_id = new_tv_response["requestId"]
                    status_query = VAS.check_status(req_id=request_id)
                    if status_query["content"]["transactions"]["status"] == "delivered":
                        response_data = {
                            "status": "success",
                            "message": f"TV subscription purchase of {new_amount} was successful.",
                            "cable_tv_response": new_tv_response,
                        }
                    logger.info(
                        f"User {user.first_name} {user.last_name} successfully purchased TV subscription."
                    )
                    return Response(
                        data=encrypt(response_data), status=status.HTTP_200_OK
                    )
                else:
                    logger.warning(
                        f"TV subscription purchase failed for user {user.first_name} {user.last_name} via CARD."
                    )
                    return Response(
                        data=encrypt(
                            {
                                "status": "fail",
                                "message": "Cable TV subscription purchase failed.",
                                "error": new_tv_response,
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
        user = request.user

        logger.info(
            f"User {user.first_name} {user.last_name} is attempting to renew TV subscription with data: {user_data}"
        )

        pin = user_data.get("pin")
        use_points = user_data.get("use_points")
        use_rewards = user_data.get("use_rewards")
        amount = user_data.get("amount")
        payment_option = user_data.get("payment_option")

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
                    if renew_tv_response["code"] == 0:
                        response_data = {
                            "status": "success",
                            "message": f"TV subscription purchase of {new_amount} was successful.",
                            "cable_tv_response": renew_tv_response,
                        }
                        logger.info(
                            f"User {user.first_name} {user.last_name} successfully renewed TV subscription."
                        )
                        return Response(
                            data=encrypt(response_data), status=status.HTTP_200_OK
                        )
                    elif renew_tv_response["code"] == 14:
                        request_id = renew_tv_response["requestId"]
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
                        return Response(
                            data=encrypt(response_data), status=status.HTTP_200_OK
                        )
                    else:
                        logger.warning(
                            f"TV subscription renewal failed for user {user.first_name} {user.last_name}."
                        )
                        return Response(
                            data=encrypt(
                                {
                                    "status": "fail",
                                    "message": "Cable TV subscription purchase failed.",
                                    "error": renew_tv_response,
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
                if renew_tv_response["code"] == 0:
                    response_data = {
                        "status": "success",
                        "message": f"TV subscription purchase of {new_amount} was successful.",
                        "cable_tv_response": renew_tv_response,
                    }
                    logger.info(
                        f"User {user.first_name} {user.last_name} successfully renewed TV subscription."
                    )
                    return Response(
                        data=encrypt(response_data), status=status.HTTP_200_OK
                    )
                elif renew_tv_response["code"] == 14:
                    request_id = renew_tv_response["requestId"]
                    status_query = VAS.check_status(req_id=request_id)
                    if status_query["content"]["transactions"]["status"] == "delivered":
                        response_data = {
                            "status": "success",
                            "message": f"TV subscription purchase of {new_amount} was successful.",
                            "cable_tv_response": renew_tv_response,
                        }
                    logger.info(
                        f"User {user.first_name} {user.last_name} successfully renewed TV subscription."
                    )
                    return Response(
                        data=encrypt(response_data), status=status.HTTP_200_OK
                    )
                else:
                    logger.warning(
                        f"TV subscription renewal failed for user {user.first_name} {user.last_name} via CARD."
                    )
                    return Response(
                        data=encrypt(
                            {
                                "status": "fail",
                                "message": "Cable TV subscription purchase failed.",
                                "error": renew_tv_response,
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
        user = request.user

        pin = user_data.get("pin")
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


class GetVehicleInsuranceVaritaionCodes(generics.RetrieveAPIView):
    """
    GetVehicleInsuranceVaritaionCodes is the GET request handler for
    retrieving the variation codes for vehicle insurance.
    Take key note of the variation codes as they
    are required to pay for vehicvle insurance.
    """

    serializer_class = VasStatusSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, VasPermission)

    @extend_schema(
        description="Variation codes",
        responses={200: {"description": "Vehicle insurance Varitaion Codes"}},
    )
    def get(self, request):
        user = request.user  # Get the authenticated user.

        if user:
            resource = "service-variations?serviceID=ui-insure"
            vehicle_variation_codes_headers = {
                "accept": "application/json",
                "api-key": api_key,
                "secret-key": x_secret,
            }

            try:
                response = requests.get(
                    url=vtpass_url + resource,
                    headers=vehicle_variation_codes_headers,
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


class GetVehicleInsuranceColorCodes(generics.RetrieveAPIView):
    """
    GetVehicleInsuranceColorCodes is the GET request handler for
    retrieving the color codes for vehicle insurance.
    Take key note of the color codes as they
    are required to pay for vehicle insurance.
    """

    serializer_class = VasStatusSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, VasPermission)

    @extend_schema(
        description="Color codes",
        responses={200: {"description": "Vehicle insurance color Codes"}},
    )
    def get(self, request):
        user = request.user  # Get the authenticated user.

        if user:
            resource = "universal-insurance/options/color"
            vehicle_color_codes_headers = {
                "accept": "application/json",
                "api-key": api_key,
                "secret-key": x_secret,
            }

            try:
                response = requests.get(
                    url=vtpass_url + resource,
                    headers=vehicle_color_codes_headers,
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


class GetVehicleEngineCapacityCodes(generics.RetrieveAPIView):
    """
    GetVehicleEngineCapacityCodes is the GET request handler for
    retrieving the engine capacity codes for vehicle insurance.
    Take key note of the engine capacity codes as they
    are required to pay for vehicle insurance.
    """

    serializer_class = VasStatusSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, VasPermission)

    @extend_schema(
        description="Engine Capacity codes",
        responses={200: {"description": "Vehicle insurance engine capacity Codes"}},
    )
    def get(self, request):
        user = request.user  # Get the authenticated user.

        if user:
            resource = "universal-insurance/options/engine-capacity"
            vehicle_engine_capacity_codes_headers = {
                "accept": "application/json",
                "api-key": api_key,
                "secret-key": x_secret,
            }

            try:
                response = requests.get(
                    url=vtpass_url + resource,
                    headers=vehicle_engine_capacity_codes_headers,
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


class GetVehicleInsuranceStateCodes(generics.RetrieveAPIView):
    """
    GetVehicleInsuranceStateCodes is the GET request handler for
    retrieving the state codes for vehicle insurance.
    Take key note of the state codes as they
    are required to pay for vehicle insurance.
    """

    serializer_class = VasStatusSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, VasPermission)

    @extend_schema(
        description="State codes",
        responses={200: {"description": "Vehicle insurance state Codes"}},
    )
    def get(self, request):
        user = request.user  # Get the authenticated user.

        if user:
            resource = "universal-insurance/options/state"
            vehicle_states_codes_headers = {
                "accept": "application/json",
                "api-key": api_key,
                "secret-key": x_secret,
            }

            try:
                response = requests.get(
                    url=vtpass_url + resource,
                    headers=vehicle_states_codes_headers,
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


class GetVehicleInsuranceAreaCodes(generics.RetrieveAPIView):
    """
    GetVehicleInsuranceAreaCodes is the GET request handler for
    retrieving the area codes for vehicle insurance.
    Take key note of the area codes as they
    are required to pay for vehicle insurance.
    """

    serializer_class = VasStatusSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, VasPermission)

    @extend_schema(
        description="Area codes",
        responses={200: {"description": "Vehicle insurance area Codes"}},
    )
    def get(self, request, *arg, **kwargs):
        user = request.user  # Get the authenticated user.
        state_code = kwargs.get("state_code")

        if user:
            resource = f"universal-insurance/options/lga/{state_code}"
            vehicle_area_codes_headers = {
                "accept": "application/json",
                "api-key": api_key,
                "secret-key": x_secret,
            }

            try:
                response = requests.get(
                    url=vtpass_url + resource,
                    headers=vehicle_area_codes_headers,
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


class GetVehicleInsuranceMakeCodes(generics.RetrieveAPIView):
    """
    GetVehicleInsuranceMakeCodes is the GET request handler for
    retrieving the make codes for vehicle insurance.
    Take key note of the make codes as they
    are required to pay for vehicle insurance.
    """

    serializer_class = VasStatusSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, VasPermission)

    @extend_schema(
        description="Make codes",
        responses={200: {"description": "Vehicle insurance make Codes"}},
    )
    def get(self, request):
        user = request.user  # Get the authenticated user.

        if user:
            resource = "universal-insurance/options/brand"
            vehicle_make_codes_headers = {
                "accept": "application/json",
                "api-key": api_key,
                "secret-key": x_secret,
            }

            try:
                response = requests.get(
                    url=vtpass_url + resource,
                    headers=vehicle_make_codes_headers,
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


class GetVehicleInsuranceModelCodes(generics.RetrieveAPIView):
    """
    GetVehicleInsuranceModelCodes is the GET request handler for
    retrieving the model codes for vehicle insurance.
    Take key note of the model codes as they
    are required to pay for vehicle insurance.
    """

    serializer_class = VasStatusSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, VasPermission)

    @extend_schema(
        description="Make codes",
        responses={200: {"description": "Vehicle insurance model Codes"}},
    )
    def get(self, request, *arg, **kwargs):
        user = request.user  # Get the authenticated user.
        vehicle_make_code = kwargs.get("vehicle_make_code")

        if user:
            resource = f"universal-insurance/options/model/{vehicle_make_code}"
            vehicle_make_codes_headers = {
                "accept": "application/json",
                "api-key": api_key,
                "secret-key": x_secret,
            }

            try:
                response = requests.get(
                    url=vtpass_url + resource,
                    headers=vehicle_make_codes_headers,
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


class VehicleInsuranceView(generics.GenericAPIView):
    """
    VehicleInsuranceView is the POST request handler for creating
    an accident insurance.
    """

    serializer_class = VehicleInsuranceSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, VasPermission)

    def post(self, request):
        user_data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in request.data.items()
        }
        user = request.user

        pin = user_data.get("pin")
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

        vehicle_insurance_response = None

        payment_option = request.data.get("payment_option")
        match payment_option:
            case "WALLET":
                user_details = AccountCreation.objects.get(user=user)
                debit_response = Account.Debit(
                    debitAccount=user_details.account_number,
                    amount=amount,
                    reason="Debit for vehicle insurance.",
                    transactionReference="",
                )

                if debit_response.status_code == 200:
                    vehicle_insurance_response = VehicleInsurance(
                        user=user,
                        serializer=serializer,
                        reason="Debit for vehicle insurance.",
                        user_data=user_data,
                    )
                    if vehicle_insurance_response["code"] == 200:
                        response_data = {
                            "status": "success",
                            "message": f"Vehicle insurance payment of {amount} was successful.",
                            "bonus balance": user.welcome_bonus,
                            "waec_response": vehicle_insurance_response,
                        }
                        return Response(data=response_data, status=status.HTTP_200_OK)
                    return Response(
                        data={
                            "status": "fail",
                            "message": "Waec registration failed due to insufficient balance.",
                            "error": vehicle_insurance_response,
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                else:
                    return Response(
                        data=debit_response.json(),
                        status=debit_response.status_code,
                    )
            case "CARD":
                vehicle_insurance_response = VehicleInsurance(
                    user=user,
                    serializer=serializer,
                    reason="Debit for vehicle insurance.",
                    user_data=user_data,
                )
                if vehicle_insurance_response["code"] == 200:
                    response_data = {
                        "status": "success",
                        "message": f"Vehicle insurance payment of {amount} was successful.",
                        "bonus balance": user.welcome_bonus,
                        "waec_response": vehicle_insurance_response,
                    }
                    return Response(data=response_data, status=status.HTTP_200_OK)
                return Response(
                    data={
                        "status": "fail",
                        "message": "Waec registration failed.",
                        "error": vehicle_insurance_response,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            case _:
                return Response(
                    data={"status": "fail", "message": "Invalid payment option"},
                    status=status.HTTP_400_BAD_REQUEST,
                )


class GetAccidentVaritaionCodes(generics.RetrieveAPIView):
    """
    GetAccidentVaritaionCodes is the GET request handler for retrieving the variation codes for
    accident insurance. Take key note of the variation codes as they
    are required to create an accident insurance.
    """

    serializer_class = VasStatusSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, VasPermission)

    @extend_schema(
        description="Variation codes",
        responses={200: {"description": "Accident Varitaion Codes"}},
    )
    def get(self, request):
        user = request.user  # Get the authenticated user.

        if user:
            resource = "service-variations?serviceID=personal-accident-insurance"
            accident_variation_codes_headers = {
                "accept": "application/json",
                "api-key": api_key,
                "secret-key": x_secret,
            }

            try:
                response = requests.get(
                    url=vtpass_url + resource,
                    headers=accident_variation_codes_headers,
                )
                if response.status_code == 200:
                    resp = response.json()["content"]["variations"]
                    response_data = {
                        "data": resp,
                    }
                    return Response(data=response_data, status=status.HTTP_200_OK)
            except requests.exceptions.RequestException as e:
                return Response(
                    {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )


class AccidentInsuranceView(generics.GenericAPIView):
    """
    AccidentInsuranceView is the POST request handler for creating
    an accident insurance.
    """

    serializer_class = AccidentInsuranceSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, VasPermission)

    def post(self, request):
        user_data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in request.data.items()
        }
        user = request.user

        pin = user_data.get("pin")
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

        accident_response = None

        payment_option = request.data.get("payment_option")
        match payment_option:
            case "WALLET":
                user_details = AccountCreation.objects.get(user=user)
                debit_response = Account.Debit(
                    debitAccount=user_details.account_number,
                    amount=amount,
                    reason="Debit for accident inssurance.",
                    transactionReference="",
                )

                if debit_response.status_code == 200:
                    accident_response = AccidentInsurance(
                        user=user,
                        serializer=serializer,
                        reason="Debit for accident inssurance.",
                        user_data=user_data,
                    )
                    if accident_response["code"] == 200:
                        response_data = {
                            "status": "success",
                            "message": f"Accident Insurance payment of {amount} was successful.",
                            "bonus balance": user.welcome_bonus,
                            "accident_response": accident_response,
                        }
                        return Response(data=response_data, status=status.HTTP_200_OK)
                    return Response(
                        data={
                            "status": "fail",
                            "message": "Accident insurance failed due to insufficient balance.",
                            "error": accident_response,
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                else:
                    return Response(
                        data=debit_response.json(),
                        status=debit_response.status_code,
                    )

            case "CARD":
                accident_response = AccidentInsurance(
                    user=user,
                    serializer=serializer,
                    reason="Debit for accident inssurance.",
                    user_data=user_data,
                )
                if accident_response["code"] == 200:
                    response_data = {
                        "status": "success",
                        "message": f"Accident Insurance payment of {amount} was successful.",
                        "bonus balance": user.welcome_bonus,
                        "accident_response": accident_response,
                    }
                    return Response(data=response_data, status=status.HTTP_200_OK)
                return Response(
                    data={
                        "status": "fail",
                        "message": "Accident insurance failed due to insufficient balance.",
                        "error": accident_response,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            case _:
                return Response(
                    data={"status": "fail", "message": "Invalid payment option"},
                    status=status.HTTP_400_BAD_REQUEST,
                )


class GetHealthInsuranceVaritaionCodes(generics.RetrieveAPIView):
    """
    GetHealthInsuranceVaritaionCodes is a GET request handler for retrieving variation
    codes of different health insurance plans.
    """

    serializer_class = VasStatusSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, VasPermission)

    @extend_schema(
        description="Variation codes",
        responses={200: {"description": "Health insurance Varitaion Codes"}},
    )
    def get(self, request, *args, **kwargs):
        user = self.request.user  # Get the authenticated user.

        if user:
            resource = "service-variations?serviceID=health-insurance-rhl"
            fetch_all_variation_codes_headers = {
                "accept": "application/json",
                "api-key": api_key,
                "secret-key": x_secret,
            }
            try:
                response = requests.get(
                    url=vtpass_url + resource,
                    headers=fetch_all_variation_codes_headers,
                )
                if response.status_code == 200:
                    resp = response.json()["content"]["variations"]
                    response_data = {
                        "data": resp,
                    }
                    return Response(data=response_data, status=status.HTTP_200_OK)
                else:
                    return Response(data=response.json(), status=response.status_code)
            except requests.exceptions.RequestException as e:
                return Response(
                    {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )


class GetHealthInsuranceOptions(generics.RetrieveAPIView):
    """
    GetHealthInsuranceOptions is a GET request handler for retrieving health insurance
    options, in this case lit of supported hospitals.
    """

    serializer_class = VasStatusSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, VasPermission)

    @extend_schema(
        description="Options",
        responses={200: {"description": "Health insurance options"}},
    )
    def get(self, request, *args, **kwargs):
        user = self.request.user  # Get the authenticated user.

        if user:
            resource = "options?serviceID=health-insurance-rhl&name=selected_hospital"
            insurance_options_headers = {
                "accept": "application/json",
                "api-key": api_key,
                "secret-key": x_secret,
            }
            try:
                response = requests.get(
                    url=vtpass_url + resource,
                    headers=insurance_options_headers,
                )
                if response.status_code == 200:
                    resp = response.json()["content"]["options"]
                    response_data = {
                        "data": resp,
                    }
                    return Response(data=response_data, status=status.HTTP_200_OK)
                else:
                    return Response(data=response.json(), status=response.status_code)
            except requests.exceptions.RequestException as e:
                return Response(
                    {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )


class HealthInsuranceView(generics.GenericAPIView):
    """
    HealthInsuranceView is the POST request handler for creating
    a home cover insurance.
    """

    serializer_class = HealthInsuranceSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, VasPermission)
    parser_classes = (MultiPartParser, JSONParser)

    def post(self, request):
        user_data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in request.data.items()
        }
        user = request.user

        pin = user_data.get("pin")
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

        health_response = None

        payment_option = request.data.get("payment_option")
        match payment_option:
            case "WALLET":
                user_details = AccountCreation.objects.get(user=user)
                debit_response = Account.Debit(
                    debitAccount=user_details.account_number,
                    amount=amount,
                    reason="Debit for health insurance.",
                    transactionReference="",
                )

                if debit_response.status_code == 200:
                    health_response = HealthInsurance(
                        self.uploaded_passport_url,
                        user=user,
                        serializer=serializer,
                        user_data=user_data,
                    )
                    # Start a separate thread for image upload
                    thread_upload = threading.Thread(
                        target=self.upload_image,
                        args=(user_data.get("Passport_Photo"),),
                    )
                    thread_upload.start()

                    if health_response["code"] == 200:
                        response_data = {
                            "status": "success",
                            "message": f"Health Insurance payment of {amount} was successful.",
                            "bonus balance": user.welcome_bonus,
                            "health_response": health_response,
                        }
                        return Response(data=response_data, status=status.HTTP_200_OK)
                    return Response(
                        data={
                            "status": "fail",
                            "message": "Health insurance failed due to insufficient balance.",
                            "error": health_response,
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                else:
                    return Response(
                        data=debit_response.json(),
                        status=debit_response.status_code,
                    )

            case "CARD":
                health_response = HealthInsurance(
                    self.uploaded_passport_url,
                    user=user,
                    serializer=serializer,
                    user_data=user_data,
                )
                # Start a separate thread for image upload
                thread_upload = threading.Thread(
                    target=self.upload_image,
                    args=(user_data.get("Passport_Photo"),),
                )
                thread_upload.start()

                if health_response["code"] == 200:
                    response_data = {
                        "status": "success",
                        "message": f"Health Insurance payment of {amount} was successful.",
                        "bonus balance": user.welcome_bonus,
                        "health_response": health_response,
                    }
                    return Response(data=response_data, status=status.HTTP_200_OK)
                return Response(
                    data={
                        "status": "fail",
                        "message": "Health insurance failed due to insufficient balance.",
                        "error": health_response,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            case _:
                return Response(
                    data={"status": "fail", "message": "Invalid payment option"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

    def upload_image(self, image_data):
        passport = cloud.upload(file=image_data)
        self.uploaded_passport_url = passport["url"]
