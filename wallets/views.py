import requests
from decouple import config

from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication


# Third party imports.
from .serializers import CreateWalletSerializer


api_key = config("FINCRA_API_KEY")

fincra_base_url = config("FINCRA_BASE_URL")


class VitualAccountRequest(generics.CreateAPIView):
    serializer_class = CreateWalletSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        user = request.data

        user["currency"] = "NGN"
        user["accountType"] = "individual"
        user["channel"] = "providus"

        resource = "profile/virtual-accounts/requests"
        payload = {
            "currency": "NGN",
            "channel": "providus",
            "KYCInformation": {
                "firstName": user["first_name"],
                "lastName": user["last_name"],
                "bvn": user["bvn"],
            },
            "accountType": "individual",
        }

        create_account_headers = {
            "accept": "application/json",
            "content-Type": "application/json",
            "api-key": api_key,
        }

        serializer = self.serializer_class(data=user)
        if serializer.is_valid(raise_exception=True):
            serializer.save()
            try:
                response = requests.post(
                    url=fincra_base_url + resource,
                    json=payload,
                    headers=create_account_headers,
                )

                if response.status_code == 200:
                    response_data = {
                        "message": "Virtual account created successfully",
                        "data": response.json(),
                    }

                    return Response(data=response_data, status=status.HTTP_201_CREATED)
                else:
                    return Response(response.json(), status=response.status_code)

            except requests.exceptions.RequestException as e:
                return Response(
                    {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )


class AccountDetails(generics.RetrieveAPIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

    def get(self, request, *args, **kwargs):
        user = self.request.user  # Get the authenticated user

        param_value = kwargs.get('acc_id')

        if user:
            resource = "profile/virtual-accounts/" + param_value
            retrieve_account_headers = {
                "accept": "application/json",
                "api-key": api_key,
            }
            try:
                response = requests.get(
                    url=fincra_base_url + resource, headers=retrieve_account_headers
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
