import requests
from decouple import config

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
    # IntlAirtimeSerializer,
    # WaecRegistrationSerializer,
    # VehicleInsuranceSerializer,
    # AccidentInsuranceSerializer,
    # HomeCoverInsuranceSerializer,
    # HealthInsuranceSerializer,
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
    international_topup,
    waec_reg,
    AccidentInsurance,
    VehicleInsurance,
    HomeCoverInsurance,
    HealthInsurance,
)
from .models import ELECTRICITY_SERVICE_ID_CHOICES, TV_SERVICE_ID_CHOICES
from commons import Pay, Biometrics


vtpass_url = config("VT_PASS_BASE_URL")
x_secret = config("VT_PASS_SECRET_KEY")
api_key = config("VT_PASS_API_KEY")
x_token = config("VT_PASS_PUBLIC_KEY")


class AirTimeTopUp(generics.GenericAPIView):
    """
    AirTimeTopUp is a POST request handler for purchasing airtime for
    service providers in Nigeria.
    """

    serializer_class = AirtimeTopupSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, VasPermission)

    def post(self, request):
        user_data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in request.data.items()
        }
        user = request.user

        pin = request.data.get("pin")
        payment_option = request.data.get("payment_option")
        use_bonus = user_data.get("use_bonus")
        use_points = user_data.get("use_points")
        use_rewards = user_data.get("use_rewards")
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
                    data={"status": "fail", "error": "Account or PIN not found for user"},
                    status=status.HTTP_404_NOT_FOUND,
                )

        if not verification:
            return Response(
                data={"status": "fail", "error": "Invalid credentials"},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        airtime_response = None

        if use_bonus:
            if user.welcome_bonus >= float(amount):
                airtime_response = airtime(
                    user=user,
                    serializer=serializer,
                    reason="Debit for airtime recharge.",
                    user_data=user_data,
                )
                if airtime_response.status_code == 200:
                    response_data = {
                        "status": "success",
                        "message": f"Airtime purchase of {float(amount)} was successful.",
                        "bonus balance": user.welcome_bonus,
                        "airtime_response": airtime_response,
                    }

                return Response(data=response_data, status=status.HTTP_200_OK)
            else:
                return Response(
                    data={
                        "status": "fail",
                        "message": "Airtime top-up failed due to insufficient bonus.",
                        "error": airtime_response,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
        match payment_option:
            case "WALLET":
                if use_points:
                    _, pts_amt = Pay.with_pts(user=user, amount=amount)
                else:
                    pts_amt = 0
                if use_rewards:
                    _, rwd_amt = Pay.with_rwd(user=user, amount=amount)
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
                        reason="Debit for airtime recharge.",
                        user_data=user_data,
                    )
                    if airtime_response["code"] == 200:
                        response_data = {
                            "status": "success",
                            "message": f"Airtime purchase of {new_amount} was successful.",
                            "bonus balance": user.welcome_bonus,
                            "airtime_response": airtime_response,
                        }
                        return Response(data=response_data, status=status.HTTP_200_OK)
                    return Response(
                        data={
                            "status": "fail",
                            "message": "Airtime top-up failed due to insufficient balance.",
                            "error": airtime_response,
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                else:
                    return Response(
                        data=debit_response.json(),
                        status=debit_response.status_code,
                    )
            case "CARD":
                # Implement card payment logic here
                return Response(
                    data={
                        "status": "fail",
                        "message": "Card payment not yet implemented",
                    },
                    status=status.HTTP_501_NOT_IMPLEMENTED,
                )
            case _:
                return Response(
                    data={"status": "fail", "message": "Invalid payment option"},
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

        if user:
            resource = "service-variations?serviceID=" + param_value
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
            except requests.exceptions.RequestException as e:
                return Response(
                    {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
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
        user_data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in request.data.items()
        }
        user = request.user

        pin = request.data.get("pin")
        use_bonus = request.data.get("use_bonus")
        amount = request.data.get("amount")
        use_points = request.data.get("use_points")
        use_rewards = request.data.get("use_rewards")

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
                    data={"status": "fail", "error": "Account or PIN not found for user"},
                    status=status.HTTP_404_NOT_FOUND,
                )

        if not verification:
            return Response(
                data={"status": "fail", "error": "Invalid credentials"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        data_response = None

        payment_option = request.data.get("payment_option")
        if use_bonus:
            if user.welcome_bonus >= float(amount):
                data_response = data(
                    user=user,
                    serializer=serializer,
                    reason="Debit for data subscription.",
                    user_data=user_data,
                )
                if data_response.status_code == 200:
                    response_data = {
                        "status": "success",
                        "message": f"Data purchase of {float(amount)} was successful.",
                        "bonus balance": user.welcome_bonus,
                        "data_response": data_response,
                    }

                return Response(data=response_data, status=status.HTTP_200_OK)
            else:
                return Response(
                    data={
                        "status": "fail",
                        "message": "Data subscription failed due to insufficient bonus.",
                        "error": data_response,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
        match payment_option:
            case "WALLET":
                if use_points:
                    _, pts_amt = Pay.with_pts(user=user, amount=amount)
                else:
                    pts_amt = 0
                if use_rewards:
                    _, rwd_amt = Pay.with_rwd(user=user, amount=amount)
                else:
                    rwd_amt = 0

                new_amount = int(amount) - pts_amt - rwd_amt

                user_details = AccountCreation.objects.get(user=user)
                # Inititate a debit on the customer's account.
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
                    if data_response["code"] == 200:
                        response_data = {
                            "status": "success",
                            "message": f"Data purchase of {new_amount} was successful.",
                            "bonus balance": user.welcome_bonus,
                            "data_response": data_response,
                        }
                        return Response(data=response_data, status=status.HTTP_200_OK)
                    return Response(
                        data={
                            "status": "fail",
                            "message": "Data subscription failed due to insufficient balance.",
                            "error": data_response,
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                else:
                    return Response(
                        data=debit_response.json(),
                        status=debit_response.status_code,
                    )
            case "CARD":
                # Implement card payment logic here
                return Response(
                    data={
                        "status": "fail",
                        "message": "Card payment not yet implemented",
                    },
                    status=status.HTTP_501_NOT_IMPLEMENTED,
                )
            case _:
                return Response(
                    data={"status": "fail", "message": "Invalid payment option"},
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
            data={
                "status": "success.",
                "message": "Electricity service Ids retrieved successfully.",
                "categories": electricity_service_ids,
            },
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
        user_data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in request.data.items()
        }

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
            response = requests.post(
                url=vtpass_url + resource,
                json=payload,
                headers=verify_meter_headers,
            )

            if response.status_code == 200:
                response_data = {
                    "data": response.json(),
                }

                return Response(data=response_data, status=status.HTTP_200_OK)
            else:
                return Response(response.json(), status=response.status_code)

        except requests.exceptions.RequestException as e:
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
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
        user_data = request.data
        user = request.user

        pin = user_data.get("pin")
        use_bonus = user_data.get("use_bonus")
        amount = user_data.get("amount")
        use_points = user_data.get("use_points")
        use_rewards = user_data.get("use_rewards")

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
                    data={"status": "fail", "error": "Account or PIN not found for user"},
                    status=status.HTTP_404_NOT_FOUND,
                )

        if not verification:
            return Response(
                data={"status": "fail", "error": "Invalid credentials"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        electricity_response = None

        payment_option = request.data.get("payment_option")
        if use_bonus:
            if user.welcome_bonus >= float(amount):
                electricity_response = electricity(
                    user=user,
                    serializer=serializer,
                    reason="Debit for electricity bill payment.",
                    user_data=user_data,
                )
                if electricity_response.status_code == 200:
                    response_data = {
                        "status": "success",
                        "message": f"Electricity purchase of {float(amount)} was successful.",
                        "bonus balance": user.welcome_bonus,
                        "electricity_response": electricity_response,
                    }

                    return Response(data=response_data, status=status.HTTP_200_OK)
            else:
                return Response(
                    data={
                        "status": "fail",
                        "message": "Electricity purchase failed due to insufficient bonus.",
                        "error": electricity_response,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
        match payment_option:
            case "WALLET":
                if use_points:
                    _, pts_amt = Pay.with_pts(user=user, amount=amount)
                else:
                    pts_amt = 0
                if use_rewards:
                    _, rwd_amt = Pay.with_rwd(user=user, amount=amount)
                else:
                    rwd_amt = 0

                new_amount = int(amount) - pts_amt - rwd_amt

                user_details = AccountCreation.objects.get(user=user)

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
                    if electricity_response["code"] == 200:
                        response_data = {
                            "status": "success",
                            "message": f"Electricity purchase of {new_amount} was successful.",
                            "bonus balance": user.welcome_bonus,
                            "electricity_response": electricity_response,
                        }
                        return Response(data=response_data, status=status.HTTP_200_OK)
                    return Response(
                        data={
                            "status": "fail",
                            "message": "Electricty purchase failed due to insufficient balance.",
                            "error": electricity_response,
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                else:
                    return Response(
                        data=debit_response.json(),
                        status=debit_response.status_code,
                    )

            case "CARD":
                return Response(
                    data={
                        "status": "fail",
                        "message": "Card payment not yet implemented",
                    },
                    status=status.HTTP_501_NOT_IMPLEMENTED,
                )
            case _:
                return Response(
                    data={"status": "fail", "message": "Invalid payment option"},
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
            data={
                "status": "success.",
                "message": "Electricity service Ids retrieved successfully.",
                "categories": cableTv_service_ids,
            },
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
            if response.status_code == 200:
                resp = response.json()
                response_data = {
                    "data": resp,
                }
                return Response(data=response_data, status=status.HTTP_200_OK)
        except requests.exceptions.RequestException as e:
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
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
                response = requests.get(
                    url=resource,
                    headers=fetch_all_variation_codes_headers,
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
        user = request.data

        resource = "merchant-verify"
        payload = {
            "serviceID": user["serviceID"],
            "billersCode": user["billersCode"],
        }

        verify_smart_card_headers = {
            "accept": "application/json",
            "api-key": api_key,
            "secret-key": x_secret,
        }
        try:
            response = requests.post(
                url=vtpass_url + resource,
                json=payload,
                headers=verify_smart_card_headers,
            )

            if response.status_code == 200:
                response_data = {
                    "data": response.json(),
                }

                return Response(data=response_data, status=status.HTTP_200_OK)
            else:
                return Response(response.json(), status=response.status_code)

        except requests.exceptions.RequestException as e:
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
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
        user_data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in request.data.items()
        }
        user = request.user

        pin = user_data.get("pin")
        use_points = user_data.get("use_points")
        use_rewards = user_data.get("use_rewards")
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
                    data={"status": "fail", "error": "Account or PIN not found for user"},
                    status=status.HTTP_404_NOT_FOUND,
                )

        if not verification:
            return Response(
                data={"status": "fail", "error": "Invalid credentials"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        new_tv_response = None

        payment_option = request.data.get("payment_option")
        match payment_option:
            case "WALLET":
                if use_points:
                    _, pts_amt = Pay.with_pts(user=user, amount=amount)
                else:
                    pts_amt = 0
                if use_rewards:
                    _, rwd_amt = Pay.with_rwd(user=user, amount=amount)
                else:
                    rwd_amt = 0

                new_amount = int(amount) - pts_amt - rwd_amt

                user_details = AccountCreation.objects.get(user=user)
                debit_response = Account.Debit(
                    debitAccount=user_details.account_number,
                    amount=new_amount,
                    reason="Debit for Tv subscription.",
                    transactionReference="",
                )
                if debit_response.status_code == 200:
                    new_tv_response = NewTvSub(
                        user=user,
                        serializer=serializer,
                        reason="Debit for Tv subscription.",
                        user_data=user_data,
                    )
                    if new_tv_response["code"] == 200:
                        response_data = {
                            "status": "success",
                            "message": f"Tv subscription purchase of {new_amount} was successful.",
                            "cable_tv_response": new_tv_response,
                        }
                        return Response(data=response_data, status=status.HTTP_200_OK)
                    return Response(
                        data={
                            "status": "fail",
                            "message": "Cable TV subscription purchase failed due to insufficient balance.",
                            "error": new_tv_response,
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                else:
                    return Response(
                        data=debit_response.json(),
                        status=debit_response.status_code,
                    )

            case "CARD":
                return Response(
                    data={
                        "status": "fail",
                        "message": "Card payment not yet implemented",
                    },
                    status=status.HTTP_501_NOT_IMPLEMENTED,
                )

            case _:
                return Response(
                    data={"status": "fail", "message": "Invalid payment option"},
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
        user_data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in request.data.items()
        }
        user = request.user

        pin = user_data.get("pin")
        use_points = user_data.get("use_points")
        use_rewards = user_data.get("use_rewards")
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
                    data={"status": "fail", "error": "Account or PIN not found for user"},
                    status=status.HTTP_404_NOT_FOUND,
                )

        if not verification:
            return Response(
                data={"status": "fail", "error": "Invalid credentials"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        renew_tv_response = None

        payment_option = request.data.get("payment_option")
        match payment_option:
            case "WALLET":
                if use_points:
                    _, pts_amt = Pay.with_pts(user=user, amount=amount)
                else:
                    pts_amt = 0
                if use_rewards:
                    _, rwd_amt = Pay.with_rwd(user=user, amount=amount)
                else:
                    rwd_amt = 0

                new_amount = int(amount) - pts_amt - rwd_amt

                user_details = AccountCreation.objects.get(user=user)
                debit_response = Account.Debit(
                    debitAccount=user_details.account_number,
                    amount=new_amount,
                    reason="Debit for tv subscription renewal.",
                    transactionReference="",
                )
                if debit_response.status_code == 200:
                    renew_tv_response = RenewTvSub(
                        user=user,
                        serializer=serializer,
                        reason="Debit for tv subscription renewal.",
                        user_data=user_data,
                    )
                    if renew_tv_response["code"] == 200:
                        response_data = {
                            "status": "success",
                            "message": f"Tv subscription purchase of {new_amount} was successful.",
                            "cable_tv_response": renew_tv_response,
                        }
                        return Response(data=response_data, status=status.HTTP_200_OK)
                    return Response(
                        data={
                            "status": "fail",
                            "message": "Cable TV subscription purchase failed due to insufficient balance.",
                            "error": renew_tv_response,
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                else:
                    return Response(
                        data=debit_response.json(),
                        status=debit_response.status_code,
                    )

            case "CARD":
                return Response(
                    data={
                        "status": "fail",
                        "message": "Card payment not yet implemented",
                    },
                    status=status.HTTP_501_NOT_IMPLEMENTED,
                )

            case _:
                return Response(
                    data={"status": "fail", "message": "Invalid payment option"},
                    status=status.HTTP_400_BAD_REQUEST,
                )


# class GetIntlAirtimeCountryCodes(generics.GenericAPIView):
#     """
#     GetIntlAirtimeCountryCodes is a GET request handler for retrieving
#     available counntry codes for airtime services for worldwide.
#     Take note of the country codes as it would be required to
#     get airtime products available in that country.
#     """

#     serializer_class = VasStatusSerializer
#     authentication_classes = [JWTAuthentication]
#     permission_classes = (IsAuthenticated, VasPermission)

#     @extend_schema(
#         description="Variation codes",
#         responses={200: {"description": "Get international airtime country codes"}},
#     )
#     def get(self, request):
#         resource = "get-international-airtime-countries"
#         get_intl_codes_headers = {
#             "accept": "application/json",
#             "api-key": api_key,
#             "secret-key": x_secret,
#         }

#         try:
#             response = requests.get(
#                 url=vtpass_url + resource,
#                 headers=get_intl_codes_headers,
#             )
#             if response.status_code == 200:
#                 resp = response.json()["content"]["countries"]
#                 for _ in range(len(resp)):
#                     response_data = {
#                         "data": resp,
#                     }
#                     return Response(data=response_data, status=status.HTTP_200_OK)
#         except requests.exceptions.RequestException as e:
#             return Response(
#                 {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
#             )


# class GetIntlAirtimeProducts(generics.GenericAPIView):
#     """
#     GetIntlAirtimeProducts is a GET request handler for retrieving
#     airtime products available in the country. The endpoints takes
#     the country_code as url params.
#     """

#     serializer_class = VasStatusSerializer
#     authentication_classes = [JWTAuthentication]
#     permission_classes = (IsAuthenticated, VasPermission)

#     @extend_schema(
#         description="International airtime products",
#         responses={200: {"description": "Get International airtime products"}},
#     )
#     def get(self, request, *args, **kwargs):
#         param_value = kwargs.get("country_code")

#         resource = "get-international-airtime-product-types?code=" + param_value
#         prod_types_headers = {
#             "accept": "application/json",
#             "api-key": api_key,
#             "secret-key": x_secret,
#         }

#         try:
#             response = requests.get(
#                 url=vtpass_url + resource,
#                 headers=prod_types_headers,
#             )
#             if response.status_code == 200:
#                 resp = response.json()["content"]
#                 response_data = {
#                     "data": resp,
#                 }
#                 return Response(data=response_data, status=status.HTTP_200_OK)
#         except requests.exceptions.RequestException as e:
#             return Response(
#                 {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
#             )


# class GetIntlAirtimeOperators(generics.GenericAPIView):
#     """
#     GetIntlAirtimeOperators is a GET request handler for retrieving
#     airtime operators available in the country. The endpoints takes
#     the country_code aas well as product type id as url params.
#     Take note of the operator_id and it will be required to get
#     the variation codes.
#     """

#     serializer_class = VasStatusSerializer
#     authentication_classes = [JWTAuthentication]
#     permission_classes = (IsAuthenticated, VasPermission)

#     @extend_schema(
#         description="Airtime operators.",
#         responses={200: {"description": "Get international airtime operators"}},
#     )
#     def get(self, request, *args, **kwargs):
#         code = kwargs.get("country_code")
#         product_type = kwargs.get("product_type_id")

#         prefix = "get-international-airtime-operators?code="
#         resource = prefix + code + "&product_type_id=" + product_type
#         code_and_prod_headers = {
#             "accept": "application/json",
#             "api-key": api_key,
#             "secret-key": x_secret,
#         }

#         try:
#             response = requests.get(
#                 url=vtpass_url + resource,
#                 headers=code_and_prod_headers,
#             )
#             if response.status_code == 200:
#                 resp = response.json()["content"]
#                 response_data = {
#                     "data": resp,
#                 }
#                 return Response(data=response_data, status=status.HTTP_200_OK)
#         except requests.exceptions.RequestException as e:
#             return Response(
#                 {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
#             )


# class GetIntlAirtimeVaraitionCodes(generics.GenericAPIView):
#     """
#     GetIntlAirtimeVaraitionCodes is the GET request handler for retrieving
#     the variation codes for international airrtime topup.
#     Take key note of the variation codes as they
#     are required to chose a registration plan.
#     The endpoints takes the operator_id as well as product type id
#     as url params.
#     """

#     serializer_class = VasStatusSerializer
#     authentication_classes = [JWTAuthentication]
#     permission_classes = (IsAuthenticated, VasPermission)

#     @extend_schema(
#         description="Variation codes",
#         responses={200: {"description": "International airtime Varitaion Codes"}},
#     )
#     def get(self, request, *args, **kwargs):
#         ops_id = kwargs.get("operator_id")
#         product_type = kwargs.get("product_type_id")

#         prefix = "service-variations?serviceID=foreign-airtime&operator_id="
#         resource = prefix + ops_id + "&product_type_id=" + product_type
#         code_and_prod_headers = {
#             "accept": "application/json",
#             "api-key": api_key,
#             "secret-key": x_secret,
#         }

#         try:
#             response = requests.get(
#                 url=vtpass_url + resource,
#                 headers=code_and_prod_headers,
#             )
#             if response.status_code == 200:
#                 resp = response.json()["content"]["variations"]
#                 for _ in range(len(resp)):
#                     response_data = {
#                         "data": resp,
#                     }
#                     return Response(data=response_data, status=status.HTTP_200_OK)
#         except requests.exceptions.RequestException as e:
#             return Response(
#                 {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
#             )


# class InternationalAirTimeTopUp(generics.GenericAPIView):
#     """
#     InternationalAirTimeTopUp is the POST request handler for
#     international airtime topup.
#     """

#     serializer_class = IntlAirtimeSerializer
#     authentication_classes = [JWTAuthentication]
#     permission_classes = (IsAuthenticated, VasPermission)

#     def post(self, request):
#         user_data = {
#             key: value.strip() if isinstance(value, str) else value
#             for key, value in request.data.items()
#         }
#         user = request.user
#         use_points = user_data.get("use_points")
#         use_rewards = user_data.get("use_rewards")
#         amount = user_data.get("amount")

#         pin = request.data.get("pin")
#         account = AccountCreation.objects.get(user=user)
#         verification = Pin.verify(user=user, pin=pin, hashed_pin=account.pin)
#         if verification:
#             payment_option = request.data.get("payment_option")
#             match payment_option:
#                 case "WALLET":
#                     if use_points:
#                         _, pts_amt = Pay.with_pts(user=user, amount=amount)
#                     else:
#                         pts_amt = 0
#                     if use_rewards:
#                         _, rwd_amt = Pay.with_rwd(user=user, amount=amount)
#                     else:
#                         rwd_amt = 0

#                     new_amount = amount - pts_amt - rwd_amt

#                     user_details = AccountCreation.objects.get(user=user)
#                     debit_response = Account.Debit(
#                         debitAccount=user_details.account_number,
#                         amount=new_amount,
#                         reason="Debit for international airtime recharge.",
#                         transactionReference="",
#                     )
#                     if debit_response == 200:
#                         serializer = self.serializer_class(data=user_data)
#                         if serializer.is_valid(raise_exception=True):
#                             international_topup(
#                                 user=user,
#                                 serializer=serializer,
#                                 reason="Debit for international airtime recharge.",
#                                 user_data=user_data,
#                             )
#                         else:
#                             return Response(
#                                 data=serializer.errors,
#                                 status=status.HTTP_400_BAD_REQUEST,
#                             )
#                     else:
#                         credit_response = Account.Credit(
#                             acct_no=user_details.account_number,
#                             amount=new_amount,
#                             transactionReference="",
#                             reason="Refund for failed international aitime topup.",
#                         )
#                         if credit_response == 200:
#                             logging.info(
#                                 f"Account credit successful for account {user_details.account_number}. Amount: {new_amount}"
#                             )
#                         else:
#                             logging.error(
#                                 f"Account credit failed for account {user_details.account_number}. Status code: {credit_response}"
#                             )
#                         return Response(
#                             data=debit_response.json(),
#                             status=debit_response.status_code,
#                         )
#                 case "CARD":
#                     pass


# class GetWaecVaritaionCodes(generics.RetrieveAPIView):
#     """
#     GetWaecVaritaionCodes is the GET request handler for
#     retrieving the variation codes for WAEC registration.
#     Take key note of the variation codes as they
#     are required to chose a registration plan.
#     """

#     serializer_class = VasStatusSerializer
#     authentication_classes = [JWTAuthentication]
#     permission_classes = (IsAuthenticated, VasPermission)

#     @extend_schema(
#         description="Variation codes",
#         responses={200: {"description": "Waec Varitaion Codes"}},
#     )
#     def get(self, request):
#         user = request.user  # Get the authenticated user.

#         if user:
#             resource = "service-variations?serviceID=waec-registration"
#             waec_variation_codes_headers = {
#                 "accept": "application/json",
#                 "api-key": api_key,
#                 "secret-key": x_secret,
#             }

#             try:
#                 response = requests.get(
#                     url=vtpass_url + resource,
#                     headers=waec_variation_codes_headers,
#                 )
#                 if response.status_code == 200:
#                     resp = response.json()["content"]
#                     response_data = {
#                         "data": resp,
#                     }
#                     return Response(data=response_data, status=status.HTTP_200_OK)
#             except requests.exceptions.RequestException as e:
#                 return Response(
#                     {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
#                 )


# class WaecRegistration(generics.GenericAPIView):
#     """
#     WaecRegistration is the POST request handler for WAEC
#     registration.
#     """

#     serializer_class = WaecRegistrationSerializer
#     authentication_classes = [JWTAuthentication]
#     permission_classes = (IsAuthenticated, VasPermission)

#     def post(self, request):
#         user_data = {
#             key: value.strip() if isinstance(value, str) else value
#             for key, value in request.data.items()
#         }
#         user = request.user

#         pin = user_data.get("pin")
#         use_points = user_data.get("use_points")
#         use_rewards = user_data.get("use_rewards")
#         amount = user_data.get("amount")

#         account = AccountCreation.objects.get(user=user)
#         verification = Pin.verify(user=user, pin=pin, hashed_pin=account.pin)
#         if verification:
#             payment_option = request.data.get("payment_option")
#             match payment_option:
#                 case "WALLET":
#                     if use_points:
#                         _, pts_amt = Pay.with_pts(user=user, amount=amount)
#                     else:
#                         pts_amt = 0
#                     if use_rewards:
#                         _, rwd_amt = Pay.with_rwd(user=user, amount=amount)
#                     else:
#                         rwd_amt = 0

#                     new_amount = amount - pts_amt - rwd_amt

#                     user_details = AccountCreation.objects.get(user=user)
#                     debit_response = Account.Debit(
#                         debitAccount=user_details.account_number,
#                         amount=new_amount,
#                         reason="Debit for waec registration.",
#                         transactionReference="",
#                     )
#                     if debit_response == 200:
#                         serializer = self.serializer_class(data=user_data)
#                         if serializer.is_valid(raise_exception=True):
#                             waec_reg(
#                                 user=user,
#                                 serializer=serializer,
#                                 reason="Debit for waec registration.",
#                                 user_data=user_data,
#                             )
#                         else:
#                             return Response(
#                                 data=serializer.errors,
#                                 status=status.HTTP_400_BAD_REQUEST,
#                             )
#                     else:
#                         credit_response = Account.Credit(
#                             acct_no=user_details.account_number,
#                             amount=new_amount,
#                             transactionReference="",
#                             reason="Refund for failed waec registration.",
#                         )
#                         if credit_response == 200:
#                             logging.info(
#                                 f"Account credit successful for account {user_details.account_number}. Amount: {new_amount}"
#                             )
#                         else:
#                             logging.error(
#                                 f"Account credit failed for account {user_details.account_number}. Status code: {credit_response}"
#                             )
#                         return Response(
#                             data=debit_response.json(),
#                             status=debit_response.status_code,
#                         )
#                 case "CARD":
#                     pass


# class GetVehicleInsuranceVaritaionCodes(generics.RetrieveAPIView):
#     """
#     GetVehicleInsuranceVaritaionCodes is the GET request handler for
#     retrieving the variation codes for vehicle insurance.
#     Take key note of the variation codes as they
#     are required to create an accident insurance.
#     """

#     serializer_class = VasStatusSerializer
#     authentication_classes = [JWTAuthentication]
#     permission_classes = (IsAuthenticated, VasPermission)

#     @extend_schema(
#         description="Variation codes",
#         responses={200: {"description": "Vehicle insurance Varitaion Codes"}},
#     )
#     def get(self, request):
#         user = request.user  # Get the authenticated user.

#         if user:
#             resource = "service-variations?serviceID=ui-insure"
#             wae_variation_codes_headers = {
#                 "accept": "application/json",
#                 "api-key": api_key,
#                 "secret-key": x_secret,
#             }

#             try:
#                 response = requests.get(
#                     url=vtpass_url + resource,
#                     headers=wae_variation_codes_headers,
#                 )
#                 if response.status_code == 200:
#                     resp = response.json()["content"]
#                     response_data = {
#                         "data": resp,
#                     }
#                     return Response(data=response_data, status=status.HTTP_200_OK)
#             except requests.exceptions.RequestException as e:
#                 return Response(
#                     {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
#                 )


# class VehicleInsuranceView(generics.GenericAPIView):
#     """
#     VehicleInsuranceView is the POST request handler for creating
#     an accident insurance.
#     """

#     serializer_class = VehicleInsuranceSerializer
#     authentication_classes = [JWTAuthentication]
#     permission_classes = (IsAuthenticated, VasPermission)

#     def post(self, request):
#         user_data = {
#             key: value.strip() if isinstance(value, str) else value
#             for key, value in request.data.items()
#         }
#         user = request.user

#         pin = user_data.get("pin")
#         use_points = user_data.get("use_points")
#         use_rewards = user_data.get("use_rewards")
#         amount = user_data.get("amount")

#         account = AccountCreation.objects.get(user=user)
#         verification = Pin.verify(user=user, pin=pin, hashed_pin=account.pin)
#         if verification:
#             payment_option = request.data.get("payment_option")
#             match payment_option:
#                 case "WALLET":
#                     if use_points:
#                         _, pts_amt = Pay.with_pts(user=user, amount=amount)
#                     else:
#                         pts_amt = 0
#                     if use_rewards:
#                         _, rwd_amt = Pay.with_rwd(user=user, amount=amount)
#                     else:
#                         rwd_amt = 0

#                     new_amount = amount - pts_amt - rwd_amt

#                     user_details = AccountCreation.objects.get(user=user)
#                     debit_response = Account.Debit(
#                         debitAccount=user_details.account_number,
#                         amount=new_amount,
#                         reason="Debit for vehicle insurance.",
#                         transactionReference="",
#                     )

#                     if debit_response.status_code == 200:
#                         serializer = self.serializer_class(data=user_data)
#                         if serializer.is_valid(raise_exception=True):
#                             VehicleInsurance(
#                                 user=user,
#                                 serializer=serializer,
#                                 reason="Debit for vehicle insurance.",
#                                 user_data=user_data,
#                             )
#                         else:
#                             return Response(
#                                 data=serializer.errors,
#                                 status=status.HTTP_400_BAD_REQUEST,
#                             )
#                     else:
#                         credit_response = Account.Credit(
#                             acct_no=user_details.account_number,
#                             amount=new_amount,
#                             transactionReference="",
#                             reason="Refund for failed vehicle insurance.",
#                         )
#                         if credit_response == 200:
#                             logging.info(
#                                 f"Account credit successful for account {user_details.account_number}. Amount: {new_amount}"
#                             )
#                         else:
#                             logging.error(
#                                 f"Account credit failed for account {user_details.account_number}. Status code: {credit_response}"
#                             )
#                         return Response(
#                             data=debit_response.json(),
#                             status=debit_response.status_code,
#                         )
#                 case "CARD":
#                     pass


# class GetAccidentVaritaionCodes(generics.RetrieveAPIView):
#     """
#     GetAccidentVaritaionCodes is the GET request handler for retrieving the variation codes for
#     accident insurance. Take key note of the variation codes as they
#     are required to create an accident insurance.
#     """

#     serializer_class = VasStatusSerializer
#     authentication_classes = [JWTAuthentication]
#     permission_classes = (IsAuthenticated, VasPermission)

#     @extend_schema(
#         description="Variation codes",
#         responses={200: {"description": "Accident Varitaion Codes"}},
#     )
#     def get(self, request):
#         user = request.user  # Get the authenticated user.

#         if user:
#             resource = "service-variations?serviceID=personal-accident-insurance"
#             accident_variation_codes_headers = {
#                 "accept": "application/json",
#                 "api-key": api_key,
#                 "secret-key": x_secret,
#             }

#             try:
#                 response = requests.get(
#                     url=vtpass_url + resource,
#                     headers=accident_variation_codes_headers,
#                 )
#                 if response.status_code == 200:
#                     resp = response.json()["content"]["variations"]
#                     response_data = {
#                         "data": resp,
#                     }
#                     return Response(data=response_data, status=status.HTTP_200_OK)
#             except requests.exceptions.RequestException as e:
#                 return Response(
#                     {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
#                 )


# class AccidentInsuranceView(generics.GenericAPIView):
#     """
#     AccidentInsuranceView is the POST request handler for creating
#     an accident insurance.
#     """

#     serializer_class = AccidentInsuranceSerializer
#     authentication_classes = [JWTAuthentication]
#     permission_classes = (IsAuthenticated, VasPermission)

#     def post(self, request):
#         user_data = {
#             key: value.strip() if isinstance(value, str) else value
#             for key, value in request.data.items()
#         }
#         user = request.user

#         pin = user_data.get("pin")
#         use_points = user_data.get("use_points")
#         use_rewards = user_data.get("use_rewards")
#         amount = user_data.get("amount")

#         account = AccountCreation.objects.get(user=user)
#         verification = Pin.verify(user=user, pin=pin, hashed_pin=account.pin)
#         if verification:
#             payment_option = request.data.get("payment_option")
#             match payment_option:
#                 case "WALLET":
#                     if use_points:
#                         _, pts_amt = Pay.with_pts(user=user, amount=amount)
#                     else:
#                         pts_amt = 0
#                     if use_rewards:
#                         _, rwd_amt = Pay.with_rwd(user=user, amount=amount)
#                     else:
#                         rwd_amt = 0

#                     new_amount = amount - pts_amt - rwd_amt

#                     user_details = AccountCreation.objects.get(user=user)
#                     debit_response = Account.Debit(
#                         debitAccount=user_details.account_number,
#                         amount=new_amount,
#                         reason="Debit for accident inssurance.",
#                         transactionReference="",
#                     )

#                     if debit_response.status_code == 200:
#                         serializer = self.serializer_class(data=user)
#                         if serializer.is_valid(raise_exception=True):
#                             AccidentInsurance(
#                                 user=user,
#                                 serializer=serializer,
#                                 reason="Debit for accident inssurance.",
#                                 user_data=user_data,
#                             )
#                         else:
#                             return Response(
#                                 data=serializer.errors,
#                                 status=status.HTTP_400_BAD_REQUEST,
#                             )
#                     else:
#                         credit_response = Account.Credit(
#                             acct_no=user_details.account_number,
#                             amount=new_amount,
#                             transactionReference="",
#                             reason="Refund for failed accident insurance.",
#                         )
#                         if credit_response == 200:
#                             logging.info(
#                                 f"Account credit successful for account {user_details.account_number}. Amount: {new_amount}"
#                             )
#                         else:
#                             logging.error(
#                                 f"Account credit failed for account {user_details.account_number}. Status code: {credit_response}"
#                             )
#                         return Response(
#                             data=debit_response.json(),
#                             status=debit_response.status_code,
#                         )

#                 case "CARD":
#                     pass


# class GetHomeCoverVaritaionCodes(generics.RetrieveAPIView):
#     """
#     GetHomeCoverVaritaionCodes is the GET request handler for
#     retrieving the variation codes fora home cover insurance.
#     Take key note of the variation codes as they
#     are required to create a home cover insurance.
#     """

#     serializer_class = VasStatusSerializer
#     authentication_classes = [JWTAuthentication]
#     permission_classes = (IsAuthenticated, VasPermission)

#     @extend_schema(
#         description="Variation codes",
#         responses={200: {"description": "Home Cover Varitaion Codes"}},
#     )
#     def get(self, request):
#         user = request.user  # Get the authenticated user.

#         if user:
#             resource = "service-variations?serviceID=home-cover-insurance"
#             home_cover_variation_codes_headers = {
#                 "accept": "application/json",
#                 "api-key": api_key,
#                 "secret-key": x_secret,
#             }

#             try:
#                 response = requests.get(
#                     url=vtpass_url + resource,
#                     headers=home_cover_variation_codes_headers,
#                 )
#                 if response.status_code == 200:
#                     resp = response.json()["content"]["variations"]
#                     response_data = {
#                         "data": resp,
#                     }
#                     return Response(data=response_data, status=status.HTTP_200_OK)
#             except requests.exceptions.RequestException as e:
#                 return Response(
#                     {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
#                 )


# class HomeCoverInsuranceView(generics.GenericAPIView):
#     """
#     HomeCoverInsuranceView is the POST request handler for creating
#     a home cover insurance.
#     """

#     serializer_class = HomeCoverInsuranceSerializer
#     authentication_classes = [JWTAuthentication]
#     permission_classes = (IsAuthenticated, VasPermission)

#     def post(self, request):
#         user_data = {
#             key: value.strip() if isinstance(value, str) else value
#             for key, value in request.data.items()
#         }
#         user = request.user

#         pin = user_data.get("pin")
#         use_points = user_data.get("use_points")
#         use_rewards = user_data.get("use_rewards")
#         amount = user_data.get("amount")

#         account = AccountCreation.objects.get(user=user)
#         verification = Pin.verify(user=user, pin=pin, hashed_pin=account.pin)
#         if verification:
#             payment_option = request.data.get("payment_option")
#             match payment_option:
#                 case "WALLET":
#                     if use_points:
#                         _, pts_amt = Pay.with_pts(user=user, amount=amount)
#                     else:
#                         pts_amt = 0
#                     if use_rewards:
#                         _, rwd_amt = Pay.with_rwd(user=user, amount=amount)
#                     else:
#                         rwd_amt = 0

#                     new_amount = amount - pts_amt - rwd_amt

#                     user_details = AccountCreation.objects.get(user=user)
#                     debit_response = Account.Debit(
#                         debitAccount=user_details.account_number,
#                         amount=new_amount,
#                         reason="Debit for home cover insurance registration.",
#                         transactionReference="",
#                     )

#                     if debit_response.status_code == 200:
#                         serializer = self.serializer_class(data=user)
#                         if serializer.is_valid(raise_exception=True):
#                             HomeCoverInsurance(
#                                 user=user,
#                                 serializer=serializer,
#                                 reason="Debit for home cover insurance registration.",
#                                 user_data=user_data,
#                             )
#                         else:
#                             return Response(
#                                 data=serializer.errors,
#                                 status=status.HTTP_400_BAD_REQUEST,
#                             )
#                     else:
#                         credit_response = Account.Credit(
#                             acct_no=user_details.account_number,
#                             amount=new_amount,
#                             transactionReference="",
#                             reason="Refund for failed home cover insurance.",
#                         )
#                         if credit_response == 200:
#                             logging.info(
#                                 f"Account credit successful for account {user_details.account_number}. Amount: {new_amount}"
#                             )
#                         else:
#                             logging.error(
#                                 f"Account credit failed for account {user_details.account_number}. Status code: {credit_response}"
#                             )
#                         return Response(
#                             data=debit_response.json(),
#                             status=debit_response.status_code,
#                         )
#                 case "CARD":
#                     pass


# class GetHealthInsuranceVaritaionCodes(generics.RetrieveAPIView):
#     """
#     GetHealthInsuranceVaritaionCodes is a GET request handler for retrieving variation
#     codes of different health insurance plans.
#     """

#     serializer_class = VasStatusSerializer
#     authentication_classes = [JWTAuthentication]
#     permission_classes = (IsAuthenticated, VasPermission)

#     @extend_schema(
#         description="Variation codes",
#         responses={200: {"description": "Health insurance Varitaion Codes"}},
#     )
#     def get(self, request, *args, **kwargs):
#         user = self.request.user  # Get the authenticated user.

#         if user:
#             resource = "service-variations?serviceID=health-insurance-rhl"
#             fetch_all_variation_codes_headers = {
#                 "accept": "application/json",
#                 "api-key": api_key,
#                 "secret-key": x_secret,
#             }
#             try:
#                 response = requests.get(
#                     url=vtpass_url + resource,
#                     headers=fetch_all_variation_codes_headers,
#                 )
#                 if response.status_code == 200:
#                     resp = response.json()["content"]["variations"]
#                     response_data = {
#                         "data": resp,
#                     }
#                     return Response(data=response_data, status=status.HTTP_200_OK)
#                 else:
#                     return Response(data=response.json(), status=response.status_code)
#             except requests.exceptions.RequestException as e:
#                 return Response(
#                     {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
#                 )


# class GetHealthInsuranceOptions(generics.RetrieveAPIView):
#     """
#     GetHealthInsuranceOptions is a GET request handler for retrieving health insurance
#     options, in this case lit of supported hospitals.
#     """

#     serializer_class = VasStatusSerializer
#     authentication_classes = [JWTAuthentication]
#     permission_classes = (IsAuthenticated, VasPermission)

#     @extend_schema(
#         description="Options",
#         responses={200: {"description": "Health insurance options"}},
#     )
#     def get(self, request, *args, **kwargs):
#         user = self.request.user  # Get the authenticated user.

#         if user:
#             resource = "options?serviceID=health-insurance-rhl&name=selected_hospital"
#             insurance_options_headers = {
#                 "accept": "application/json",
#                 "api-key": api_key,
#                 "secret-key": x_secret,
#             }
#             try:
#                 response = requests.get(
#                     url=vtpass_url + resource,
#                     headers=insurance_options_headers,
#                 )
#                 if response.status_code == 200:
#                     resp = response.json()["content"]["options"]
#                     response_data = {
#                         "data": resp,
#                     }
#                     return Response(data=response_data, status=status.HTTP_200_OK)
#                 else:
#                     return Response(data=response.json(), status=response.status_code)
#             except requests.exceptions.RequestException as e:
#                 return Response(
#                     {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
#                 )


# class HealthInsuranceView(generics.GenericAPIView):
#     """
#     HealthInsuranceView is the POST request handler for creating
#     a home cover insurance.
#     """

#     serializer_class = HealthInsuranceSerializer
#     authentication_classes = [JWTAuthentication]
#     permission_classes = (IsAuthenticated, VasPermission)
#     parser_classes = (MultiPartParser, JSONParser)

#     def post(self, request):
#         user_data = {
#             key: value.strip() if isinstance(value, str) else value
#             for key, value in request.data.items()
#         }
#         user = request.user

#         pin = user_data.get("pin")
#         use_points = user_data.get("use_points")
#         use_rewards = user_data.get("use_rewards")
#         amount = user_data.get("amount")

#         account = AccountCreation.objects.get(user=user)
#         verification = Pin.verify(user=user, pin=pin, hashed_pin=account.pin)
#         if verification:
#             payment_option = request.data.get("payment_option")
#             match payment_option:
#                 case "WALLET":
#                     if use_points:
#                         _, pts_amt = Pay.with_pts(user=user, amount=amount)
#                     else:
#                         pts_amt = 0
#                     if use_rewards:
#                         _, rwd_amt = Pay.with_rwd(user=user, amount=amount)
#                     else:
#                         rwd_amt = 0

#                     new_amount = amount - pts_amt - rwd_amt

#                     user_details = AccountCreation.objects.get(user=user)
#                     debit_response = Account.Debit(
#                         debitAccount=user_details.account_number,
#                         amount=new_amount,
#                         reason="Debit for health insurance.",
#                         transactionReference="",
#                     )

#                     if debit_response.status_code == 200:
#                         serializer = self.serializer_class(data=user)
#                         if serializer.is_valid(raise_exception=True):
#                             HealthInsurance(
#                                 self.uploaded_passport_url,
#                                 user=user,
#                                 serializer=serializer,
#                                 user_data=user_data,
#                             )
#                             # Start a separate thread for image upload
#                             thread_upload = Thread(
#                                 target=self.upload_image,
#                                 args=(user_data.get("Passport_Photo"),),
#                             )
#                             thread_upload.start()
#                         else:
#                             return Response(
#                                 data=serializer.errors,
#                                 status=status.HTTP_400_BAD_REQUEST,
#                             )
#                     else:
#                         credit_response = Account.Credit(
#                             acct_no=user_details.account_number,
#                             amount=new_amount,
#                             transactionReference="",
#                             reason="Refund for failed health insurance.",
#                         )
#                         if credit_response == 200:
#                             logging.info(
#                                 f"Account credit successful for account {user_details.account_number}. Amount: {new_amount}"
#                             )
#                         else:
#                             logging.error(
#                                 f"Account credit failed for account {user_details.account_number}. Status code: {credit_response}"
#                             )
#                         return Response(
#                             data=debit_response.json(),
#                             status=debit_response.status_code,
#                         )

#                 case "CARD":
#                     pass

#     def upload_image(self, image_data):
#         passport = cloud.upload(file=image_data)
#         self.uploaded_passport_url = passport["url"]
