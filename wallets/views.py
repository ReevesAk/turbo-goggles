import requests
from decouple import config
import json

from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication

# In-projects imports.
from .serializers import (
    CreateWalletSerializer,
    BankAcccPayoutSerializers,
    FincraPayoutSerializers,
    PicadailysPayoutSerializers,
    BVNSerializer,
    ResetPinSerializer,
)
from .models import CreateWallet, BVNData
from .helpers import generate_random_string, insert_hyphens
from .controllers import BVN, Pin
from permissions import IsPartnerOrMember
from accounts.otp import otp_manager
from accounts.serializers import VerifyOTPSerializer
from commons import Message


random_string = generate_random_string(20)
customer_reference = insert_hyphens(random_string, 4)


api_key = config("FINCRA_API_KEY")
api_secret_key = config("FINCRA_SECRET_KEY")
bus_key = config("PICADIALYS_BUSINESS_KEY")

fincra_base_url = config("FINCRA_BASE_URL")

bus_id = config("PICADIALYS_BUSINESS_ID")

wallet_no = config("WALLET_NUMBER")


class VerifYBVN(generics.CreateAPIView):
    serializer_class = BVNSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsPartnerOrMember)

    def create(self, request):
        user_data = request.data
        authenticated_user = request.user

        if authenticated_user.is_bvn_verified:
            bvn_deets = BVNData.objects.filter(user=authenticated_user).first()
            data = {
                "First Name": bvn_deets.first_name,
                "Last Name": bvn_deets.last_name,
                "phone_no": bvn_deets.phone_number,
                "Date of Birth": bvn_deets.date_of_birth,
                "bvn": user_data.get("bvn"),
            }
            return Response(
                data={"message": "User has already verified BVN", "Bvn data": data},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            bvn = BVNData.objects.get(user=authenticated_user)
        except BVNData.DoesNotExist:
            bvn = BVNData.objects.create(user=authenticated_user)

        # Verify the user's BVN.
        bvn_data = BVN.verify(bvn=user_data.get("bvn"))
        if bvn_data is None:
            return Response(
                data={"message": "Bvn provided does not exist"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check if the user's date of birth and phone number match the ones on BVN.
        if (
            user_data.get("date_of_birth") != bvn_data["date_of_birth"]
            or user_data.get("phone_number") != bvn_data["phone_num"]
        ):
            return Response(
                data={
                    "message": "Date of birth or phone number provided does not match the one on bvn"
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Update the user's BVN instance with the new data.
        bvn.first_name = bvn_data["first_name"]
        bvn.last_name = bvn_data["last_name"]
        bvn.date_of_birth = bvn_data["date_of_birth"]
        bvn.phone_number = bvn_data["phone_num"]
        bvn.number = user_data.get("bvn")
        bvn.save()

        authenticated_user.is_bvn_verified = True
        authenticated_user.save()

        serializer = BVNSerializer(data=user_data)

        response = {
            "status": "Success",
            "message": "Bvn verification was successful",
            "Bvn data": serializer.data,
        }
        return Response(data=response, status=status.HTTP_201_CREATED)


class VitualAccountRequest(generics.GenericAPIView):
    serializer_class = CreateWalletSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsPartnerOrMember)

    def post(self, request):
        authenticated_user = request.user

        if authenticated_user.is_bvn_verified is False:
            return Response(
                data="error: Your bvn is not verified",
                status=status.HTTP_401_UNAUTHORIZED,
            )

        bvn = BVNData.objects.get(user=authenticated_user)
        received_user_data = request.data

        create_account_headers = {
            "accept": "application/json",
            "content-Type": "application/json",
            "api-key": api_secret_key,
        }

        wallet_exist = CreateWallet.objects.filter(user=authenticated_user).first()
        if wallet_exist:
            existing_wallet_data = {
                "id": wallet_exist.id,
                "virtualAccountId": wallet_exist.virtualAccountId,
                "currency": wallet_exist.currency,
                "channel": wallet_exist.bankName,
                "accountNumber": wallet_exist.accountNumber,
                "accountInformation": wallet_exist.accountInformation,
                "first_name": wallet_exist.first_name,
                "last_name": wallet_exist.last_name,
                "accountType": wallet_exist.accountType,
            }
            response_data = {
                "message": "A wallet with this BVN already exists",
                "data": existing_wallet_data,
            }
            return Response(data=response_data, status=status.HTTP_400_BAD_REQUEST)

        resource = "profile/virtual-accounts/requests/"
        payload = {
            "currency": "NGN",
            "channel": "globus",
            "KYCInformation": {
                "firstName": bvn.first_name,
                "lastName": bvn.last_name,
                "bvn": bvn.number,
            },
            "accountType": "individual",
        }

        serializer = self.serializer_class(data=received_user_data)
        if serializer.is_valid(raise_exception=True):
            serializer.save()
            try:
                response = requests.post(
                    url=fincra_base_url + resource,
                    json=payload,
                    headers=create_account_headers,
                )
                try:
                    # Check if the response contains valid JSON
                    response.json()
                except json.JSONDecodeError:
                    # If JSON parsing fails, handle the error as needed
                    return Response(
                        {"error": "Invalid JSON response from the external API"},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    )

                if response.status_code == 200:
                    account_detials = CreateWallet.objects.create(
                        user=authenticated_user
                    )
                    account_detials.virtualAccountId = response.json()["data"]["_id"]
                    account_detials.first_name = response.json()["data"][
                        "KYCInformation"
                    ]["firstName"]
                    account_detials.last_name = response.json()["data"][
                        "KYCInformation"
                    ]["lastName"]
                    account_detials.accountNumber = response.json()["data"][
                        "accountNumber"
                    ]
                    account_detials.currency = response.json()["data"]["currency"]
                    account_detials.bankName = response.json()["data"][
                        "accountInformation"
                    ]["bankName"]
                    account_detials.accountInformation = response.json()["data"][
                        "accountInformation"
                    ]
                    account_detials.accountType = response.json()["data"]["accountType"]
                    account_detials.save()
                    response_data = {
                        "message": "Virtual account created successfully",
                        "data": response.json(),
                    }

                    return Response(data=response_data, status=status.HTTP_200_OK)
                else:
                    return Response(response.json(), status=response.status_code)

            except requests.exceptions.RequestException as e:
                return Response(
                    {"error": str(e)},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )


class SetWalletPin(generics.CreateAPIView):
    serializer_class = CreateWalletSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsPartnerOrMember)

    def create(self, request, *args, **kwargs):
        user_data = request.data
        authenticated_user = request.user

        try:
            user = CreateWallet.objects.get(user=authenticated_user)
        except CreateWallet.DoesNotExist:
            return Response(
                data={"error": "Wallet not found for the authenticated user."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = self.serializer_class(data=user_data)
        if serializer.is_valid(raise_exception=True):
            pin = user_data.get("pin")
            pin2 = user_data.get("pin2")

            if pin != pin2:
                return Response(
                    data={"error": "Pins do not match!"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # set the pin and save it in a 'pin' flag on the db.
            user.pin = pin
            user.save()

            response = {
                "status": "Success!",
                "message": "Wallet pin created succesfully!",
            }
            return Response(data=response, status=status.HTTP_201_CREATED)


class ForgotWalletPin(generics.GenericAPIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsPartnerOrMember)

    def post(self, request):
        user = request.user
        phone_no = user.phone_number
        # Create and send OTP.
        otp = otp_manager.create_otp(user_id=str(user.id))
        msg = "Enter this OTP {} to verify your account and reset your pin".format(otp)

        response = Message.send_otp(msg=str(msg), to=phone_no)
        if response.status_code == 200:
            try:
                response = {
                    "status": "success",
                    "message": "Check your phone for an OTP",
                }
                return Response(data=response, status=status.HTTP_201_CREATED)
            except Exception as err:
                return Response(
                    {
                        "status": "fail",
                        "message": err,
                    },
                    status=status.HTTP_409_CONFLICT,
                )
        else:
            return Response(data=response, status=response.status_code)


class PinResendOTP(generics.GenericAPIView):
    """
    PinResendOTP handles the POST request of resending an
    OTP to a user.
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsPartnerOrMember)

    def post(self, request):
        user = request.user
        phone_number = user.phone_number

        # Generate otp.
        otp = otp_manager.create_otp(user_id=str(user.id))
        msg = "To reset your pin, please enter this One Time Password {}.".format(otp)

        response = Message.send_otp(msg=str(msg), to=phone_number)
        if response.status_code == 200:
            response = {
                "status": "success",
                "message": "Otp resent Successfully. Check your phone for validation",
            }
            return Response(data=response, status=status.HTTP_200_OK)
        else:
            return Response(data=response, status=response.status_code)


class PinVerifyOTP(generics.GenericAPIView):
    serializer_class = VerifyOTPSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsPartnerOrMember)

    def post(self, request):
        user = request.data
        user_data = request.user
        serializer = self.serializer_class(data=user)
        if serializer.is_valid(raise_exception=True):
            received_otp = serializer.data["otp"]

            # Validate otp.
            user_id = otp_manager.validate_user_otp(received_otp)

            if not user_id:
                return Response(
                    data={"error": "Invalid or expired OTP"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Send welcome message to user.
            msg = "User is verified... You can reset now your pin!"
            recipient = user_data.phone_number

            response = Message.send_msg(msg=str(msg), to=recipient)
            if response.status_code == 200:
                return Response(
                    {"Success": "Account is verified"}, status=status.HTTP_200_OK
                )


class ResetPin(generics.CreateAPIView):
    serializer_class = ResetPinSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsPartnerOrMember)

    def create(self, request):
        authenticated_user = request.user
        user_data = request.data
        serializer = self.get_serializer(data=request.data)

        try:
            user = CreateWallet.objects.get(user=authenticated_user)
        except CreateWallet.DoesNotExist:
            return Response(
                data={"error": "Wallet not found for the authenticated user."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if serializer.is_valid(raise_exception=True):
            otp = user_data["otp"]
            user_id = otp_manager.validate_user_otp(otp=otp)

            if not user_id:
                return Response(
                    data={"error": "Invalid or expired OTP"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            pin = user_data.get("pin")
            pin2 = user_data.get("pin2")

            if pin != pin2:
                return Response(
                    data={"error": "Pins do not match!"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            user.pin = pin
            user.save()

            response = {"status": "Success!", "message": "Pin reset successfully"}
            return Response(data=response, status=status.HTTP_200_OK)
        else:
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)


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
            "customerReference": customer_reference,
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
            authenticated_user = request.user
            pin = request.data.get("pin")

            verification = Pin.verify_pin(user=authenticated_user, pin=pin)
            if verification:
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

                        return Response(data=response_data, status=status.HTTP_200_OK)
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
            authenticated_user = request.user
            pin = request.data.get("pin")

            verification = Pin.verify_pin(user=authenticated_user, pin=pin)
            if verification:
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

                        return Response(data=response_data, status=status.HTTP_200_OK)
                    else:
                        return Response(response.json(), status=response.status_code)

                except requests.exceptions.RequestException as e:
                    return Response(
                        {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )


class PicadailysTransfers(generics.GenericAPIView):
    serializer_class = PicadailysPayoutSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        user = request.data

        if user:
            resource = "profile/virtual-accounts/" + user["virtualAccountId"]
            retrieve_account_headers = {
                "accept": "application/json",
                "api-key": api_key,
            }
            try:
                response = requests.get(
                    url=fincra_base_url + resource, headers=retrieve_account_headers
                )

                if response.status_code == 200:
                    resp = response.json()["data"]

                    resource = "disbursements/payouts"
                    picadailys_payouts_headers = {
                        "accept": "application/json",
                        "api-key": api_key,
                        "content-type": "application/json",
                    }
                    f_name = resp["KYCInformation"]["firstName"]
                    l_name = resp["KYCInformation"]["lastName"]
                    payload = {
                        "business": bus_id,
                        "sourceCurrency": "NGN",
                        "destinationCurrency": "NGN",
                        "amount": user["amount"],
                        "description": user["description"],
                        "customerReference": customer_reference,
                        "beneficiary": {
                            "firstName": resp["KYCInformation"]["firstName"],
                            "lastName": resp["KYCInformation"]["lastName"],
                            "accountHolderName": f_name + l_name,
                            "accountNumber": resp["accountNumber"],
                            "type": "individual",
                            "bankCode": "103",
                        },
                        "paymentDestination": "bank_account",
                    }
                    serializer = self.serializer_class(data=user)
                    if serializer.is_valid(raise_exception=True):
                        authenticated_user = request.user
                        pin = request.data.get("pin")

                        verification = Pin.verify_pin(user=authenticated_user, pin=pin)
                        if verification:
                            serializer.save()
                            try:
                                response = requests.post(
                                    url=fincra_base_url + resource,
                                    json=payload,
                                    headers=picadailys_payouts_headers,
                                )

                                if response.status_code == 200:
                                    response_data = {
                                        "message": "Transaction successful",
                                        "data": response.json(),
                                    }
                                    return Response(
                                        data=response_data, status=status.HTTP_200_OK
                                    )
                                else:
                                    return Response(
                                        response.json(), status=response.status_code
                                    )

                            except requests.exceptions.RequestException as e:
                                return Response(
                                    {"error": str(e)},
                                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                )
            except requests.exceptions.RequestException as e:
                return Response(
                    {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
