import logging
import requests
from decouple import config
from accounts.otp import otp_manager
from permissions import IsPartnerUserOrMember, IsBrandAd
from commons import Message

from django.contrib.auth.hashers import make_password

# Third party imports.
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

# from rest_framework.exceptions import NotFound
from rest_framework.parsers import MultiPartParser, JSONParser
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.pagination import PageNumberPagination

from drf_spectacular.utils import extend_schema

# In-projects imports.
from .serializers import (
    BVNSerializer,
    BankAccountCreationSerializers,
    CreateWalletPinSerializer,
    VerifyPinOTPSerializer,
    ResetPinSerializer,
    BankNtfnSerializer,
    BankingStatusSerializer,
    AccountBalanceSerializer,
)
from accounts.models import UserNotification
from .models import (
    AccountCreation,
    BVNData,
)
from .controllers import BVN, Account


base_url = config("MAPLERAD_BASE_URL")
secret_key = config("MAPLERAD_SECRET_KEY")
headers = {
    "accept": "application/json",
    "content-Type": "application/json",
    "Authorization": "Bearer " + secret_key,
}

picadailys_email = config("EMAIL_HOST_USER")
app_password = config("EMAIL_HOST_PASSWORD")


class PaginationStyle(PageNumberPagination):
    page_size = 20


