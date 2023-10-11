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
    WaecRegistrationSerializer,
    VehicleInsuranceSerializer,
    AccidentInsuranceSerializer,
    HomeCoverInsuranceSerializer,
)
from wallets.views import Debit

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
    """
    GetNetworkProvidersVaritaionCodes is a GET request handler for retrieving variation
    codes of different network providers. It takes in the service_ID(mtn, airtel etc)
    as url param.
    """

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
    """
    DataSubscription is a POST request handler for data
    subscription.
    """

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
    """
    VerifySmartCardNumber is a POST request handler for verifying
    electricity meter number.
    """

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
    """
    ElectrcityBillPayment is a POST request handler for payment of electricity
    bills for both prepaid and postpaid account types.
    """

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
    """
    ProductStatus is the POST request handler for checking the status
    of any Value Added Services product purchased. It takes in the
    request_id of the request and returns the status.
    """

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
    """
    GetTvVaritaionCodes is the GET request handler for retrieving
    the variation codes for tv subscription. Take key note of the
    variation codes as they are required to chose a tv plan.
    """

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
    """
    VerifySmartCardNumber is a POST request handler for verifying smart
    card or registration number for tv operators(e.g dstv, gotv).
    """

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
    """
    NewTvSubscription is a POST request handler for new
    tv plan subscription.
    """

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
    """
    RenewTvSubscription is a POST request handler for
    tv plan subscription renewal.
    """

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
    """
    GetIntlAirtimeCountryCodes is a GET request handler for retrieving
    available counntry codes for airtime services for worldwide.
    Take note of the country codes as it would be required to
    get airtime products available in that country.
    """

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
    """
    GetIntlAirtimeProducts is a GET request handler for retrieving
    airtime products available in the country. The endpoints takes
    the country_code as url params.
    """

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
    """
    GetIntlAirtimeOperators is a GET request handler for retrieving
    airtime operators available in the country. The endpoints takes
    the country_code aas well as product type id as url params.
    Take note of the operator_id and it will be required to get
    the variation codes.
    """

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
    """
    GetIntlAirtimeVaraitionCodes is the GET request handler for retrieving
    the variation codes for international airrtime topup.
    Take key note of the variation codes as they
    are required to chose a registration plan.
    The endpoints takes the operator_id as well as product type id
    as url params.
    """

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
    """
    InternationalAirTimeTopUp is the POST request handler for
    international airtime topup.
    """

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


class GetWaecVaritaionCodes(generics.RetrieveAPIView):
    """
    GetWaecVaritaionCodes is the GET request handler for
    retrieving the variation codes for WAEC registration.
    Take key note of the variation codes as they
    are required to chose a registration plan.
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

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
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        user = request.data

        current_datetime = datetime.now()
        res_id = current_datetime.strftime("%Y%m%d%H%M" + "picadailys")

        resource = "pay"
        payload = {
            "request_id": res_id,
            "serviceID": user["serviceID"],
            "variation_code": user["variation_code"],
            "quantity": user["quantity"],
            "phone": user["phone"],
        }

        debit_response = Debit.debit_customer(
            amount=user["amount"], description="Debit for waec registration"
        )
        if debit_response == 200:
            waec_headers = {"secret-key": x_secret, "api-key": api_key}

            serializer = self.serializer_class(data=user)
            if serializer.is_valid(raise_exception=True):
                serializer.save()
                try:
                    response = requests.post(
                        url=vtpass_url + resource,
                        json=payload,
                        headers=waec_headers,
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


class GetVehicleInsuranceVaritaionCodes(generics.RetrieveAPIView):
    """
    GetVehicleInsuranceVaritaionCodes is the GET request handler for
    retrieving the variation codes for vehicle insurance.
    Take key note of the variation codes as they
    are required to create an accident insurance.
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

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
            "variation_code": user["variation_code"],
            "phone": user["phone"],
            "Insured_Name": user["Insured_Name"],
            "Engine_Number": user["Engine_Number"],
            "Chasis_Number": user["Chasis_Number"],
            "Plate_Number": user["Plate_Number"],
            "Vehicle_Make": user["Vehicle_Make"],
            "Vehicle_Color": user["Vehicle_Color"],
            "Vehicle_Model": user["Vehicle_Model"],
            "Year_of_Make": user["Year_of_Make"],
            "Contact_Address": user["Contact_Address"],
        }
        debit_response = Debit.debit_customer(
            amount=user["amount"], description="Debit for vehicle insurance."
        )

        if debit_response == 200:
            insurance_headers = {"secret-key": x_secret, "api-key": api_key}

            serializer = self.serializer_class(data=user)
            if serializer.is_valid(raise_exception=True):
                serializer.save()
                try:
                    response = requests.post(
                        url=vtpass_url + resource,
                        json=payload,
                        headers=insurance_headers,
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


class GetAccidentVaritaionCodes(generics.RetrieveAPIView):
    """
    GetAccidentVaritaionCodes is the GET request handler for retrieving the variation codes for
    accident insurance. Take key note of the variation codes as they
    are required to create an accident insurance.
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

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
            "variation_code": user["variation_code"],
            "phone": user["phone"],
            "full_name": user["full_name"],
            "address": user["address"],
            "dob": user["dob"],
            "next_kin_name": user["next_kin_name"],
            "next_kin_phone": user["next_kin_phone"],
            "business_occupation": user["business_occupation"],
        }
        debit_response = Debit.debit_customer(
            amount=user["amount"], description="Debit for accident insurance"
        )

        if debit_response == 200:
            insurance_headers = {"secret-key": x_secret, "api-key": api_key}

            serializer = self.serializer_class(data=user)
            if serializer.is_valid(raise_exception=True):
                serializer.save()
                try:
                    response = requests.post(
                        url=vtpass_url + resource,
                        json=payload,
                        headers=insurance_headers,
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


class GetHomeCoverVaritaionCodes(generics.RetrieveAPIView):
    """
    GetHomeCoverVaritaionCodes is the GET request handler for
    retrieving the variation codes fora home cover insurance.
    Take key note of the variation codes as they
    are required to create a home cover insurance.
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

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
            "variation_code": user["variation_code"],
            "phone": user["phone"],
            "full_name": user["full_name"],
            "address": user["address"],
            "date_of_birth": user["date_of_birth"],
            "type_building": user["type_building"],
            "business_occupation": user["business_occupation"],
        }
        debit_response = Debit.debit_customer(
            amount=user["amount"], description="Debit for home cover insurance"
        )

        if debit_response == 200:
            insurance_headers = {"secret-key": x_secret, "api-key": api_key}

            serializer = self.serializer_class(data=user)
            if serializer.is_valid(raise_exception=True):
                serializer.save()
                try:
                    response = requests.post(
                        url=vtpass_url + resource,
                        json=payload,
                        headers=insurance_headers,
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
