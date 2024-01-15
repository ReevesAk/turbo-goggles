import logging
from datetime import datetime
import requests
from decouple import config
from commons import Pts
from accounts.models import TxModel

from django.db import transaction

from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication

from .serializers import (
    AirtimeTopupSerializer,
    DataSubscriptionSerializer,
    ElectricityBillSerializer,
    TvSubscriptionSerializer,
    IntlAirtimeSerializer,
    WaecRegistrationSerializer,
    VehicleInsuranceSerializer,
    AccidentInsuranceSerializer,
    HomeCoverInsuranceSerializer,
)
from wallets.controllers import Credit
from banking.controllers import Account
from permissions import VasPermission
from wallets.controllers import Pin
from .helpers import VAS


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

        verification = Pin.verify_pin(user=user, pin=pin)
        if verification:
            # Inititate a debit on the customer's account.
            debit_response = Account.Debit(
                amount=user_data["amount"], reason="Debit for airtime recharge"
            )
            if debit_response.status_code == 200:
                serializer = self.serializer_class(data=user_data)
                if serializer.is_valid(raise_exception=True):
                    airtime_response = VAS.aritime(
                        service_id=user_data["serviceID"],
                        amount=user_data["amount"],
                        phone=user_data["phone"]
                    )

                    if airtime_response.status_code == 200:
                        serializer.save()
                        amount = user_data["amount"]

                        if amount >= 100:
                            new_points = Pts.award(amount=amount)
                            tx = TxModel.objects.create(
                                user=user,
                                tx_id=airtime_response.json()["transactionId"],
                                amount=user_data["amount"],
                                description="Debit for airtime recharge",
                                pts=new_points
                            )
                            pts = Pts.objects.create(user=user)
                            pts.balance += new_points
                            pts.transaction = tx
                            pts.save()
                            
                        response_data = {
                            "status": "Success",
                            "message": f"Recharge of {amount} was succesful and you have been awarded {new_points} points",
                            "data": airtime_response.json(),
                        }

                        return Response(
                            data=response_data, status=status.HTTP_200_OK
                        )
                    else:
                        response_data = {
                            "data": airtime_response.json(),
                            "messsage": "A refund will be issued.",
                        }

                        # initiate a credit refund to the customer after failed transaction.
                        _ = Credit.credit_customer(
                            first_name=user.firstName,
                            lastname=user.lastName,
                            accNo=user.accountNumber,
                            bankCode="103",
                            amount=user["amount"],
                        )
                        return Response(data=response_data, status=airtime_response.status_code)
                else:
                    return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            else:
                return Response(data=debit_response.json(), status=debit_response.status_code)


