import logging
import requests
from decouple import config
from accounts.otp import otp_manager
from permissions import (
    IsPartnerUserOrMember,
    IsPartnerUserOrMemberBrandAdOrSuperAdmin,
)
from commons import Messaging

from django.contrib.auth.hashers import make_password
from django.template.loader import render_to_string

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
from security import encrypt, decrypt
from sms import Message


base_url = config("MAPLERAD_BASE_URL")
secret_key = config("MAPLERAD_SECRET_KEY")
headers = {
    "accept": "application/json",
    "content-Type": "application/json",
    "Authorization": "Bearer " + secret_key,
}


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
        decrypted_payload = decrypt(request.data)
        user_data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_payload.items()
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
            num = user_data.get("bvn")
            if number:
                resp = {
                    "status": "fail",
                    "message": f"User with this bvn: {num} already exist",
                }
                encrypt_resp = encrypt(resp)
                return Response(
                    data=encrypt_resp,
                    status=status.HTTP_400_BAD_REQUEST,
                )
            # Verify the user's BVN.
            bvn_response = BVN.verify(bvn=user_data.get("bvn"))
            bvn_status_code = bvn_response.status_code

            if bvn_status_code == 200:
                bvn_data = bvn_response.json()
                logging.info(f"Bvn response: {bvn_data}")

                # Check if the user's date of birth or phone number matches the BVN data
                dob_match = user_data.get("date_of_birth") == bvn_data.get("DOB")
                phone_match = user_data.get("phone_number") == bvn_data.get("Phone")

                # Fail if neither matches
                if not (dob_match or phone_match):
                    resp = {
                        "status": "fail",
                        "message": "Either date of birth or phone number provided must match the one on BVN",
                    }
                    encrypt_resp = encrypt(resp)
                    return Response(
                        data=encrypt_resp,
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
                    description=f"{authenticated_user.first_name} {authenticated_user.last_name} verified their BVN successfully.",
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
                encrypt_resp = encrypt(response)
                return Response(data=encrypt_resp, status=status.HTTP_201_CREATED)
            else:
                return Response(
                    data=encrypt(bvn_response.json()), status=bvn_status_code
                )
        else:
            return Response(
                data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST
            )


class CreateBankAccount(generics.GenericAPIView):
    """
    CreateBankAccount handles the POST request of receiving a
    customer's transaction detail.
    """

    serializer_class = BankAccountCreationSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, IsPartnerUserOrMemberBrandAdOrSuperAdmin]
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
            return Response(
                data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST
            )

        try:
            acc_response = Account.Open(
                addr=payload.get("address"),
                tc=payload.get("tc"),
                acc_type="65",
                religion=payload.get("religion"),
                ms=payload.get("ms"),
                gn=payload.get("gn"),
                branch="203",
                bvn=payload.get("bvn"),
                state=payload.get("state"),
                lga=payload.get("lga"),
                country=payload.get("country"),
                altEmail=payload.get("alt_email"),
                altPhone=payload.get("alt_phone"),
                currentAddress=payload.get("address"),
                nin=payload.get("NIN"),
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
                resp = {
                    "status": "fail",
                    "error": error_message,
                    "details": response_data["ResponseDetInfo"],
                }
                encrypted_repsonse = encrypt(resp)
                return Response(
                    data=encrypted_repsonse,
                    status=status.HTTP_408_REQUEST_TIMEOUT,
                )

            elif acc_response.status_code == 200:
                user_acc = AccountCreation.objects.create(
                    user=current_user,
                    account_number=acc_response.json()["AccountNUBAN"],
                    customer_numnber=acc_response.json()["CustomerNumber"],
                    acct_name=acc_response.json()["AccountName"],
                    sex=payload.get("gn"),
                    title=payload.get("tc"),
                    marital_status=payload.get("ms"),
                    lga=payload.get("lga"),
                    state=payload.get("state"),
                    religion=payload.get("religion"),
                    nin=payload.get("NIN"),
                    address=payload.get("address"),
                )
                UserNotification.objects.create(
                    user=current_user,
                    title="Virtual Account Creation 🎉",
                    message="Congratulations! 🎊🎉 Your virtual account has been created successfully. 🥳",
                )

                ActivityModel.objects.create(
                    user=current_user,
                    title="Virtual Account Creation.",
                    description=f"{current_user.first_name} {current_user.last_name} created a virtual account 🎊🎉.",
                )

                # Set the value of has_wallet to true.
                current_user.has_wallet = True
                current_user.save()

                # Set the value of user's active at account creation.
                user_acc.active_role_on_creation = current_user.active_role
                user_acc.save()

                resp = {
                    "status": "success",
                    "message": "Open Account Operation was successful!",
                    "accountNumber": acc_response.json()["AccountNUBAN"],
                    "accountName": acc_response.json()["AccountName"],
                    "CustomerNumber": acc_response.json()["CustomerNumber"],
                }
                return Response(data=encrypt(resp), status=status.HTTP_201_CREATED)
            else:
                return Response(
                    data=encrypt(acc_response.json()), status=acc_response.status_code
                )
        except requests.exceptions.RequestException as e:
            logging.error(f"Account creation API request error: {str(e)}")
            return Response(
                encrypt({"error": str(e)}), status=status.HTTP_500_INTERNAL_SERVER_ERROR
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
        decrypted_resp = decrypt(request.data)
        user_data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_resp.items()
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
                data=encrypt(
                    {"error": "User with this account number does not exist."}
                ),
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
                    description=f"{user.first_name} {user.last_name} received a credit transaction with narraiton: {narration}.",
                )

                text_content = render_to_string(
                    template_name="table_email.html",
                    context={
                        "custom_text": f"Dear {user.first_name},<br><br>You received a creidt transaction of {amount} and below are the detials.",
                        "narration": narration,
                        "account_number": account_number,
                        "amount": amount,
                        "datetime": date_time,
                        "tx_type": "Credit Transaction",
                        "balance": user_data["accountBalance"],
                        "support_email": "support@picadailys.com",
                        "picadailys_phone": "+123 456 7890",
                    },
                )

                Messaging.send_email(
                    email=request.user.email,
                    html_content=text_content,
                    subject="Credit Transaction",
                )

            case "db":
                UserNotification.objects.create(
                    user=user, title="Debit Transaction", message=narration
                )

                text_content = render_to_string(
                    template_name="table_email.html",
                    context={
                        "custom_text": f"Dear {user.first_name},<br><br>You made a transaction of {amount} and below are the detials.",
                        "narration": narration,
                        "account_number": account_number,
                        "amount": amount,
                        "datetime": date_time,
                        "tx_type": "Debit Transaction",
                        "balance": user_data["accountBalance"],
                        "support_email": "support@picadailys.com",
                        "picadailys_phone": "+123 456 7890",
                    },
                )

                Messaging.send_email(
                    email=request.user.email,
                    html_content=text_content,
                    subject="Debit Transaction",
                )

            case _:
                pass

        serializer = self.serializer_class(data=user_data)
        if serializer.is_valid(raise_exception=True):
            response_data = {
                "status": "Successful",
                "message": "Transaction created successfully.",
            }
            return Response(data=encrypt(response_data), status=status.HTTP_201_CREATED)
        else:
            return Response(
                data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST
            )


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
            return Response(data=encrypt(resp), status=status.HTTP_404_NOT_FOUND)
        serializer = AccountDetailsSerializer(acct_details)
        response = {
            "status": "success",
            "message": "Account details retrieve operation succesful.",
            "data": serializer.data,
        }
        return Response(data=encrypt(response), status=status.HTTP_200_OK)


class SetWalletPin(generics.CreateAPIView):
    """
    SetWalletPin handles the POST request of creating a pin for a
    customer wallet.
    """

    serializer_class = CreateWalletPinSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsPartnerUserOrMember)

    def create(self, request, *args, **kwargs):
        decrypted_resp = decrypt(request.data)
        user_data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_resp.items()
        }
        authenticated_user = request.user

        try:
            user = AccountCreation.objects.get(user=authenticated_user)
        except AccountCreation.DoesNotExist:
            return Response(
                data=encrypt({"error": "Wallet not found for the authenticated user."}),
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = self.serializer_class(data=user_data)
        if serializer.is_valid(raise_exception=True):
            pin = user_data.get("pin")
            pin2 = user_data.get("pin2")

            if pin != pin2:
                return Response(
                    data=encrypt({"error": "Pins do not match!"}),
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
                description=f"{authenticated_user.first_name} {authenticated_user.last_name} set their wallet pin successfully.",
            )

            text_content = render_to_string(
                template_name="empty_email.html",
                context={
                    "custom_text": "This is to inform you that your Wallet pin was created successful.",
                    "support_email": "support@picadailys.com",
                    "picadailys_phone": "+123 456 7890",
                },
            )

            Messaging.send_email(
                email=request.user.email,
                html_content=text_content,
                subject="Waller Pin",
            )

            response = {
                "status": "success",
                "message": "Wallet pin created succesfully!",
            }
            return Response(data=encrypt(response), status=status.HTTP_201_CREATED)


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
                resp = {
                    "status": "success",
                    "message": "Check your phone for an OTP",
                }

                ActivityModel.objects.create(
                    user=user,
                    title="Wallet Pin.",
                    description=f"{user.first_name} {user.last_name} forgot their wallet pin and sent a request to reset it.",
                )

                return Response(data=encrypt(resp), status=status.HTTP_201_CREATED)
            except Exception as err:
                return Response(
                    encrypt(
                        {
                            "status": "fail",
                            "message": err,
                        }
                    ),
                    status=status.HTTP_409_CONFLICT,
                )
        else:
            return Response(data=encrypt(response), status=response.status_code)


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
            resp = {
                "status": "success",
                "message": "Otp resent Successfully. Check your phone for validation",
            }
            return Response(data=encrypt(resp), status=status.HTTP_200_OK)
        else:
            return Response(data=encrypt(response), status=response.status_code)


class PinVerifyOTP(generics.GenericAPIView):
    """
    PinVerifyOTP handles the POST request of verifying an
    OTP after wallet pin change request.
    """

    serializer_class = VerifyPinOTPSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsPartnerUserOrMember)

    def post(self, request):
        decrypted_resp = decrypt(request.data)
        user_data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_resp.items()
        }
        user = request.user
        serializer = self.serializer_class(data=user_data)
        if serializer.is_valid(raise_exception=True):
            received_otp = serializer.data["otp"]

            # Validate otp.
            user_id = otp_manager.validate_user_otp(received_otp)

            if not user_id:
                return Response(
                    data=encrypt({"error": "Invalid or expired OTP"}),
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
                    description=f"{user.first_name} {user.last_name} reset it.",
                )

                data = {"status": "success", "message": "Account is verified"}
                return Response(data=encrypt(data), status=status.HTTP_200_OK)
        else:
            return Response(
                data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST
            )


