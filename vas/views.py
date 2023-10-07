from datetime import datetime
import requests
from decouple import config

from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication


from .serializers import AirtimeTopupSerilizers, DataSubscriptionSerilizers


vtpass_url = config("VT_PASS_BASE_URL")
x_secret = config("VT_PASS_SECRET_KEY")
api_key = config("VT_PASS_API_KEY")
x_token = config("VT_PASS_PUBLIC_KEY")


class AirTimeTopUp(generics.GenericAPIView):
    serializer_class = AirtimeTopupSerilizers
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


class GetVaritaionCodes(generics.RetrieveAPIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

    def get(self, request, *args, **kwargs):
        user = self.request.user  # Get the authenticated user.

        param_value = kwargs.get("service_ID")

        if user:
            resource = "service-variations?serviceID=" + param_value
            fetch_all_variation_Codes = {
                "accept": "application/json",
                "api-key": api_key,
                "secret-key": x_secret,
            }
            try:
                response = requests.get(
                    url=vtpass_url + resource,
                    headers=fetch_all_variation_Codes,
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
    serializer_class = DataSubscriptionSerilizers
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