class GetNetworkProvidersVaritaionCodes(generics.RetrieveAPIView):
    """
    GetNetworkProvidersVaritaionCodes is a GET request handler for retrieving variation
    codes of different network providers. It takes in the service_ID(mtn, airtel etc)
    as url param.
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, VasPermission)

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
        verification = Pin.verify_pin(user=user, pin=pin)
        if verification:
            debit_response = Account.Debit(
                amount=user_data["amount"], reason="Debit for airtime recharge"
            )
            if debit_response == 200:
                serializer = self.serializer_class(data=user_data)
                if serializer.is_valid(raise_exception=True):
                    data_response = VAS.data(
                        service_id=user_data["serviceID"],
                        amount=user_data["amount"],
                        phone=user_data["phone"],
                        billersCode=user_data["billersCode"],
                        variation_code=user_data["variation_code"]
                    )
                    if data_response.status_code == 200:
                        serializer.save()
                        amount = user_data["amount"]

                        if amount >= 100:
                            new_points = Pts.award(amount=amount)
                            tx = TxModel.objects.create(
                                user=user,
                                tx_id=data_response.json()["transactionId"],
                                amount=user_data["amount"],
                                description="Debit for data subscription",
                                pts=new_points
                            )
                            pts = Pts.objects.create(user=user)
                            pts.balance += new_points
                            pts.transaction = tx
                            pts.save()

                            response_data = {
                                "status": "Success",
                                "message": f"Subscription of {amount} was succesful and you have been awarded {new_points} points",
                                "data": data_response.json(),
                            }

                            return Response(
                                data=response_data, status=status.HTTP_200_OK
                            )
                    else:
                        response_data = {
                            "data": data_response.json(),
                            "messsage": "A refund will be issued",
                        }

                        # initiate a credit refund to the customer after failed transaction.
                        _ = Credit.credit_customer(
                            first_name=user.firstName,
                            lastname=user.lastName,
                            accNo=user.accountNumber,
                            bankCode="103",
                            amount=user_data["amount"],
                        )
                        return Response(data=response_data, status=data_response.status_code)
                else:
                    return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            else:
                return Response(data=debit_response.json(), status=debit_response.status_code)


class VerifyMeterNumber(generics.RetrieveAPIView):
    """
    VerifySmartCardNumber is a POST request handler for verifying
    electricity meter number.
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, VasPermission)

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
        verification = Pin.verify_pin(user=user, pin=pin)
        if verification:
            debit_response = Account.Debit(
                amount=user_data["amount"], reason="Debit for electricity bill payment"
            )
            if debit_response == 200:
                serializer = self.serializer_class(data=user_data)
                if serializer.is_valid(raise_exception=True):
                    electricity_response = VAS.electricity(
                        service_id=user_data["serviceID"],
                        amount=user_data["amount"],
                        phone=user_data["phone"],
                        billersCode=user_data["billersCode"],
                        variation_code=user_data["variation_code"]
                    )
                    if electricity_response.status_code == 200:
                        serializer.save()
                        amount = user_data["amount"]
                        
                        if amount >= 100:
                            new_points = Pts.award(amount=amount)
                            try:
                                with transaction.atomic():
                                    tx, _ = TxModel.objects.get_or_create(user=user)
                                    tx.tx_id = electricity_response.json().get("transactionId", "")
                                    tx.amount = user_data.get("amount", 0)
                                    tx.description = "Debit for electricity payment"
                                    tx.pts = new_points
                                    tx.save()

                                    pts, _ = Pts.objects.get_or_create(user=user)
                                    pts.balance += new_points
                                    pts.transaction = tx
                                    pts.save()

                            except Exception as e:
                                logging.error(f"Database query error: {str(e)}")

                            response_data = {
                                "status": "Success",
                                "message": f"Payment of {amount} was succesful and you have been awarded {new_points} points",
                                "data": electricity_response.json(),
                            }

                            return Response(
                                data=response_data, status=status.HTTP_200_OK
                            )
                    else:
                        response_data = {
                            "data": electricity_response.json(),
                            "messsage": "A refund will be issued.",
                        }

                        # initiate a credit refund to the customer after failed transaction.
                        _ = Credit.credit_customer(
                            first_name=user.firstName,
                            lastname=user.lastName,
                            accNo=user.accountNumber,
                            bankCode="103",
                            amount=user["amount"],
                        )
                        return Response(data=response_data, status=electricity_response.status_code)
                else:
                    return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            else:
                return Response(data=debit_response.json(), status=debit_response.status_code)


