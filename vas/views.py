import requests
from threading import Thread
from decouple import config

from rest_framework.parsers import MultiPartParser, JSONParser

from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication

from drf_spectacular.utils import extend_schema

from .serializers import (
    VasStatusSerializer,
    AirtimeTopupSerializer,
    DataSubscriptionSerializer,
    ElectricityBillSerializer,
    TvSubscriptionSerializer,
    IntlAirtimeSerializer,
    WaecRegistrationSerializer,
    VehicleInsuranceSerializer,
    AccidentInsuranceSerializer,
    HomeCoverInsuranceSerializer,
    HealthInsuranceSerializer,
)
from banking.controllers import Account
from banking.payments import UseCard
from banking.models import PayWithCard
from permissions import VasPermission
from wallets.controllers import Pin
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

from cloudinary import uploader as cloud


vtpass_url = config("VT_PASS_BASE_URL")
x_secret = config("VT_PASS_SECRET_KEY")
api_key = config("VT_PASS_API_KEY")
x_token = config("VT_PASS_PUBLIC_KEY")


class AirTimeTopUp(generics.GenericAPIView):
    """
    AirTimeTopUp is a POST request handler for purchase airtime for
    service providers in Nigeria.
    """

    serializer_class = AirtimeTopupSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, VasPermission)

    def post(self, request):
        user_data = request.data
        user = request.user

        pin = request.data.get("pin")
        payment_option = request.data.get("payment_option")
        use_bonus = request.data.get("use_bonus")
        amount = request.data.get("amount")

        serializer = self.serializer_class(data=user_data)
        verification = Pin.verify_pin(user=user, pin=pin)
        if verification:
            if use_bonus:
                if user.welcome_bonus <= float(amount):
                    airtime(
                        user=user,
                        serializer=serializer,
                        reason="Debit for airtime recharge.",
                        user_data=user_data
                    )
                else:
                    return Response(
                        data="You do not have enough bonus to purchase this product",
                        status=status.HTTP_400_BAD_REQUEST
                    )
            else:
                match payment_option:
                    case "WALLET":
                        # Inititate a debit on the customer's account.
                        debit_response = Account.Debit(
                            amount=amount, reason="Debit for airtime recharge."
                        )

                        if debit_response.status_code == 200:
                            serializer = self.serializer_class(data=user_data)
                            if serializer.is_valid(raise_exception=True):
                                airtime(
                                    user=user,
                                    serializer=serializer,
                                    reason="Debit for airtime recharge.",
                                    user_data=user_data
                                )
                            else:
                                return Response(
                                    data=serializer.errors,
                                    status=status.HTTP_400_BAD_REQUEST,
                                )
                        else:
                            return Response(
                                data=debit_response.json(),
                                status=debit_response.status_code,
                            )

                    case "CARD":
                        initialize_response = UseCard.initialize_payment(
                            amount=request.data.get("amount"),
                            customerName=user.firstname + user.last_name,
                            customerEmail=user.email,
                            paymentDescription="Debit for airtime recharge.",
                        )
                        if initialize_response.status_code == 200:
                            resp = initialize_response.json()["responseBody"]
                            init_pay = PayWithCard.objects.create(
                                user=user,
                                transactionReference=resp["transactionReference"],
                                paymentReference=resp["paymentReference"],
                                customerName=user.firstname + user.last_name,
                                customerEmail=user.email,
                                redirectUrl=resp["checkoutUrl"],
                            )
                            charge_from_card_resp = UseCard.charge(
                                transactionReference=init_pay.transactionReference,
                                number=request.data.get("number"),
                                expiryMonth=request.data.get("expiryMonth"),
                                expiryYear=request.data.get("expiryYear"),
                                pin=request.data.get("card_pin"),
                                cvv=request.data.get("cvv"),
                            )
                            if charge_from_card_resp.status_code == 200:
                                resp = initialize_response.json()["responseBody"]
                                validate_card = UseCard.validate_otp(
                                    init_pay.transactionReference,
                                    tokenId=request.data.get("tokenId"),
                                    token=request.data.get("token"),
                                )
                                if validate_card.status_code == 200:
                                    serializer = self.serializer_class(data=user_data)
                                    if serializer.is_valid(raise_exception=True):
                                        airtime(
                                            user=user,
                                            serializer=serializer,
                                            reason="Debit for airtime recharge.",
                                            user_data=user_data,
                                        )
                                    else:
                                        return Response(
                                            data=serializer.errors,
                                            status=status.HTTP_400_BAD_REQUEST,
                                        )
                                else:
                                    return Response(
                                        data=debit_response.json(),
                                        status=debit_response.status_code,
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


class DataSubscription(generics.GenericAPIView):
    """
    DataSubscription is a POST request handler for data
    subscription.
    """

    serializer_class = DataSubscriptionSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, VasPermission)

    def post(self, request):
        user_data = request.data
        user = request.user

        pin = request.data.get("pin")
        use_bonus = request.data.get("use_bonus")
        amount = request.data.get("amount")

        serializer = self.serializer_class(data=user_data)
        verification = Pin.verify_pin(user=user, pin=pin)
        if verification:
            payment_option = request.data.get("payment_option")
            if use_bonus:
                if user.welcome_bonus <= float(amount):
                    data(
                        user=user,
                        serializer=serializer,
                        reason="Debit for data subscription.",
                        user_data=user_data
                    )
                else:
                    return Response(
                        data="You do not have enough bonus to purchase this product",
                        status=status.HTTP_400_BAD_REQUEST
                    )
            else:
                match payment_option:
                    case "WALLET":
                        # Inititate a debit on the customer's account.
                        debit_response = Account.Debit(
                            amount=user_data["amount"],
                            reason="Debit for data subscription.",
                        )

                        if debit_response.status_code == 200:
                            serializer = self.serializer_class(data=user_data)
                            if serializer.is_valid(raise_exception=True):
                                data(
                                    user=user,
                                    serializer=serializer,
                                    reason="Debit for data subscription.",
                                    user_data=user_data
                                )
                            else:
                                return Response(
                                    data=serializer.errors,
                                    status=status.HTTP_400_BAD_REQUEST,
                                )
                        else:
                            return Response(
                                data=debit_response.json(),
                                status=debit_response.status_code,
                            )
                    case "CARD":
                        initialize_response = UseCard.initialize_payment(
                            amount=request.data.get("amount"),
                            customerName=user.firstname + user.last_name,
                            customerEmail=user.email,
                            paymentDescription="Debit for data subscription",
                        )
                        if initialize_response.status_code == 200:
                            resp = initialize_response.json()["responseBody"]
                            init_pay = PayWithCard.objects.create(
                                user=user,
                                transactionReference=resp["transactionReference"],
                                paymentReference=resp["paymentReference"],
                                customerName=user.firstname + user.last_name,
                                customerEmail=user.email,
                                redirectUrl=resp["checkoutUrl"],
                            )
                            charge_from_card_resp = UseCard.charge(
                                transactionReference=init_pay.transactionReference,
                                number=request.data.get("number"),
                                expiryMonth=request.data.get("expiryMonth"),
                                expiryYear=request.data.get("expiryYear"),
                                pin=request.data.get("card_pin"),
                                cvv=request.data.get("cvv"),
                            )
                            if charge_from_card_resp.status_code == 200:
                                resp = initialize_response.json()["responseBody"]
                                validate_card = UseCard.validate_otp(
                                    init_pay.transactionReference,
                                    tokenId=request.data.get("tokenId"),
                                    token=request.data.get("token"),
                                )
                                if validate_card.status_code == 200:
                                    serializer = self.serializer_class(data=user_data)
                                    if serializer.is_valid(raise_exception=True):
                                        data(
                                            user=user,
                                            serializer=serializer,
                                            reason="Debit for data subscription.",
                                            user_data=user_data,
                                        )
                                    else:
                                        return Response(
                                            data=serializer.errors,
                                            status=status.HTTP_400_BAD_REQUEST,
                                        )
                                else:
                                    return Response(
                                        data=debit_response.json(),
                                        status=debit_response.status_code,
                                    )


