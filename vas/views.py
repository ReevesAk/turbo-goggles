from datetime import datetime
import requests
from decouple import config

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
)
from wallets.views import Debit

vtpass_url = config("VT_PASS_BASE_URL")
x_secret = config("VT_PASS_SECRET_KEY")
api_key = config("VT_PASS_API_KEY")
x_token = config("VT_PASS_PUBLIC_KEY")


class AirTimeTopUp(generics.GenericAPIView):
    serializer_class = AirtimeTopupSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        user = request.data

        current_datetime = datetime.now()
        res_id = current_datetime.strftime("%Y%m%d%H%M" + "picadailys")

        resource = "pay"
        payload = {
            "request_id": res_id,
            "serviceID": user["serviceID"],
            "amount": user["amount"],
            "phone": user["phone"],
        }

        debit_response = Debit.debit_customer(
            amount=user["amount"], description="Debit for airtime recharge"
        )
        if debit_response == 200:
            airtime_headers = {"secret-key": x_secret, "api-key": api_key}

            serializer = self.serializer_class(data=user)
            if serializer.is_valid(raise_exception=True):
                serializer.save()
                try:
                    response = requests.post(
                        url=vtpass_url + resource,
                        json=payload,
                        headers=airtime_headers,
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


class GetNetworkProvidersVaritaionCodes(generics.RetrieveAPIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

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
    serializer_class = DataSubscriptionSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        user = request.data

        current_datetime = datetime.now()
        res_id = current_datetime.strftime("%Y%m%d%H%M" + "picadailys")

        resource = "pay"
        payload = {
            "request_id": res_id,
            "serviceID": user["serviceID"],
            "amount": user["amount"],
            "phone": user["phone"],
            "billersCode": user["billersCode"],
            "variation_code": user["variation_code"],
        }

        debit_response = Debit.debit_customer(
            amount=user["amount"], description="Debit for data subscription"
        )
        if debit_response == 200:
            data_headers = {
                "secret-key": x_secret,
                "api-key": api_key,
                "secret-key": x_secret,
            }

            serializer = self.serializer_class(data=user)
            if serializer.is_valid(raise_exception=True):
                serializer.save()
                try:
                    response = requests.post(
                        url=vtpass_url + resource,
                        json=payload,
                        headers=data_headers,
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


class VerifyMeterNumber(generics.RetrieveAPIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

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
    serializer_class = ElectricityBillSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        user = request.data

        current_datetime = datetime.now()
        res_id = current_datetime.strftime("%Y%m%d%H%M" + "picadailys")

        resource = "pay"
        payload = {
            "request_id": res_id,
            "serviceID": user["serviceID"],
            "billersCode": user["billersCode"],
            "amount": user["amount"],
            "phone": user["phone"],
            "variation_code": user["variation_code"],
        }
        debit_response = Debit.debit_customer(
            amount=user["amount"], description="Debit for electricity bill payment"
        )
        if debit_response == 200:
            electricty_bill_headers = {"secret-key": x_secret, "api-key": api_key}

            serializer = self.serializer_class(data=user)
            if serializer.is_valid(raise_exception=True):
                serializer.save()
                try:
                    response = requests.post(
                        url=vtpass_url + resource,
                        json=payload,
                        headers=electricty_bill_headers,
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


class ProductStatus(generics.RetrieveAPIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

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
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

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
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

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
    serializer_class = TvSubscriptionSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        user = request.data

        current_datetime = datetime.now()
        res_id = current_datetime.strftime("%Y%m%d%H%M" + "picadailys")

        resource = "pay"
        payload = {
            "request_id": res_id,
            "serviceID": user["serviceID"],
            "amount": user["amount"],
            "phone": user["phone"],
            "billersCode": user["billersCode"],
            "subscription_type": user["subscription_type"],
            "quantity": user["quantity"],
            "variation_code": user["variation_code"],
        }
        tv_sub_headers = {
            "secret-key": x_secret,
            "api-key": api_key,
            "secret-key": x_secret,
        }

        serializer = self.serializer_class(data=user)
        if serializer.is_valid(raise_exception=True):
            serializer.save()
            try:
                response = requests.post(
                    url=vtpass_url + resource,
                    json=payload,
                    headers=tv_sub_headers,
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


class RenewTvSubscription(generics.GenericAPIView):
    serializer_class = TvSubscriptionSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        user = request.data

        current_datetime = datetime.now()
        res_id = current_datetime.strftime("%Y%m%d%H%M" + "picadailys")

        resource = "pay"
        payload = {
            "request_id": res_id,
            "serviceID": user["serviceID"],
            "amount": user["amount"],
            "phone": user["phone"],
            "billersCode": user["billersCode"],
            "subscription_type": user["subscription_type"],
        }
        renew_tv_sub_headers = {
            "secret-key": x_secret,
            "api-key": api_key,
            "secret-key": x_secret,
        }

        serializer = self.serializer_class(data=user)
        if serializer.is_valid(raise_exception=True):
            serializer.save()
            try:
                response = requests.post(
                    url=vtpass_url + resource,
                    json=payload,
                    headers=renew_tv_sub_headers,
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


class GetIntlAirtimeCountryCodes(generics.GenericAPIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        user = request.user

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
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

    def get(self, request, *args, **kwargs):
        user = request.user

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
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

    def get(self, request, *args, **kwargs):
        user = request.user

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
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

    def get(self, request, *args, **kwargs):
        user = request.user

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
    serializer_class = IntlAirtimeSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        user = request.data

        current_datetime = datetime.now()
        res_id = current_datetime.strftime("%Y%m%d%H%M" + "picadailys")

        resource = "pay"
        payload = {
            "request_id": res_id,
            "serviceID": user["serviceID"],
            "amount": user["amount"],
            "phone": user["phone"],
            "billersCode": user["billersCode"],
            "operator_id": user["operator_id"],
            "variation_code": user["variation_code"],
            "country_code": user["country_code"],
            "email": user["email"],
            "product_type_id": user["product_type_id"],
        }

        debit_response = Debit.debit_customer(
            amount=user["amount"], description="Debit for airtime recharge"
        )
        if debit_response == 200:
            intl_airtime_headers = {"secret-key": x_secret, "api-key": api_key}

            serializer = self.serializer_class(data=user)
            if serializer.is_valid(raise_exception=True):
                serializer.save()
                try:
                    response = requests.post(
                        url=vtpass_url + resource,
                        json=payload,
                        headers=intl_airtime_headers,
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