class ProductStatus(generics.RetrieveAPIView):
    """
    ProductStatus is the POST request handler for checking the status
    of any Value Added Services product purchased. It takes in the
    request_id of the request and returns the status.
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, VasPermission)

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

    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, VasPermission)

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

    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, VasPermission)

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
            debit_response = Account.Debit(
                amount=user_data["amount"], reason="Debit for Tv subscription"
            )
            if debit_response == 200:
                serializer = self.serializer_class(data=user_data)
                if serializer.is_valid(raise_exception=True):
                    new_tv_response = VAS.newTvSub(
                        service_id=user_data["serviceID"],
                        amount=user_data["amount"],
                        phone=user_data["phone"],
                        billersCode=user_data["billersCode"],
                        variation_code=user_data["variation_code"],
                        subscription_type=user_data["subscription_type"],
                        quantity=user_data["quantity"]
                    )
                    if new_tv_response.status_code == 200:
                        serializer.save()
                        amount = user_data["amount"]

                        if amount >= 100:
                            new_points = Pts.award(amount=amount)
                            try:
                                with transaction.atomic():
                                    tx, _ = TxModel.objects.get_or_create(user=user)
                                    tx.tx_id=new_tv_response.json().get("transactionId")
                                    tx.amount=user_data.get("amount", 0)
                                    tx.description="Debit for tv subscription"
                                    tx.pts=new_points
                                    tx.save()

                                    pts, _ = Pts.objects.get_or_create(user=user)
                                    pts.balance += new_points
                                    pts.transaction = tx
                                    pts.save()

                            except Exception as e:
                                logging.error(f"Database query error: {str(e)}")

                            response_data = {
                                "status": "Success",
                                "message": f"Tv subscription of {amount} was succesful and you have been awarded {new_points} points",
                                "data": new_tv_response.json(),
                            }
                            return Response(
                                data=response_data, status=status.HTTP_200_OK
                            )
                    else:
                        response_data = {
                            "data": new_tv_response.json(),
                            "messsage": "A refund will be issued.",
                        }

                        # initiate a credit refund to the customer after failed transaction.
                        _ = Credit.credit_customer(
                            first_name=user.firstName,
                            lastname=user.lastName,
                            accNo=user.accountNumber,
                            bankCode="103",
                            amount=user["amount"],
                        )
                        return Response(response_data, status=new_tv_response.status_code)
                else:
                    return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            else:
                return Response(data=debit_response.json(), status=debit_response.status_code)


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
            debit_response = Account.Debit(
                amount=user_data["amount"], reason="Debit for Tv subscription"
            )
            if debit_response.status_code == 200:
                serializer = self.serializer_class(data=user_data)
                if serializer.is_valid(raise_exception=True):
                    renew_tv_response = VAS.renewTvSub(
                        service_id=user_data["serviceID"],
                        amount=user_data["amount"],
                        phone=user_data["phone"],
                        billersCode=user_data["billersCode"],
                        subscription_type=user_data["subscription_type"],
                    )
                    if renew_tv_response.status_code == 200:
                        serializer.save()
                        amount = user_data["amount"]

                        if amount >= 100:
                            new_points = Pts.award(amount=amount)
                            try:
                                with transaction.atomic():
                                    tx, _ = TxModel.objects.get_or_create(user=user)
                                    tx.tx_id=renew_tv_response.json().get("transactionId")
                                    tx.amount=user_data.get("amount", 0)
                                    tx.description="Debit for tv subscription"
                                    tx.pts=new_points
                                    tx.save()

                                    pts, _ = Pts.objects.get_or_create(user=user)
                                    pts.balance += new_points
                                    pts.transaction = tx
                                    pts.save()

                            except Exception as e:
                                logging.error(f"Database query error: {str(e)}")

                            response_data = {
                                "status": "Success",
                                "message": f"Tv subscription of {amount} was succesful and you have been awarded {new_points} points",
                                "data": renew_tv_response.json(),
                            }

                            return Response(
                                data=response_data, status=status.HTTP_200_OK
                            )
                    else:
                        response_data = {
                            "data": renew_tv_response.json(),
                            "messsage": "A refund will be issued.",
                        }

                        # initiate a credit refund to the customer after failed transaction.
                        _ = Credit.credit_customer(
                            first_name=user.firstName,
                            lastname=user.lastName,
                            accNo=user.accountNumber,
                            bankCode="103",
                            amount=user["amount"],
                        )
                        return Response(response_data, status=renew_tv_response.status_code)
                else:
                    return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            else:
                return Response(data=debit_response.json(), status=debit_response.status_code)


class GetIntlAirtimeCountryCodes(generics.GenericAPIView):
    """
    GetIntlAirtimeCountryCodes is a GET request handler for retrieving
    available counntry codes for airtime services for worldwide.
    Take note of the country codes as it would be required to
    get airtime products available in that country.
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, VasPermission)

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

    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, VasPermission)

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

    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, VasPermission)

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

    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, VasPermission)

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
            debit_response = Account.Debit(
                amount=user_data["amount"], reason="Debit for international airtime recharge"
            )
            if debit_response == 200:
                serializer = self.serializer_class(data=user_data)
                if serializer.is_valid(raise_exception=True):
                    intl_topup_response = VAS.intl_topup(
                        service_id=user_data["serviceID"],
                        amount=user_data["amount"],
                        phone=user_data["phone"],
                        billersCode=user_data["billersCode"],
                        operator_id=user_data["operator_id"],
                        variation_code=user_data["variation_code"],
                        country_code=user_data["country_code"],
                        email=user_data["email"],
                        product_type_id=user_data["product_type_id"],
                    )
                    if intl_topup_response.status_code == 200:
                        serializer.save()
                        amount = user_data["amount"]
            
                        if amount >= 100:
                            new_points = Pts.award(amount=amount)
                            try:
                                with transaction.atomic():
                                    tx, _ = TxModel.objects.get_or_create(user=user)
                                    tx.tx_id=intl_topup_response.json().get("transactionId")
                                    tx.amount=user_data.get("amount", 0)
                                    tx.description="Debit for tv subscription"
                                    tx.pts=new_points
                                    tx.save()

                                    pts, _ = Pts.objects.get_or_create(user=user)
                                    pts.balance += new_points
                                    pts.transaction = tx
                                    pts.save()

                            except Exception as e:
                                logging.error(f"Database query error: {str(e)}")

                            response_data = {
                                "status": "Success",
                                "message": f"Topup of {amount} was succesful and you have been awarded {new_points} points",
                                "data": intl_topup_response.json(),
                            }

                            return Response(
                                data=response_data, status=status.HTTP_200_OK
                            )
                    else:
                        response_data = {
                            "data": intl_topup_response.json(),
                            "messsage": "A refund will be issued.",
                        }

                        # initiate a credit refund to the customer after failed transaction.
                        _ = Credit.credit_customer(
                            first_name=user.firstName,
                            lastname=user.lastName,
                            accNo=user.accountNumber,
                            bankCode="103",
                            amount=user["amount"],
                        )
                        return Response(data=response_data, status=intl_topup_response.status_code)
                else:
                    return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            else:
                return Response(data=debit_response.json(), status=debit_response.status_code)