class VerifYBVN(generics.GenericAPIView):
    """
    VerifYBVN handles the POST request of verifying a
    customer's bvn. It accepts DOB in this format: 30-Dec-1650.
    """

    serializer_class = BVNSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsPartnerUserOrMember)

    def post(self, request):
        user_data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in request.data.items()
        }
        authenticated_user = request.user

        if authenticated_user.is_bvn_verified:
            bvn_deets = BVNData.objects.filter(user=authenticated_user).first()
            data = {
                "First Name": bvn_deets.first_name,
                "Last Name": bvn_deets.last_name,
                "Phone_no": bvn_deets.phone_number,
                "Date of Birth": bvn_deets.date_of_birth,
                "Bvn": user_data.get("bvn"),
            }
            return Response(
                data={
                    "status": "success",
                    "message": "User has already verified BVN",
                    "Bvn data": data,
                },
                status=status.HTTP_202_ACCEPTED,
            )
        try:
            bvn = BVNData.objects.get(user=authenticated_user)
        except BVNData.DoesNotExist:
            bvn = BVNData.objects.create(user=authenticated_user)

        serializer = self.serializer_class(data=user_data)
        if serializer.is_valid(raise_exception=True):
            number = BVNData.objects.filter(bvn=user_data.get("bvn")).exists()
            num = request.data.get("bvn")
            if number:
                return Response(
                    data={
                        "status": "fail",
                        "message": f"User with this bvn: {num} already exist",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            # Verify the user's BVN.
            bvn_response = BVN.verify(bvn=user_data.get("bvn"))
            bvn_status_code = bvn_response.status_code

            if bvn_status_code == 200:
                bvn_data = bvn_response.json()

                # Check if the user's date of birth matches the ones on BVN.
                if all(
                    data != bvn_data[field]
                    for data, field in [
                        (user_data.get("date_of_birth"), "DOB"),
                        (user_data.get("phone_number"), "Phone"),
                    ]
                ):
                    return Response(
                        data={
                            "status": "fail",
                            "message": "Date of birth or phone number provided does not match the one on bvn",
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                # Update the user's BVN instance with the new data.
                bvn.first_name = bvn_data["FirstName"]
                bvn.last_name = bvn_data["LastName"]
                bvn.date_of_birth = bvn_data["DOB"]
                bvn.phone_number = bvn_data["Phone"]
                bvn.number = user_data.get("bvn")
                bvn.save()

                authenticated_user.is_bvn_verified = True
                authenticated_user.save()

                serializer = BVNSerializer(data=user_data)

                UserNotification.objects.create(
                    user=request.user,
                    title="BVN Verification.",
                    message="Your BVN Verifiction is successful.",
                )

                response = {
                    "status": "success",
                    "message": "Bvn verification was successful",
                    "bvn data": {
                        "first_name": bvn_data["FirstName"],
                        "last_name": bvn_data["LastName"],
                        "date_of_birth": bvn_data["DOB"],
                        "phone_number": bvn_data["Phone"],
                        "bvn": user_data.get("bvn"),
                    },
                }
                return Response(data=response, status=status.HTTP_201_CREATED)
            else:
                return Response(data=bvn_response.json(), status=bvn_status_code)
        else:
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class CreateBankAccount(generics.GenericAPIView):
    """
    CreateBankAccount handles the POST request of receiving a
    customer's transaction detail.
    """

    serializer_class = BankAccountCreationSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, (IsPartnerUserOrMember | IsBrandAd))
    parser_classes = (
        MultiPartParser,
        JSONParser,
    )

    def post(self, request):
        payload = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in request.data.items()
        }

        passport = request.FILES.get("passport")
        identity = request.FILES.get("identity")
        utility = request.FILES.get("utility")
        signature = request.FILES.get("signature")

        serializer = BankAccountCreationSerializers(data=payload)
        if not serializer.is_valid():
            logging.error(f"Validation Errors: {serializer.errors}")
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            # _ = BVNData.objects.get(user=request.user)
            acc_response = Account.Open(
                addr=request.data.get("address"),
                tc=request.data.get("tc"),
                acc_type="65",
                religion=request.data.get("religion"),
                ms=request.data.get("ms"),
                gn=request.data.get("gn"),
                branch="203",
                bvn=request.data.get("bvn"),
                state=request.data.get("state"),
                lga=request.data.get("lga"),
                country=request.data.get("country"),
                altEmail=request.data.get("altEmail"),
                altPhone=request.data.get("altPhone"),
                currentAddress=request.data.get("currentAdress"),
                nin=request.data.get("NIN"),
                passport=passport,
                identity=identity,
                utility=utility,
                signature=signature,
            )

            if acc_response.status_code == 200:
                AccountCreation.objects.create(
                    account_number=acc_response.json()["AccountNUBAN"],
                    customer_numnber=acc_response.json()["CustomerNumber"],
                    acct_name=acc_response.json()["AccountName"],
                    sex=request.data.get("gn"),
                    title=request.data.get("tc"),
                    marital_status=request.data.get("ms"),
                    lga=request.data.get("lga"),
                    state=request.data.get("state"),
                    religion=request.data.get("religion"),
                    nin=request.data.get("NIN"),
                    address=request.data.get("address"),
                )
                resp = {
                    "status": "success",
                    "message": "Open Account Operation was successful!",
                    "accountNumber": acc_response.json()["AccountNUBAN"],
                    "accountName": acc_response.json()["AccountName"],
                }
                return Response(data=resp, status=status.HTTP_201_CREATED)
            else:
                return Response(
                    data=acc_response.json(), status=acc_response.status_code
                )
        except requests.exceptions.RequestException as e:
            logging.error(f"Account creation API request error: {str(e)}")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class NotificationView(generics.CreateAPIView):
    """
    NotificationView handles the POST request of receiving a
    customer's transaction detail.
    """

    serializer_class = BankNtfnSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        user_data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in request.data.items()
        }
        account_number = user_data.get("accountNumber")
        transactiontype = user_data.get("transactiontype")
        narration = user_data.get("narration")

        try:
            user = AccountCreation.objects.get(account_number=account_number)
        except AccountCreation.DoesNotExist:
            return Response(
                data={"error": "User with this account number does not exist."},
                status=status.HTTP_404_NOT_FOUND,
            )

        user.balance = user_data["accountBalance"]
        user.save()

        match transactiontype:
            case "cr":
                UserNotification.objects.create(
                    user=user, title="Credit Transaction", message=narration
                )
            case "db":
                UserNotification.objects.create(
                    user=user, title="Debit Transaction", message=narration
                )
            case _:
                pass

        serializer = self.serializer_class(data=user_data)
        if serializer.is_valid(raise_exception=True):
            response_data = {
                "status": "Successful",
                "message": "Transaction created successfully.",
            }
            return Response(data=response_data, status=status.HTTP_201_CREATED)
        else:
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class GetAccountBalance(generics.GenericAPIView):
    """
    GetAccountBalance handles the GET request of retrieving a
    customer's account balance.
    """

    serializer_class = AccountBalanceSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        user = request.user

        acct_details = AccountCreation.objects.filter(user=user).exists()
        if not acct_details:
            resp = {
                "status": "fail",
                "message": "customer does not have an account.",
            }
            return Response(data=resp, status=status.HTTP_404_NOT_FOUND)

        serializer = AccountBalanceSerializer(acct_details)
        response = {
            "status": "success",
            "message": "Account balance retreieve operation succesful.",
            "data": serializer.data
        }
        return Response(data=response, status=status.HTTP_200_OK)


class SetWalletPin(generics.CreateAPIView):
    """
    SetWalletPin handles the POST request of creating a pin for a
    customer wallet.
    """

    serializer_class = CreateWalletPinSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsPartnerUserOrMember)

    def create(self, request, *args, **kwargs):
        user_data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in request.data.items()
        }
        authenticated_user = request.user

        try:
            user = AccountCreation.objects.get(user=authenticated_user)
        except AccountCreation.DoesNotExist:
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

            # Hash the pin using make_password
            hashed_pin = make_password(pin)

            # set the hashed_pin and save it in the 'pin' flag on the db.
            user.pin = hashed_pin
            user.save()

            authenticated_user.has_created_pin = True
            authenticated_user.save()

            UserNotification.objects.create(
                user=authenticated_user,
                title="Wallet Pin.",
                message="Wallet pin created successfully.",
            )
            # send_email(
            #     subject="Wallet Pin.",
            #     body="This is to inform you that your Wallet pin was created successful.",
            #     sender=picadailys_email,
            #     recipients=authenticated_user.email,
            #     password=app_password,
            # )
            response = {
                "status": "success",
                "message": "Wallet pin created succesfully!",
            }
            return Response(data=response, status=status.HTTP_201_CREATED)


