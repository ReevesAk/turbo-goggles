import logging
import requests
from decouple import config
from accounts.otp import otp_manager
from permissions import IsPartnerUserOrMember, IsBrandAd
from commons import Message

from django.contrib.auth.hashers import make_password
from django.template.loader import render_to_string
from django.shortcuts import get_object_or_404

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
    AccountDetailsSerializer,
)
from accounts.models import UserNotification
from roles.models import ActivityModel
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

logger = logging.getLogger(__name__)


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

        # if authenticated_user.is_bvn_verified:
        # bvn_deets = BVNData.objects.filter(user=authenticated_user).first()
        # data = {
        #     "First Name": bvn_deets.first_name,
        #     "Last Name": bvn_deets.last_name,
        #     "Phone_no": bvn_deets.phone_number,
        #     "Date of Birth": bvn_deets.date_of_birth,
        #     "Bvn": user_data.get("bvn"),
        # }
        # return Response(
        #     data={
        #         "status": "success",
        #         "message": "User has already verified BVN",
        #         "Bvn data": data,
        #     },
        #     status=status.HTTP_202_ACCEPTED,
        # )
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
                    user=authenticated_user,
                    title="BVN Verification.",
                    message="Your BVN Verifiction is successful.",
                )

                ActivityModel.objects.create(
                    user=authenticated_user,
                    title="BVN Verification.",
                    description=f"{authenticated_user.first_name} {authenticated_user.last_name} verified their BVN successfully."
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
        current_user = request.user
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
                altEmail=request.data.get("alt_email"),
                altPhone=request.data.get("alt_phone"),
                currentAddress=request.data.get("address"),
                nin=request.data.get("NIN"),
                passport=passport,
                identity=identity,
                utility=utility,
                signature=signature,
            )
            response_data = acc_response.json()
            response_code = response_data.get("ResponseCode")

            # Handle different response codes explicitly
            if response_code == "7799":
                logging.error(
                    f"Error {response_code}: {response_data['ResponseDetInfo']}"
                )
                error_message = "The operation has timed out. Please try again later."
                return Response(
                    data={
                        "status": "fail",
                        "error": error_message,
                        "details": response_data["ResponseDetInfo"],
                    },
                    status=status.HTTP_408_REQUEST_TIMEOUT,
                )

            elif acc_response.status_code == 200:
                print(acc_response.json())
                AccountCreation.objects.create(
                    user=current_user,
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
                UserNotification.objects.create(
                    user=current_user,
                    title="Virtual Account Creation 🎉",
                    message="Congratulations! 🎊🎉 Your virtual account has been created successfully. 🥳",
                )

                ActivityModel.objects.create(
                    user=current_user,
                    title="Virtual Account Creation.",
                    description=f"{current_user.first_name} {current_user.last_name} created a virtual account 🎊🎉."
                )

                # Set the value of has_wallet to true.
                current_user.has_wallet = True
                current_user.save()

                resp = {
                    "status": "success",
                    "message": "Open Account Operation was successful!",
                    "accountNumber": acc_response.json()["AccountNUBAN"],
                    "accountName": acc_response.json()["AccountName"],
                    "CustomerNumber": acc_response.json()["CustomerNumber"],
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
        amount = user_data.get("amount")
        date_time = user_data.get("dateTime")

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

                ActivityModel.objects.create(
                    user=user,
                    title="Credit Transactionn.",
                    description=f"{user.first_name} {user.last_name} received a credit transaction with narraiton: {narration}."
                )

                email_body = f"{user.acct_name}, /n This is to inform you that a transaction occurred on your account."
                email_content = render_to_string(
                    "table_email.html",
                    {
                        "email_body": email_body,
                        "name": user.acct_name,
                        "narration": narration,
                        "account_number": account_number,
                        "amount": amount,
                        "tx_type": "Credit Transaction.",
                        "datetime": date_time,
                        "balance": user_data["accountBalance"],
                    },
                )

                Message.send_email(
                    content=email_content,
                    email=user.email,
                    subject="Incoming Transfer.",
                )
            case "db":
                UserNotification.objects.create(
                    user=user, title="Debit Transaction", message=narration
                )

                email_body = f"{user.acct_name}, /n This is to inform you that a transaction occurred on your account."
                email_content = render_to_string(
                    "table_email.html",
                    {
                        "email_body": email_body,
                        "name": user.acct_name,
                        "narration": narration,
                        "account_number": account_number,
                        "amount": amount,
                        "tx_type": "Debit Transaction.",
                        "datetime": date_time,
                        "balance": user_data["accountBalance"],
                    },
                )

                Message.send_email(
                    content=email_content,
                    email=user.email,
                    subject="Outgoing Transfer.",
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


class GetAccountDetails(generics.GenericAPIView):
    """
    GetAccountDetails handles the GET request of retrieving a
    customer's account details.
    """

    serializer_class = AccountDetailsSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        user = request.user

        try:
            acct_details = AccountCreation.objects.get(user=user)
        except AccountCreation.DoesNotExist:
            resp = {
                "status": "fail",
                "message": "Customer does not have an account.",
            }
            return Response(data=resp, status=status.HTTP_404_NOT_FOUND)
        serializer = AccountDetailsSerializer(acct_details)
        response = {
            "status": "success",
            "message": "Account details retrieve operation succesful.",
            "data": serializer.data,
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

            ActivityModel.objects.create(
                user=authenticated_user,
                title="Wallet.",
                description=f"{authenticated_user.first_name} {authenticated_user.last_name} set their wallet pin successfully."
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

                ActivityModel.objects.create(
                    user=user,
                    title="Wallet Pin.",
                    description=f"{user.first_name} {user.last_name} forgot their wallet pin and sent a request to reset it."
                )

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
                ActivityModel.objects.create(
                    user=user,
                    title="Wallet Pin.",
                    description=f"{user.first_name} {user.last_name} reset it."
                )

                data = {"status": "success", "message": "Account is verified"}
                return Response(data=data, status=status.HTTP_200_OK)
        else:
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)


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

            ActivityModel.objects.create(
                user=user,
                title="Reset Wallet Pin.",
                description=f"{user.first_name} {user.last_name} has reset their wallet pin."
            )

            # send transactional email.
            response = {"status": "success", "message": "Pin reset successfully"}
            return Response(data=response, status=status.HTTP_200_OK)
        else:
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)