class GetWaecVaritaionCodes(generics.RetrieveAPIView):
    """
    GetWaecVaritaionCodes is the GET request handler for
    retrieving the variation codes for WAEC registration.
    Take key note of the variation codes as they
    are required to chose a registration plan.
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, VasPermission)

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
            debit_response = Account.Debit(
                amount=user_data["amount"], reason="Debit for waec registration"
            )
            if debit_response == 200:

                serializer = self.serializer_class(data=user_data)
                if serializer.is_valid(raise_exception=True):
                    waec_response = VAS.waec_reg(
                        service_id=user_data["serviceID"],
                        phone=user_data["phone"],
                        variation_code=user_data["variation_code"],
                        quantity=user_data["quantity"],
                    )
                    if waec_response.status_code == 200:
                        serializer.save()
                        amount = waec_response.json()["amount"]

                        if amount >= 100:
                            new_points = Pts.award(amount=amount)
                            try:
                                with transaction.atomic():
                                    tx, _ = TxModel.objects.get_or_create(user=user)
                                    tx.tx_id=waec_response.json().get["content"]["transactions"]("transactionId")
                                    tx.amount=user_data.get("amount", 0)
                                    tx.description="Debit for tv subscription"
                                    tx.pts=new_points
                                    tx.save()

                                    pts, _ = Pts.objects.get_or_create(user=user)
                                    pts.balance += new_points
                                    pts.transaction = tx
                                    pts.save()

                            except Exception as e:
                                logging.error(f"Database query error: {str(e)}")

                            response_data = {
                                "status": "Success",
                                "message": f"Waec registration of {amount} was succesful and you have been awarded {new_points} points",
                                "data": waec_response.json(),
                            }

                            return Response(
                                data=response_data, status=status.HTTP_200_OK
                            )
                    else:
                        response_data = {
                            "data": waec_response.json(),
                            "messsage": "A refund will be issued.",
                        }

                        # initiate a credit refund to the customer after failed transaction.
                        _ = Credit.credit_customer(
                            first_name=user.firstName,
                            lastname=user.lastName,
                            accNo=user.accountNumber,
                            bankCode="103",
                            amount=user["amount"],
                        )
                        return Response(response_data, status=waec_response.status_code)
                else:
                    return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            else:
                return Response(data=debit_response.json(), status=debit_response.status_code)


class GetVehicleInsuranceVaritaionCodes(generics.RetrieveAPIView):
    """
    GetVehicleInsuranceVaritaionCodes is the GET request handler for
    retrieving the variation codes for vehicle insurance.
    Take key note of the variation codes as they
    are required to create an accident insurance.
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, VasPermission)

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