class ResetPin(generics.CreateAPIView):
    serializer_class = ResetPinSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsPartnerUserOrMember)

    def create(self, request):
        authenticated_user = request.user
        decrypted_data = decrypt(request.data)
        user_data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_data.items()
        }
        serializer = self.get_serializer(data=user_data)

        try:
            user = AccountCreation.objects.get(user=authenticated_user)
        except AccountCreation.DoesNotExist:
            return Response(
                data=encrypt({"error": "Wallet not found for the authenticated user."}),
                status=status.HTTP_404_NOT_FOUND,
            )

        if serializer.is_valid(raise_exception=True):
            otp = user_data["otp"]
            user_id = otp_manager.validate_user_otp(otp=otp)

            if not user_id:
                return Response(
                    data=encrypt({"error": "Invalid or expired OTP"}),
                    status=status.HTTP_400_BAD_REQUEST,
                )

            pin = user_data.get("pin")
            pin2 = user_data.get("pin2")

            if pin != pin2:
                return Response(
                    data=encrypt({"error": "Pins do not match!"}),
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
                description=f"{user.first_name} {user.last_name} has reset their wallet pin.",
            )

            # send transactional email.
            response = {"status": "success", "message": "Pin reset successfully"}
            return Response(data=encrypt(response), status=status.HTTP_200_OK)
        else:
            return Response(
                data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST
            )