class VerifyMeterNumber(generics.RetrieveAPIView):
    """
    VerifySmartCardNumber is a POST request handler for verifying
    electricity meter number.
    """

    serializer_class = VasStatusSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, VasPermission)

    @extend_schema(
        description="Meter number",
        responses={200: {"description": "Verify meter number"}},
    )
    def post(self, request):
        user = request.data

        resource = "merchant-verify"
        payload = {
            "serviceID": user["serviceID"],
            "type": user["type"],
            "billersCode": user["billersCode"],
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

        pin = request.data.get("pin")
        use_bonus = request.data.get("use_bonus")
        amount = request.data.get("amount")

        serializer = self.serializer_class(data=user_data)
        verification = Pin.verify_pin(user=user, pin=pin)
        if verification:
            payment_option = request.data.get("payment_option")
            if use_bonus:
                if user.welcome_bonus <= float(amount):
                    electricity(
                        user=user,
                        serializer=serializer,
                        reason="Debit for electricity bill payment.",
                        user_data=user_data
                    )
                else:
                    return Response(
                        data="You do not have enough bonus to purchase this product",
                        status=status.HTTP_400_BAD_REQUEST
                    )
                match payment_option:
                    case "WALLET":
                        debit_response = Account.Debit(
                            amount=user_data["amount"],
                            reason="Debit for electricity bill payment.",
                        )
                        if debit_response == 200:
                            serializer = self.serializer_class(data=user_data)
                            if serializer.is_valid(raise_exception=True):
                                electricity(
                                    user=user,
                                    serializer=serializer,
                                    reason="Debit for electricity bill payment.",
                                    user_data=user_data
                                )
                            else:
                                return Response(
                                    data=serializer.errors,
                                    status=status.HTTP_400_BAD_REQUEST,
                                )
                        else:
                            return Response(
                                data=debit_response.json(),
                                status=debit_response.status_code,
                            )

                    case "CARD":
                        initialize_response = UseCard.initialize_payment(
                            amount=request.data.get("amount"),
                            customerName=user.firstname + user.last_name,
                            customerEmail=user.email,
                            paymentDescription="Debit for electricity bill payment.",
                        )
                        if initialize_response.status_code == 200:
                            resp = initialize_response.json()["responseBody"]
                            init_pay = PayWithCard.objects.create(
                                user=user,
                                transactionReference=resp["transactionReference"],
                                paymentReference=resp["paymentReference"],
                                customerName=user.firstname + user.last_name,
                                customerEmail=user.email,
                                redirectUrl=resp["checkoutUrl"],
                            )
                            charge_from_card_resp = UseCard.charge(
                                transactionReference=init_pay.transactionReference,
                                number=request.data.get("number"),
                                expiryMonth=request.data.get("expiryMonth"),
                                expiryYear=request.data.get("expiryYear"),
                                pin=request.data.get("card_pin"),
                                cvv=request.data.get("cvv"),
                            )
                            if charge_from_card_resp.status_code == 200:
                                resp = initialize_response.json()["responseBody"]
                                validate_card = UseCard.validate_otp(
                                    init_pay.transactionReference,
                                    tokenId=request.data.get("tokenId"),
                                    token=request.data.get("token"),
                                )
                                if validate_card.status_code == 200:
                                    serializer = self.serializer_class(data=user_data)
                                    if serializer.is_valid(raise_exception=True):
                                        electricity(
                                            user=user,
                                            serializer=serializer,
                                            reason="Debit for electricity bill payment.",
                                            user_data=user_data,
                                        )
                                    else:
                                        return Response(
                                            data=serializer.errors,
                                            status=status.HTTP_400_BAD_REQUEST,
                                        )
                                else:
                                    return Response(
                                        data=debit_response.json(),
                                        status=debit_response.status_code,
                                    )


class ProductStatus(generics.RetrieveAPIView):
    """
    ProductStatus is the POST request handler for checking the status
    of any Value Added Services product purchased. It takes in the
    request_id of the request and returns the status.
    """

    serializer_class = VasStatusSerializer
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


class VerifySmartCardNumber(generics.GenericAPIView):
    """
    VerifySmartCardNumber is a POST request handler for verifying smart
    card or registration number for tv operators(e.g dstv, gotv).
    """

    serializer_class = VasStatusSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, VasPermission)

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
        user_data = request.data
        user = request.user

        pin = request.data.get("pin")

        verification = Pin.verify_pin(user=user, pin=pin)
        if verification:
            payment_option = request.data.get("payment_option")
            match payment_option:
                case "WALLET":
                    debit_response = Account.Debit(
                        amount=user_data["amount"], reason="Debit for Tv subscription."
                    )
                    if debit_response == 200:
                        serializer = self.serializer_class(data=user_data)
                        if serializer.is_valid(raise_exception=True):
                            NewTvSub(
                                user=user,
                                serializer=serializer,
                                reason="Debit for Tv subscription.",
                                user_data=user_data
                            )
                        else:
                            return Response(
                                data=serializer.errors,
                                status=status.HTTP_400_BAD_REQUEST,
                            )
                    else:
                        return Response(
                            data=debit_response.json(),
                            status=debit_response.status_code,
                        )
                case "CARD":
                    initialize_response = UseCard.initialize_payment(
                        amount=request.data.get("amount"),
                        customerName=user.firstname + user.last_name,
                        customerEmail=user.email,
                        paymentDescription="Debit for Tv subscription.",
                    )
                    if initialize_response.status_code == 200:
                        resp = initialize_response.json()["responseBody"]
                        init_pay = PayWithCard.objects.create(
                            user=user,
                            transactionReference=resp["transactionReference"],
                            paymentReference=resp["paymentReference"],
                            customerName=user.firstname + user.last_name,
                            customerEmail=user.email,
                            redirectUrl=resp["checkoutUrl"],
                        )
                        charge_from_card_resp = UseCard.charge(
                            transactionReference=init_pay.transactionReference,
                            number=request.data.get("number"),
                            expiryMonth=request.data.get("expiryMonth"),
                            expiryYear=request.data.get("expiryYear"),
                            pin=request.data.get("card_pin"),
                            cvv=request.data.get("cvv"),
                        )
                        if charge_from_card_resp.status_code == 200:
                            resp = initialize_response.json()["responseBody"]
                            validate_card = UseCard.validate_otp(
                                init_pay.transactionReference,
                                tokenId=request.data.get("tokenId"),
                                token=request.data.get("token"),
                            )
                            if validate_card.status_code == 200:
                                serializer = self.serializer_class(data=user_data)
                                if serializer.is_valid(raise_exception=True):
                                    NewTvSub(
                                        user=user,
                                        serializer=serializer,
                                        reason="Debit for Tv subscription.",
                                        user_data=user_data,
                                    )
                                else:
                                    return Response(
                                        data=serializer.errors,
                                        status=status.HTTP_400_BAD_REQUEST,
                                    )
                            else:
                                return Response(
                                    data=debit_response.json(),
                                    status=debit_response.status_code,
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
        user_data = request.data
        user = request.user

        pin = request.data.get("pin")

        verification = Pin.verify_pin(user=user, pin=pin)
        if verification:
            payment_option = request.data.get("payment_option")
            match payment_option:
                case "WALLET":
                    debit_response = Account.Debit(
                        amount=user_data["amount"],
                        reason="Debit for tv subscription renewal.",
                    )
                    if debit_response.status_code == 200:
                        serializer = self.serializer_class(data=user_data)
                        if serializer.is_valid(raise_exception=True):
                            RenewTvSub(
                                user=user,
                                serializer=serializer,
                                reason="Debit for tv subscription renewal.",
                                user_data=user_data
                            )
                        else:
                            return Response(
                                data=serializer.errors,
                                status=status.HTTP_400_BAD_REQUEST,
                            )
                    else:
                        return Response(
                            data=debit_response.json(),
                            status=debit_response.status_code,
                        )
                case "CARD":
                    initialize_response = UseCard.initialize_payment(
                        amount=request.data.get("amount"),
                        customerName=user.firstname + user.last_name,
                        customerEmail=user.email,
                        paymentDescription="Debit for tv subscription renewal.",
                    )
                    if initialize_response.status_code == 200:
                        resp = initialize_response.json()["responseBody"]
                        init_pay = PayWithCard.objects.create(
                            user=user,
                            transactionReference=resp["transactionReference"],
                            paymentReference=resp["paymentReference"],
                            customerName=user.firstname + user.last_name,
                            customerEmail=user.email,
                            redirectUrl=resp["checkoutUrl"],
                        )
                        charge_from_card_resp = UseCard.charge(
                            transactionReference=init_pay.transactionReference,
                            number=request.data.get("number"),
                            expiryMonth=request.data.get("expiryMonth"),
                            expiryYear=request.data.get("expiryYear"),
                            pin=request.data.get("card_pin"),
                            cvv=request.data.get("cvv"),
                        )
                        if charge_from_card_resp.status_code == 200:
                            resp = initialize_response.json()["responseBody"]
                            validate_card = UseCard.validate_otp(
                                init_pay.transactionReference,
                                tokenId=request.data.get("tokenId"),
                                token=request.data.get("token"),
                            )
                            if validate_card.status_code == 200:
                                serializer = self.serializer_class(data=user_data)
                                if serializer.is_valid(raise_exception=True):
                                    RenewTvSub(
                                        user=user,
                                        serializer=serializer,
                                        reason="Debit for tv subscription renewal.",
                                        user_data=user_data,
                                    )
                                else:
                                    return Response(
                                        data=serializer.errors,
                                        status=status.HTTP_400_BAD_REQUEST,
                                    )
                            else:
                                return Response(
                                    data=debit_response.json(),
                                    status=debit_response.status_code,
                                )


class GetIntlAirtimeCountryCodes(generics.GenericAPIView):
    """
    GetIntlAirtimeCountryCodes is a GET request handler for retrieving
    available counntry codes for airtime services for worldwide.
    Take note of the country codes as it would be required to
    get airtime products available in that country.
    """

    serializer_class = VasStatusSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, VasPermission)

    @extend_schema(
        description="Variation codes",
        responses={200: {"description": "Get international airtime country codes"}},
    )
    def get(self, request):
        resource = "get-international-airtime-countries"
        get_intl_codes_headers = {
            "accept": "application/json",
            "api-key": api_key,
            "secret-key": x_secret,
        }

        try:
            response = requests.get(
                url=vtpass_url + resource,
                headers=get_intl_codes_headers,
            )
            if response.status_code == 200:
                resp = response.json()["content"]["countries"]
                for _ in range(len(resp)):
                    response_data = {
                        "data": resp,
                    }
                    return Response(data=response_data, status=status.HTTP_200_OK)
        except requests.exceptions.RequestException as e:
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class GetIntlAirtimeProducts(generics.GenericAPIView):
    """
    GetIntlAirtimeProducts is a GET request handler for retrieving
    airtime products available in the country. The endpoints takes
    the country_code as url params.
    """

    serializer_class = VasStatusSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, VasPermission)

    @extend_schema(
        description="International airtime products",
        responses={200: {"description": "Get International airtime products"}},
    )
    def get(self, request, *args, **kwargs):
        param_value = kwargs.get("country_code")

        resource = "get-international-airtime-product-types?code=" + param_value
        prod_types_headers = {
            "accept": "application/json",
            "api-key": api_key,
            "secret-key": x_secret,
        }

        try:
            response = requests.get(
                url=vtpass_url + resource,
                headers=prod_types_headers,
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


class GetIntlAirtimeOperators(generics.GenericAPIView):
    """
    GetIntlAirtimeOperators is a GET request handler for retrieving
    airtime operators available in the country. The endpoints takes
    the country_code aas well as product type id as url params.
    Take note of the operator_id and it will be required to get
    the variation codes.
    """

    serializer_class = VasStatusSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, VasPermission)

    @extend_schema(
        description="Airtime operators.",
        responses={200: {"description": "Get international airtime operators"}},
    )
    def get(self, request, *args, **kwargs):
        code = kwargs.get("country_code")
        product_type = kwargs.get("product_type_id")

        prefix = "get-international-airtime-operators?code="
        resource = prefix + code + "&product_type_id=" + product_type
        code_and_prod_headers = {
            "accept": "application/json",
            "api-key": api_key,
            "secret-key": x_secret,
        }

        try:
            response = requests.get(
                url=vtpass_url + resource,
                headers=code_and_prod_headers,
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


class GetIntlAirtimeVaraitionCodes(generics.GenericAPIView):
    """
    GetIntlAirtimeVaraitionCodes is the GET request handler for retrieving
    the variation codes for international airrtime topup.
    Take key note of the variation codes as they
    are required to chose a registration plan.
    The endpoints takes the operator_id as well as product type id
    as url params.
    """

    serializer_class = VasStatusSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, VasPermission)

    @extend_schema(
        description="Variation codes",
        responses={200: {"description": "International airtime Varitaion Codes"}},
    )
    def get(self, request, *args, **kwargs):
        ops_id = kwargs.get("operator_id")
        product_type = kwargs.get("product_type_id")

        prefix = "service-variations?serviceID=foreign-airtime&operator_id="
        resource = prefix + ops_id + "&product_type_id=" + product_type
        code_and_prod_headers = {
            "accept": "application/json",
            "api-key": api_key,
            "secret-key": x_secret,
        }

        try:
            response = requests.get(
                url=vtpass_url + resource,
                headers=code_and_prod_headers,
            )
            if response.status_code == 200:
                resp = response.json()["content"]["variations"]
                for _ in range(len(resp)):
                    response_data = {
                        "data": resp,
                    }
                    return Response(data=response_data, status=status.HTTP_200_OK)
        except requests.exceptions.RequestException as e:
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class InternationalAirTimeTopUp(generics.GenericAPIView):
    """
    InternationalAirTimeTopUp is the POST request handler for
    international airtime topup.
    """

    serializer_class = IntlAirtimeSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, VasPermission)

    def post(self, request):
        user_data = request.data
        user = request.user

        pin = request.data.get("pin")
        verification = Pin.verify_pin(user=user, pin=pin)
        if verification:
            payment_option = request.data.get("payment_option")
            match payment_option:
                case "WALLET":
                    debit_response = Account.Debit(
                        amount=user_data["amount"],
                        reason="Debit for international airtime recharge.",
                    )
                    if debit_response == 200:
                        serializer = self.serializer_class(data=user_data)
                        if serializer.is_valid(raise_exception=True):
                            international_topup(
                                user=user,
                                serializer=serializer,
                                reason="Debit for international airtime recharge.",
                                user_data=user_data
                            )
                        else:
                            return Response(
                                data=serializer.errors,
                                status=status.HTTP_400_BAD_REQUEST,
                            )
                    else:
                        return Response(
                            data=debit_response.json(),
                            status=debit_response.status_code,
                        )
                case "CARD":
                    initialize_response = UseCard.initialize_payment(
                        amount=request.data.get("amount"),
                        customerName=user.firstname + user.last_name,
                        customerEmail=user.email,
                        paymentDescription="Debit for international airtime recharge.",
                    )
                    if initialize_response.status_code == 200:
                        resp = initialize_response.json()["responseBody"]
                        init_pay = PayWithCard.objects.create(
                            user=user,
                            transactionReference=resp["transactionReference"],
                            paymentReference=resp["paymentReference"],
                            customerName=user.firstname + user.last_name,
                            customerEmail=user.email,
                            redirectUrl=resp["checkoutUrl"],
                        )
                        charge_from_card_resp = UseCard.charge(
                            transactionReference=init_pay.transactionReference,
                            number=request.data.get("number"),
                            expiryMonth=request.data.get("expiryMonth"),
                            expiryYear=request.data.get("expiryYear"),
                            pin=request.data.get("card_pin"),
                            cvv=request.data.get("cvv"),
                        )
                        if charge_from_card_resp.status_code == 200:
                            resp = initialize_response.json()["responseBody"]
                            validate_card = UseCard.validate_otp(
                                init_pay.transactionReference,
                                tokenId=request.data.get("tokenId"),
                                token=request.data.get("token"),
                            )
                            if validate_card.status_code == 200:
                                serializer = self.serializer_class(data=user_data)
                                if serializer.is_valid(raise_exception=True):
                                    international_topup(
                                        user=user,
                                        serializer=serializer,
                                        reason="Debit for international airtime recharge.",
                                        user_data=user_data,
                                    )
                                else:
                                    return Response(
                                        data=serializer.errors,
                                        status=status.HTTP_400_BAD_REQUEST,
                                    )
                            else:
                                return Response(
                                    data=debit_response.json(),
                                    status=debit_response.status_code,
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
        user_data = request.data
        user = request.user

        pin = request.data.get("pin")
        verification = Pin.verify_pin(user=user, pin=pin)
        if verification:
            payment_option = request.data.get("payment_option")
            match payment_option:
                case "WALLET":
                    debit_response = Account.Debit(
                        amount=user_data["amount"],
                        reason="Debit for waec registration.",
                    )
                    if debit_response == 200:
                        serializer = self.serializer_class(data=user_data)
                        if serializer.is_valid(raise_exception=True):
                            waec_reg(
                                user=user,
                                serializer=serializer,
                                reason="Debit for waec registration.",
                                user_data=user_data
                            )
                        else:
                            return Response(
                                data=serializer.errors,
                                status=status.HTTP_400_BAD_REQUEST,
                            )
                    else:
                        return Response(
                            data=debit_response.json(),
                            status=debit_response.status_code,
                        )
                case "CARD":
                    initialize_response = UseCard.initialize_payment(
                        amount=request.data.get("amount"),
                        customerName=user.firstname + user.last_name,
                        customerEmail=user.email,
                        paymentDescription="Debit for waec registration.",
                    )
                    if initialize_response.status_code == 200:
                        resp = initialize_response.json()["responseBody"]
                        init_pay = PayWithCard.objects.create(
                            user=user,
                            transactionReference=resp["transactionReference"],
                            paymentReference=resp["paymentReference"],
                            customerName=user.firstname + user.last_name,
                            customerEmail=user.email,
                            redirectUrl=resp["checkoutUrl"],
                        )
                        charge_from_card_resp = UseCard.charge(
                            transactionReference=init_pay.transactionReference,
                            number=request.data.get("number"),
                            expiryMonth=request.data.get("expiryMonth"),
                            expiryYear=request.data.get("expiryYear"),
                            pin=request.data.get("card_pin"),
                            cvv=request.data.get("cvv"),
                        )
                        if charge_from_card_resp.status_code == 200:
                            resp = initialize_response.json()["responseBody"]
                            validate_card = UseCard.validate_otp(
                                init_pay.transactionReference,
                                tokenId=request.data.get("tokenId"),
                                token=request.data.get("token"),
                            )
                            if validate_card.status_code == 200:
                                serializer = self.serializer_class(data=user_data)
                                if serializer.is_valid(raise_exception=True):
                                    waec_reg(
                                        user=user,
                                        serializer=serializer,
                                        reason="Debit for waec registration.",
                                        user_data=user_data,
                                    )
                                else:
                                    return Response(
                                        data=serializer.errors,
                                        status=status.HTTP_400_BAD_REQUEST,
                                    )
                            else:
                                return Response(
                                    data=debit_response.json(),
                                    status=debit_response.status_code,
                                )


class GetVehicleInsuranceVaritaionCodes(generics.RetrieveAPIView):
    """
    GetVehicleInsuranceVaritaionCodes is the GET request handler for
    retrieving the variation codes for vehicle insurance.
    Take key note of the variation codes as they
    are required to create an accident insurance.
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
            wae_variation_codes_headers = {
                "accept": "application/json",
                "api-key": api_key,
                "secret-key": x_secret,
            }

            try:
                response = requests.get(
                    url=vtpass_url + resource,
                    headers=wae_variation_codes_headers,
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
        user_data = request.data
        user = request.user

        pin = request.data.get("pin")
        verification = Pin.verify_pin(user=user, pin=pin)
        if verification:
            payment_option = request.data.get("payment_option")
            match payment_option:
                case "WALLET":
                    debit_response = Account.Debit(
                        amount=user_data["amount"],
                        reason="Debit for vehicle insurance.",
                    )

                    if debit_response.status_code == 200:
                        serializer = self.serializer_class(data=user_data)
                        if serializer.is_valid(raise_exception=True):
                            VehicleInsurance(
                                user=user,
                                serializer=serializer,
                                reason="Debit for vehicle insurance.",
                                user_data=user_data
                            )
                        else:
                            return Response(
                                data=serializer.errors,
                                status=status.HTTP_400_BAD_REQUEST,
                            )
                    else:
                        return Response(
                            data=debit_response.json(),
                            status=debit_response.status_code,
                        )
                case "CARD":
                    initialize_response = UseCard.initialize_payment(
                        amount=request.data.get("amount"),
                        customerName=user.firstname + user.last_name,
                        customerEmail=user.email,
                        paymentDescription="Debit for vehicle insurance.",
                    )
                    if initialize_response.status_code == 200:
                        resp = initialize_response.json()["responseBody"]
                        init_pay = PayWithCard.objects.create(
                            user=user,
                            transactionReference=resp["transactionReference"],
                            paymentReference=resp["paymentReference"],
                            customerName=user.firstname + user.last_name,
                            customerEmail=user.email,
                            redirectUrl=resp["checkoutUrl"],
                        )
                        charge_from_card_resp = UseCard.charge(
                            transactionReference=init_pay.transactionReference,
                            number=request.data.get("number"),
                            expiryMonth=request.data.get("expiryMonth"),
                            expiryYear=request.data.get("expiryYear"),
                            pin=request.data.get("card_pin"),
                            cvv=request.data.get("cvv"),
                        )
                        if charge_from_card_resp.status_code == 200:
                            resp = initialize_response.json()["responseBody"]
                            validate_card = UseCard.validate_otp(
                                init_pay.transactionReference,
                                tokenId=request.data.get("tokenId"),
                                token=request.data.get("token"),
                            )
                            if validate_card.status_code == 200:
                                serializer = self.serializer_class(data=user_data)
                                if serializer.is_valid(raise_exception=True):
                                    VehicleInsurance(
                                        user=user,
                                        serializer=serializer,
                                        reason="Debit for vehicle insurance.",
                                        user_data=user_data,
                                    )
                                else:
                                    return Response(
                                        data=serializer.errors,
                                        status=status.HTTP_400_BAD_REQUEST,
                                    )
                            else:
                                return Response(
                                    data=debit_response.json(),
                                    status=debit_response.status_code,
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
        user_data = request.data
        user = request.user

        pin = request.data.get("pin")
        verification = Pin.verify_pin(user=user, pin=pin)
        if verification:
            payment_option = request.data.get("payment_option")
            match payment_option:
                case "WALLET":
                    debit_response = Account.Debit(
                        amount=user_data["amount"],
                        reason="Debit for accident inssurance.",
                    )

                    if debit_response.status_code == 200:
                        serializer = self.serializer_class(data=user)
                        if serializer.is_valid(raise_exception=True):
                            AccidentInsurance(
                                user=user,
                                serializer=serializer,
                                reason="Debit for accident inssurance.",
                                user_data=user_data
                            )
                        else:
                            return Response(
                                data=serializer.errors,
                                status=status.HTTP_400_BAD_REQUEST,
                            )
                    else:
                        return Response(
                            data=debit_response.json(),
                            status=debit_response.status_code,
                        )

                case "CARD":
                    initialize_response = UseCard.initialize_payment(
                        amount=request.data.get("amount"),
                        customerName=user.firstname + user.last_name,
                        customerEmail=user.email,
                        paymentDescription="Debit for accident inssurance.",
                    )
                    if initialize_response.status_code == 200:
                        resp = initialize_response.json()["responseBody"]
                        init_pay = PayWithCard.objects.create(
                            user=user,
                            transactionReference=resp["transactionReference"],
                            paymentReference=resp["paymentReference"],
                            customerName=user.firstname + user.last_name,
                            customerEmail=user.email,
                            redirectUrl=resp["checkoutUrl"],
                        )
                        charge_from_card_resp = UseCard.charge(
                            transactionReference=init_pay.transactionReference,
                            number=request.data.get("number"),
                            expiryMonth=request.data.get("expiryMonth"),
                            expiryYear=request.data.get("expiryYear"),
                            pin=request.data.get("card_pin"),
                            cvv=request.data.get("cvv"),
                        )
                        if charge_from_card_resp.status_code == 200:
                            resp = initialize_response.json()["responseBody"]
                            validate_card = UseCard.validate_otp(
                                init_pay.transactionReference,
                                tokenId=request.data.get("tokenId"),
                                token=request.data.get("token"),
                            )
                            if validate_card.status_code == 200:
                                serializer = self.serializer_class(data=user_data)
                                if serializer.is_valid(raise_exception=True):
                                    AccidentInsurance(
                                        user=user,
                                        serializer=serializer,
                                        reason="Debit for accident inssurance.",
                                        user_data=user_data,
                                    )
                                else:
                                    return Response(
                                        data=serializer.errors,
                                        status=status.HTTP_400_BAD_REQUEST,
                                    )
                            else:
                                return Response(
                                    data=debit_response.json(),
                                    status=debit_response.status_code,
                                )


class GetHomeCoverVaritaionCodes(generics.RetrieveAPIView):
    """
    GetHomeCoverVaritaionCodes is the GET request handler for
    retrieving the variation codes fora home cover insurance.
    Take key note of the variation codes as they
    are required to create a home cover insurance.
    """

    serializer_class = VasStatusSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, VasPermission)

    @extend_schema(
        description="Variation codes",
        responses={200: {"description": "Home Cover Varitaion Codes"}},
    )
    def get(self, request):
        user = request.user  # Get the authenticated user.

        if user:
            resource = "service-variations?serviceID=home-cover-insurance"
            home_cover_variation_codes_headers = {
                "accept": "application/json",
                "api-key": api_key,
                "secret-key": x_secret,
            }

            try:
                response = requests.get(
                    url=vtpass_url + resource,
                    headers=home_cover_variation_codes_headers,
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


class HomeCoverInsuranceView(generics.GenericAPIView):
    """
    HomeCoverInsuranceView is the POST request handler for creating
    a home cover insurance.
    """

    serializer_class = HomeCoverInsuranceSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, VasPermission)

    def post(self, request):
        user_data = request.data
        user = request.user

        pin = request.data.get("pin")
        verification = Pin.verify_pin(user=user, pin=pin)
        if verification:
            payment_option = request.data.get("payment_option")
            match payment_option:
                case "WALLET":
                    debit_response = Account.Debit(
                        amount=user["amount"],
                        reason="Debit for home cover insurance registration.",
                    )

                    if debit_response.status_code == 200:
                        serializer = self.serializer_class(data=user)
                        if serializer.is_valid(raise_exception=True):
                            HomeCoverInsurance(
                                user=user,
                                serializer=serializer,
                                reason="Debit for home cover insurance registration.",
                                user_data=user_data
                            )
                        else:
                            return Response(
                                data=serializer.errors,
                                status=status.HTTP_400_BAD_REQUEST,
                            )
                    else:
                        return Response(
                            data=debit_response.json(),
                            status=debit_response.status_code,
                        )
                case "CARD":
                    initialize_response = UseCard.initialize_payment(
                        amount=request.data.get("amount"),
                        customerName=user.firstname + user.last_name,
                        customerEmail=user.email,
                        paymentDescription="Debit for home cover insurance registration.",
                    )
                    if initialize_response.status_code == 200:
                        resp = initialize_response.json()["responseBody"]
                        init_pay = PayWithCard.objects.create(
                            user=user,
                            transactionReference=resp["transactionReference"],
                            paymentReference=resp["paymentReference"],
                            customerName=user.firstname + user.last_name,
                            customerEmail=user.email,
                            redirectUrl=resp["checkoutUrl"],
                        )
                        charge_from_card_resp = UseCard.charge(
                            transactionReference=init_pay.transactionReference,
                            number=request.data.get("number"),
                            expiryMonth=request.data.get("expiryMonth"),
                            expiryYear=request.data.get("expiryYear"),
                            pin=request.data.get("card_pin"),
                            cvv=request.data.get("cvv"),
                        )
                        if charge_from_card_resp.status_code == 200:
                            resp = initialize_response.json()["responseBody"]
                            validate_card = UseCard.validate_otp(
                                init_pay.transactionReference,
                                tokenId=request.data.get("tokenId"),
                                token=request.data.get("token"),
                            )
                            if validate_card.status_code == 200:
                                serializer = self.serializer_class(data=user_data)
                                if serializer.is_valid(raise_exception=True):
                                    HomeCoverInsurance(
                                        user=user,
                                        serializer=serializer,
                                        reason="Debit for home cover insurance registration.",
                                        user_data=user_data,
                                    )
                                else:
                                    return Response(
                                        data=serializer.errors,
                                        status=status.HTTP_400_BAD_REQUEST,
                                    )
                            else:
                                return Response(
                                    data=debit_response.json(),
                                    status=debit_response.status_code,
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
        user_data = request.data
        user = request.user

        pin = request.data.get("pin")
        verification = Pin.verify_pin(user=user, pin=pin)
        if verification:
            payment_option = request.data.get("payment_option")
            match payment_option:
                case "WALLET":
                    debit_response = Account.Debit(
                        amount=user["amount"],
                        reason="Debit for health insurance.",
                    )

                    if debit_response.status_code == 200:
                        serializer = self.serializer_class(data=user)
                        if serializer.is_valid(raise_exception=True):
                            HealthInsurance(
                                self.uploaded_passport_url,
                                user=user,
                                serializer=serializer,
                                user_data=user_data,
                            )
                            # Start a separate thread for image upload
                            thread_upload = Thread(
                                target=self.upload_image,
                                args=(user_data.get("Passport_Photo"),),
                            )
                            thread_upload.start()
                        else:
                            return Response(
                                data=serializer.errors,
                                status=status.HTTP_400_BAD_REQUEST,
                            )
                    else:
                        return Response(
                            data=debit_response.json(),
                            status=debit_response.status_code,
                        )

                case "CARD":
                    initialize_response = UseCard.initialize_payment(
                        amount=request.data.get("amount"),
                        customerName=user.firstname + user.last_name,
                        customerEmail=user.email,
                        paymentDescription="Debit for health insurance.",
                    )
                    if initialize_response.status_code == 200:
                        resp = initialize_response.json()["responseBody"]
                        init_pay = PayWithCard.objects.create(
                            user=user,
                            transactionReference=resp["transactionReference"],
                            paymentReference=resp["paymentReference"],
                            customerName=user.firstname + user.last_name,
                            customerEmail=user.email,
                            redirectUrl=resp["checkoutUrl"],
                        )
                        charge_from_card_resp = UseCard.charge(
                            transactionReference=init_pay.transactionReference,
                            number=request.data.get("number"),
                            expiryMonth=request.data.get("expiryMonth"),
                            expiryYear=request.data.get("expiryYear"),
                            pin=request.data.get("card_pin"),
                            cvv=request.data.get("cvv"),
                        )
                        if charge_from_card_resp.status_code == 200:
                            resp = initialize_response.json()["responseBody"]
                            validate_card = UseCard.validate_otp(
                                init_pay.transactionReference,
                                tokenId=request.data.get("tokenId"),
                                token=request.data.get("token"),
                            )
                            if validate_card.status_code == 200:
                                serializer = self.serializer_class(data=user_data)
                                if serializer.is_valid(raise_exception=True):
                                    HealthInsurance(
                                        self.uploaded_passport_url,
                                        user=user,
                                        serializer=serializer,
                                        user_data=user_data,
                                    )
                                else:
                                    return Response(
                                        data=serializer.errors,
                                        status=status.HTTP_400_BAD_REQUEST,
                                    )
                            else:
                                return Response(
                                    data=debit_response.json(),
                                    status=debit_response.status_code,
                                )

    def upload_image(self, image_data):
        passport = cloud.upload(file=image_data)
        self.uploaded_passport_url = passport["url"]