class VehicleInsurance(generics.GenericAPIView):
    """
    VehicleInsurance is the POST request handler for creating
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
            debit_response = Account.Debit(
                amount=user_data["amount"], reason="Debit for vehicle insurance"
            )

            if debit_response.status_code == 200:

                serializer = self.serializer_class(data=user_data)
                if serializer.is_valid(raise_exception=True):
                    vehicle_insurance_response = VAS.vehicle_insurance(
                        service_id=user_data["serviceID"],
                        phone=user_data["phone"],
                        variation_code=user_data["variation_code"],
                        billersCode=user_data["variation_code"],
                        Insured_Name=user_data["Insured_Name"],
                        Engine_Number=user_data["Engine_Number"],
                        Chasis_Number=user_data["Chasis_Number"],
                        Plate_Number=user_data["Plate_Number"],
                        Vehicle_Make=user_data["Vehicle_Make"],
                        Vehicle_Color=user_data["Vehicle_Color"],
                        Vehicle_Model=user_data["Vehicle_Model"],
                        Year_of_Make=user_data["Year_of_Make"],
                        Contact_Address=user_data["Contact_Address"],
                    )
                    if vehicle_insurance_response.status_code == 200:
                        serializer.save()
                        amount = vehicle_insurance_response.json()["amount"]

                        if amount >= 100:
                            new_points = Pts.award(amount=amount)
                            try:
                                with transaction.atomic():
                                    tx, _ = TxModel.objects.get_or_create(user=user)
                                    tx.tx_id=vehicle_insurance_response.json().get["content"]["transactions"]("transactionId")
                                    tx.amount=user_data.get("amount", 0)
                                    tx.description="Debit for tv subscription"
                                    tx.pts=new_points
                                    tx.save()

                                    pts, _ = Pts.objects.get_or_create(user=user)
                                    pts.balance += new_points
                                    pts.transaction = tx
                                    pts.save()

                            except Exception as e:
                                logging.error(f"Database query error: {str(e)}")

                            response_data = {
                                "status": "Success",
                                "message": f"Vehicle insurance of {amount} was succesful and you have been awarded {new_points} points",
                                "data": vehicle_insurance_response.json(),
                            }

                            return Response(
                                data=response_data, status=status.HTTP_200_OK
                            )
                    else:
                        response_data = {
                            "data": vehicle_insurance_response.json(),
                            "messsage": "A refund will be issued.",
                        }

                        # initiate a credit refund to the customer after failed transaction.
                        _ = Credit.credit_customer(
                            first_name=user.firstName,
                            lastname=user.lastName,
                            accNo=user.accountNumber,
                            bankCode="103",
                            amount=user["amount"],
                        )
                        return Response(data=response_data, status=vehicle_insurance_response.status_code)
                else:
                    return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            else:
                return Response(data=debit_response.json(), status=debit_response.status_code)


class GetAccidentVaritaionCodes(generics.RetrieveAPIView):
    """
    GetAccidentVaritaionCodes is the GET request handler for retrieving the variation codes for
    accident insurance. Take key note of the variation codes as they
    are required to create an accident insurance.
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, VasPermission)

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