class ForgotWalletPin(generics.GenericAPIView):
    """
    ForgotWalletPin handles the POST request of sending a requeest to
    reset a pin for a customer's wallet.
    """

    serializer_class = BankingStatusSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsPartnerUserOrMember)

    @extend_schema(
        description="Forgot pin view",
        responses={200: {"description": "Forgot wallet pin"}},
    )
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

    serializer_class = BankingStatusSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsPartnerUserOrMember)

    @extend_schema(
        description="Resend Otp",
        responses={200: {"description": "Resend otp"}},
    )
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
    """
    PinVerifyOTP handles the POST request of verifying an
    OTP after wallet pin change request.
    """

    serializer_class = VerifyPinOTPSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsPartnerUserOrMember)

    def post(self, request):
        user_data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in request.data.items()
        }
        user = request.user
        serializer = self.serializer_class(data=user_data)
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
            recipient = user.phone_number

            response = Message.send_msg(msg=str(msg), to=recipient)
            if response.status_code == 200:
                data = {"status": "success", "message": "Account is verified"}
                return Response(data=data, status=status.HTTP_200_OK)


class ResetPin(generics.CreateAPIView):
    serializer_class = ResetPinSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsPartnerUserOrMember)

    def create(self, request):
        authenticated_user = request.user
        user_data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in request.data.items()
        }
        serializer = self.get_serializer(data=request.data)

        try:
            user = AccountCreation.objects.get(user=authenticated_user)
        except AccountCreation.DoesNotExist:
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

            UserNotification.objects.create(
                user=authenticated_user,
                title="Reset Wallet Pin.",
                message="Wallet pin reset was successful.",
            )
            send_email(
                subject="Reset Wallet Pin.",
                body="This is to inform you that your Wallet pin reset was successful.",
                sender=picadailys_email,
                recipients=authenticated_user.email,
                password=app_password,
            )

            response = {"status": "success", "message": "Pin reset successfully"}
            return Response(data=response, status=status.HTTP_200_OK)
        else:
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)
