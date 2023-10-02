import requests
from decouple import config

from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication


# Third party imports.
from .serializers import (
    CreateWalletSerializer,
    BankAcccPayoutSerializers,
    FincraPayoutSerializers,
)


api_key = config("FINCRA_API_KEY")
bus_key = config("PICADIALYS_BUSINESS_KEY")

fincra_base_url = config("FINCRA_BASE_URL")

bus_id = config("PICADIALYS_BUSINESS_ID")

wallet_no = config("WALLET_NUMBER")


class VitualAccountRequest(generics.CreateAPIView):
    serializer_class = CreateWalletSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        acc_type = self.request.user

        if acc_type.account_type == "User":
            return Response(
                data="error: only partners and members can create wallets",
                status=status.HTTP_401_UNAUTHORIZED,
            )

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

        param_value = kwargs.get("acc_id")

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


class FetchAllBanks(generics.RetrieveAPIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        user = self.request.user  # Get the authenticated user.

        if user:
            resource = "core/banks?"
            fetch_all_banks_headers = {
                "accept": "application/json",
                "api-key": api_key,
                "content-type": "application/json",
            }
            try:
                response = requests.get(
                    url=fincra_base_url + resource, headers=fetch_all_banks_headers
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


class GetParentDetails(generics.RetrieveAPIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        user = self.request.user  # Get the authenticated user.

        if user:
            resource = "profile/merchants/me"
            get_parent_details_headers = {
                "accept": "application/json",
                "api-key": api_key,
            }

            try:
                response = requests.get(
                    url=fincra_base_url + resource, headers=get_parent_details_headers
                )
                if response.status_code == 200:
                    response_data = {
                        "data": response.json(),
                    }

                    return Response(data=response_data, status=status.HTTP_200_OK)
            except requests.exceptions.RequestException as e:
                return Response(
                    {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )


class BankPayouts(generics.GenericAPIView):
    serializer_class = BankAcccPayoutSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        user = request.data

        resource = "disbursements/payouts"
        banks_payouts_headers = {
            "accept": "application/json",
            "api-key": api_key,
            "content-type": "application/json",
        }
        payload = {
            "business": bus_id,
            "sourceCurrency": "NGN",
            "destinationCurrency": "NGN",
            "amount": user["amount"],
            "description": user["description"],
            "customerReference": user["customerReference"],
            "beneficiary": {
                "firstName": user["firstName"],
                "lastName": user["lastName"],
                "accountHolderName": user["firstName"] + " " + user["lastName"],
                "accountNumber": user["accountNumber"],
                "type": "individual",
                "bankCode": user["bankCode"],
            },
            "paymentDestination": "bank_account",
        }
        serializer = self.serializer_class(data=user)
        if serializer.is_valid(raise_exception=True):
            serializer.save()
            try:
                response = requests.post(
                    url=fincra_base_url + resource,
                    json=payload,
                    headers=banks_payouts_headers,
                )

                if response.status_code == 200:
                    response_data = {
                        "message": "Transaction successful",
                        "data": response.json(),
                    }

                    return Response(data=response_data, status=status.HTTP_201_CREATED)
                else:
                    return Response(response.json(), status=response.status_code)

            except requests.exceptions.RequestException as e:
                return Response(
                    {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )


class FetchAllBalances(generics.RetrieveAPIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

    def get(self, request, *args, **kwargs):
        user = self.request.user  # Get the authenticated user.

        param_value = kwargs.get("bus_id")

        if user:
            resource = "wallets/" + param_value
            fetch_all_balancess_headers = {
                "accept": "application/json",
                "api-key": api_key,
            }
            try:
                response = requests.get(
                    url=fincra_base_url + resource, headers=fetch_all_balancess_headers
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


class FincraPayouts(generics.GenericAPIView):
    serializer_class = FincraPayoutSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        user = request.data

        resource = "disbursements/payouts/wallets"
        fincra_payouts_headers = {
            "accept": "application/json",
            "api-key": api_key,
            "content-type": "application/json",
        }
        payload = {
            "business": bus_id,
            "amount": user["amount"],
            "description": user["description"],
            "customerReference": user["customerReference"],
            "beneficiaryWalletNumber": wallet_no,
        }
        serializer = self.serializer_class(data=user)
        if serializer.is_valid(raise_exception=True):
            serializer.save()
            try:
                response = requests.post(
                    url=fincra_base_url + resource,
                    json=payload,
                    headers=fincra_payouts_headers,
                )

                if response.status_code == 200:
                    response_data = {
                        "message": "Transaction succesful",
                        "data": response.json(),
                    }

                    return Response(data=response_data, status=status.HTTP_201_CREATED)
                else:
                    return Response(response.json(), status=response.status_code)

            except requests.exceptions.RequestException as e:
                return Response(
                    {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