class AccidentInsurance(generics.GenericAPIView):
    """
    AccidentInsurance is the POST request handler for creating
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
            debit_response = Account.Debit(
                amount=user_data["amount"], reason="Debit for accident inssurance"
            )

            if debit_response.status_code == 200:
                serializer = self.serializer_class(data=user)
                if serializer.is_valid(raise_exception=True):
                    accident_insurance_response = VAS.accident_insurance(
                        service_id=user_data["serviceID"],
                        phone=user_data["phone"],
                        variation_code=user_data["variation_code"],
                        billersCode=user_data["variation_code"],
                        phone_no=user_data["phone"],
                        full_name=user_data["full_name"],
                        address=user_data["address"],
                        dob=user_data["dob"],
                        next_kin_name=user_data["next_kin_name"],
                        next_kin_phone=user_data["next_kin_phone"],
                        business_occupation=user_data["business_occupation"],
                    )
                    if accident_insurance_response.status_code == 200:
                        serializer.save()
                        amount = accident_insurance_response.json()["amount"]

                        if amount >= 100:
                            new_points = Pts.award(amount=amount)
                            try:
                                with transaction.atomic():
                                    tx, _ = TxModel.objects.get_or_create(user=user)
                                    tx.tx_id=accident_insurance_response.json().get["content"]["transactions"]("transactionId")
                                    tx.amount=user_data.get("amount", 0)
                                    tx.description="Debit for tv subscription"
                                    tx.pts=new_points
                                    tx.save()

                                    pts, _ = Pts.objects.get_or_create(user=user)
                                    pts.balance += new_points
                                    pts.transaction = tx
                                    pts.save()

                            except Exception as e:
                                logging.error(f"Database query error: {str(e)}")

                            response_data = {
                                "status": "Success",
                                "message": f"Accident insurance of {amount} was succesful and you have been awarded {new_points} points",
                                "data": accident_insurance_response.json(),
                            }
                            return Response(
                                data=response_data, status=status.HTTP_200_OK
                            )
                    else:
                        response_data = {
                            "data": accident_insurance_response.json(),
                            "messsage": "A refund will be issued.",
                        }

                        # initiate a credit refund to the customer after failed transaction.
                        _ = Credit.credit_customer(
                            first_name=user.firstName,
                            lastname=user.lastName,
                            accNo=user.accountNumber,
                            bankCode="103",
                            amount=user["amount"],
                        )
                        return Response(response_data, status=accident_insurance_response.status_code)
                else:
                    return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            else:
                return Response(data=debit_response.json(), status=debit_response.status_code)


class GetHomeCoverVaritaionCodes(generics.RetrieveAPIView):
    """
    GetHomeCoverVaritaionCodes is the GET request handler for
    retrieving the variation codes fora home cover insurance.
    Take key note of the variation codes as they
    are required to create a home cover insurance.
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, VasPermission)

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


class HomeCoverInsurance(generics.GenericAPIView):
    """
    HomeCoverInsurance is the POST request handler for creating
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
            debit_response = Account.Debit(
                amount=user["amount"], reason="Debit for home cover insurance registration"
            )

            if debit_response.status_code == 200:
                serializer = self.serializer_class(data=user)
                if serializer.is_valid(raise_exception=True):
                    home_cover_insurance_response = VAS.home_cover_insurance(
                        service_id=user_data["serviceID"],
                        phone=user_data["phone"],
                        variation_code=user_data["variation_code"],
                        billersCode=user_data["variation_code"],
                        phone_no=user_data["phone"],
                        full_name=user_data["full_name"],
                        address=user_data["address"],
                        dob=user_data["date_of_birth"],
                        type_building=user_data["type_building"],
                        business_occupation=user_data["business_occupation"],
                    )
                    if home_cover_insurance_response.status_code == 200:
                        serializer.save()
                        amount = home_cover_insurance_response.json()["amount"]

                        if amount >= 100:
                            new_points = Pts.award(amount=amount)
                            try:
                                with transaction.atomic():
                                    tx, _ = TxModel.objects.get_or_create(user=user)
                                    tx.tx_id=HomeCoverInsurance.json().get["content"]["transactions"]("transactionId")
                                    tx.amount=user_data.get("amount", 0)
                                    tx.description="Debit for tv subscription"
                                    tx.pts=new_points
                                    tx.save()

                                    pts, _ = Pts.objects.get_or_create(user=user)
                                    pts.balance += new_points
                                    pts.transaction = tx
                                    pts.save()
                            except Exception as e:
                                logging.error(f"Database query error: {str(e)}")

                            response_data = {
                                "status": "Success",
                                "message": f"Home cover insurance of {amount} was succesful and you have been awarded {new_points} points",
                                "data": response.json(),
                            }

                            return Response(
                                data=response_data, status=status.HTTP_200_OK
                            )
                    else:
                        response_data = {
                            "data": response.json(),
                            "messsage": "A refund will be issued.",
                        }

                        # initiate a credit refund to the customer after failed transaction.
                        credit_response = Account.Credit(
                            acct_no=user.accountNumber,
                            amount=user["amount"],
                            reason="Refund for failed home cover insurance."
                        )
                        if credit_response.status_code == 200:
                            response = {
                                "data": response.json(),
                                "messsage": "Wallet refunded.",
                            }
                            return Response(data=response, status=credit_response.status_code)
                        else:
                            return Response(data="A refund will be issued shortly", status=credit_response.status_code)
                else:
                    return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            else:
                return Response(data=debit_response.json(), status=debit_response.status_code)

