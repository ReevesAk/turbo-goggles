import logging
import json
import requests
from decouple import config
from accounts.otp import otp_manager
from permissions import (
    IsPartnerUserOrMember,
    IsGuestWithValidId,
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
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.pagination import PageNumberPagination

from drf_spectacular.utils import extend_schema

# In-projects imports.
from .serializers import (
    BVNSerializer,
    NINSerializer,
    WalletCreationSerializers,
    Tier2WalletUpgradeSerializers,
    Tier3WalletUpgradeSerializers,
    CreateWalletPinSerializer,
    VerifyPinOTPSerializer,
    ResetPinSerializer,
    BankNtfnSerializer,
    BankingStatusSerializer,
    RefundSerializers,
    WalletDetailsSerializer,
    WalletEnquirySerializer,
)
from accounts.models import UserNotification
from roles.models import ActivityModel
from .models import (
    WalletModel,
    UserKYC,
)
from .controllers import KYC, Wallet, Paystack
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
    customer's bvn. It accepts bvn registered phone number and bvn as inputs.
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
        #     return Response(
        #         data=encrypt({
        #             "status": "success",
        #             "message": "User has already verified BVN",
        #         }),
        #         status=status.HTTP_202_ACCEPTED,
        #     )
        try:
            kyc = UserKYC.objects.get(user=authenticated_user)
        except UserKYC.DoesNotExist:
            kyc = UserKYC.objects.create(user=authenticated_user)

        serializer = self.serializer_class(data=user_data)
        if not serializer.is_valid(raise_exception=True):
            return Response(
                data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST
            )

        number = UserKYC.objects.filter(bvn=user_data.get("bvn")).exists()
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
        bvn_response = KYC.verify_bvn(bvn=user_data.get("bvn"))
        bvn_status_code = bvn_response.status_code

        if bvn_status_code != 200:
            response = {
                "status": "fail",
                "message": "Bvn verification was failed, bvn is either wrong or incomplete.",
            }
            encrypt_resp = encrypt(response)
            return Response(data=encrypt_resp, status=status.HTTP_400_BAD_REQUEST)

        if bvn_status_code == 200:
            try:
                bvn_data = bvn_response.json()
                if bvn_data.get("phone_number1") == user_data.get("bvn_phone"):
                    logging.debug(f"BVN verification successful: {bvn_data}")
                    return Response(
                        data=encrypt(
                            {
                                "status": "success",
                                "message": "BVN verification successful.",
                                "bvn data": bvn_data,
                            }
                        ),
                        status=status.HTTP_200_OK,
                    )
                else:
                    response = {
                        "status": "fail",
                        "message": "BVN verification failed, phone number does not match.",
                    }
                    encrypt_resp = encrypt(response)
                    return Response(
                        data=encrypt_resp, status=status.HTTP_400_BAD_REQUEST
                    )
            except ValueError:
                bvn_data = bvn_response.json()
                logging.error(f"BVN verification failed: {bvn_data}")

            # Update the user's BVN instance with the new data.
            kyc.bvn = user_data.get("bvn")
            kyc.bvn_verified = True
            kyc.bvn_phone = user_data.get("bvn_phone")
            kyc.save()

            authenticated_user.is_nin_verified = True
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
                    "first_name": bvn_data.get("first_name"),
                    "last_name": bvn_data.get("last_name"),
                    "date_of_birth": bvn_data.get("date_of_birth"),
                    "phone_number": bvn_data.get("phone_number"),
                    "bvn": user_data.get("bvn"),
                },
            }
            encrypt_resp = encrypt(response)
            return Response(data=encrypt_resp, status=status.HTTP_201_CREATED)
        else:
            return Response(data=encrypt(bvn_response.json()), status=bvn_status_code)


class VerifYNIN(generics.GenericAPIView):
    """
    VerifYNIN handles the POST request of verifying a
    customer's nin. It accepts DOB and user NIN in this format: 1650-12-30.
    """

    serializer_class = NINSerializer
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
        #     return Response(
        #         data=encrypt({
        #             "status": "success",
        #             "message": "User has already verified BVN",
        #         }),
        #         status=status.HTTP_202_ACCEPTED,
        #     )
        try:
            kyc = UserKYC.objects.get(user=authenticated_user)
        except UserKYC.DoesNotExist:
            kyc = UserKYC.objects.create(user=authenticated_user)

        serializer = self.serializer_class(data=user_data)
        if not serializer.is_valid(raise_exception=True):
            return Response(
                data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST
            )

        number = UserKYC.objects.filter(nin=user_data.get("nin")).exists()
        num = user_data.get("nin")
        if number:
            resp = {
                "status": "fail",
                "message": f"User with this nin: {num} already exist",
            }
            encrypt_resp = encrypt(resp)
            return Response(
                data=encrypt_resp,
                status=status.HTTP_400_BAD_REQUEST,
            )
        # Verify the user's BVN.
        nin_response = KYC.verify_nin(nin=user_data.get("nin"))
        nin_status_code = nin_response.status_code

        if nin_status_code != 200:
            response = {
                "status": "fail",
                "message": "NIN verification was failed, NIN is either wrong or incomplete.",
            }
            encrypt_resp = encrypt(response)
            return Response(data=encrypt_resp, status=status.HTTP_400_BAD_REQUEST)

        if nin_status_code == 200:
            try:
                nin_data = nin_response.json()
                if nin_data.get("date_of_birth") == user_data.get("nin_dob"):
                    logging.debug(f"NIN verification successful: {nin_data}")
                    return Response(
                        data=encrypt(
                            {
                                "status": "success",
                                "message": "NIN verification successful.",
                                "nin data": nin_data,
                            }
                        ),
                        status=status.HTTP_200_OK,
                    )
                else:
                    response = {
                        "status": "fail",
                        "message": "NIN verification failed, date of birth does not match.",
                    }
                    encrypt_resp = encrypt(response)
                    return Response(
                        data=encrypt_resp, status=status.HTTP_400_BAD_REQUEST
                    )
            except ValueError:
                nin_data = nin_response.json()
                logging.error(f"NIN verification failed: {nin_data}")

            # Update the user's NIN instance with the new data.
            kyc.nin = user_data.get("nin")
            kyc.nin_dob = user_data.get("nin_dob")
            kyc.save()

            authenticated_user.is_nin_verified = True
            authenticated_user.save()

            serializer = NINSerializer(data=user_data)

            UserNotification.objects.create(
                user=authenticated_user,
                title="NIN Verification.",
                message="Your NIN Verification is successful.",
            )

            ActivityModel.objects.create(
                user=authenticated_user,
                title="NIN Verification.",
                description=f"{authenticated_user.first_name} {authenticated_user.last_name} verified their NIN successfully.",
            )

            response = {
                "status": "success",
                "message": "NIN verification was successful",
                "nin data": {
                    "first_name": nin_data.get("first_name"),
                    "last_name": nin_data.get("last_name"),
                    "date_of_birth": nin_data.get("date_of_birth"),
                    "nin": user_data.get("nin"),
                },
            }
            encrypt_resp = encrypt(response)
            return Response(data=encrypt_resp, status=status.HTTP_201_CREATED)
        else:
            return Response(data=encrypt(nin_response.json()), status=nin_status_code)


class CreateUserWallet(generics.GenericAPIView):
    """
    CreateUserWallet handles the POST request of creating a
    wallet for individuals(Members and BrandAds).
    """

    serializer_class = WalletCreationSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        current_user = request.user
        decrypted_payload = decrypt(request.data)
        payload = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_payload.items()
        }
        logger.info(f"Wallet Creation Payload:\n{json.dumps(payload, indent=4)}")

        serializer = WalletCreationSerializers(data=payload)
        if not serializer.is_valid():
            logging.error(f"Validation Errors: {serializer.errors}")
            return Response(
                data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST
            )

        unique_code = Wallet.generate_unique_code()
        try:
            wallet_response = Wallet.Open(
                transactionTrackingRef=unique_code,
                lastName=current_user.last_name,
                otherNames=current_user.first_name,
                accountName=payload.get("account_number"),
                gender=payload.get("gender"),
                bvn=payload.get("bvn"),
                dateOfBirth=payload.get("dateOfBirth"),
                email=current_user.email,
                phoneNo=current_user.phone_number,
            )

            response_data = wallet_response.json()
            response_message = response_data.get("message")
            wallet_status = wallet_response.get("status")

            # Handle different response codes explicitly
            if (
                response_message == "Account Opening successful"
                and wallet_status == "SUCCESS"
            ):
                user_acc = WalletModel.objects.create(
                    user=current_user,
                    account_number=wallet_response.json()["data"]["accountNumber"],
                    customer_numnber=unique_code,
                    acct_name=wallet_response.json()["data"]["fullName"],
                    address=payload.get("address"),
                    walletType="INDIVIDUAL",
                )
                UserNotification.objects.create(
                    user=current_user,
                    title="Wallet Creation 🎉🎉🎉",
                    message="Congratulations! 🎊🎉🎊🎉 Your wallet has been created successfully. 🥳🥳🥳",
                )

                ActivityModel.objects.create(
                    user=current_user,
                    title="Wallet Creation",
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
                    "account_number": wallet_response.json()["data"]["accountNumber"],
                    "customer_number": unique_code,
                    "acct_name": wallet_response.json()["data"]["fullName"],
                }
                return Response(data=encrypt(resp), status=status.HTTP_201_CREATED)
            else:
                return Response(
                    data=encrypt(wallet_response.json()),
                    status=wallet_response.status_code,
                )
        except requests.exceptions.RequestException as e:
            logging.error(f"Wallet creation API request error: {str(e)}")
            return Response(
                encrypt({"error": str(e)}), status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class UpgradeToTier2Wallet(generics.GenericAPIView):
    """UpgradeToTier2Wallet Handles the POST request upgrade of a wallet to Tier 2."""

    serializer_class = Tier2WalletUpgradeSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        current_user = request.user
        decrypted_payload = decrypt(request.data)
        payload = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_payload.items()
        }
        serializer = self.get_serializer(data=payload)

        if not serializer.is_valid():
            return Response(
                data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST
            )

        user_kyc = UserKYC.objects.filter(user=current_user).first()
        if user_kyc.nin_verified is False:
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "You have to verify your NIN before upgrade.",
                    }
                ),
                status=status.HTTP_202_ACCEPTED,
            )

        user_wallet = WalletModel.objects.filter(user=current_user).first()
        if user_wallet.tier_level >= 2:
            return Response(
                data=encrypt(
                    {
                        "status": "success",
                        "message": "Wallet is already at Tier 2.",
                    }
                ),
                status=status.HTTP_202_ACCEPTED,
            )

        # Perform the upgrade logic here
        try:
            upgrade_response = Wallet.UpgradeToTier2(
                user=current_user,
                wallet_id=payload.get("wallet_id"),
                userPhoto=payload.get("userPhoto"),
                idType=payload.get("idType"),
                idNumber=payload.get("idNumber"),
                idIssueDate=payload.get("idIssueDate"),
                idCardFront=payload.get("idCardFront"),
                houseNumber=payload.get("houseNumber"),
                streetName=payload.get("streetName"),
                city=payload.get("city"),
                pep=payload.get("pep"),
                customerSignature=payload.get("customerSignature"),
            )
            response_data = upgrade_response.json()
            if upgrade_response.status_code != 200:
                logging.error(f"Wallet upgrade to tier 2 failed: {response_data}")
                return Response(
                    data=encrypt(response_data),
                    status=upgrade_response.status_code,
                )
            return Response(
                data=encrypt(
                    {
                        "status": "success",
                        "message": "Wallet upgraded to Tier 2 successfully.",
                    }
                ),
                status=status.HTTP_200_OK,
            )
        except requests.exceptions.RequestException as e:
            logging.error(f"Wallet upgrade to tier 2 API request error: {str(e)}")
            return Response(
                data=encrypt({"error": str(e)}),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class UpgradeToTier3Wallet(generics.GenericAPIView):
    """UpgradeToTier3Wallet Handles the POST request upgrade of a wallet to Tier 3."""

    serializer_class = Tier3WalletUpgradeSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        current_user = request.user
        decrypted_payload = decrypt(request.data)
        payload = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_payload.items()
        }
        serializer = self.get_serializer(data=payload)

        if not serializer.is_valid():
            return Response(
                data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST
            )

        user_wallet = WalletModel.objects.filter(user=current_user).first()
        if user_wallet.tier_level >= 2:
            return Response(
                data=encrypt(
                    {
                        "status": "success",
                        "message": "Wallet is already at Tier 2.",
                    }
                ),
                status=status.HTTP_202_ACCEPTED,
            )

        user_kyc = UserKYC.objects.filter(user=current_user).first()
        # Perform the upgrade logic here
        try:
            upgrade_response = Wallet.UpgradefromTier2ToTier3(
                accountNumber=user_wallet.account_number,
                bvn=user_kyc.bvn,
                nin=user_kyc.nin,
                proofOfAddressVerification=user_wallet.proof_of_address_verification,
            )
            response_data = upgrade_response.json()
            if upgrade_response.status_code != 200:
                logging.error(f"Wallet upgrade to tier 2 failed: {response_data}")
                return Response(
                    data=encrypt(response_data),
                    status=upgrade_response.status_code,
                )
            return Response(
                data=encrypt(
                    {
                        "status": "success",
                        "message": "Wallet upgraded to Tier 2 successfully.",
                    }
                ),
                status=status.HTTP_200_OK,
            )
        except requests.exceptions.RequestException as e:
            logging.error(f"Wallet upgrade to tier 2 API request error: {str(e)}")
            return Response(
                data=encrypt({"error": str(e)}),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class NotificationView(generics.CreateAPIView):
    """
    NotificationView handles the POST request of receiving a
    customer's transaction detail.
    """

    serializer_class = BankNtfnSerializer

    def post(self, request):
        user_data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in request.data.items()
        }
        account_number = user_data.get("accountNumber")
        transactiontype = user_data.get("transactionType")
        narration = user_data.get("narration")
        amount = user_data.get("amount")
        date_time = user_data.get("dateTime")

        try:
            user = WalletModel.objects.get(account_number=account_number)
        except WalletModel.DoesNotExist:
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
                    email=user.email,
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
                    email=user.email,
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
            return Response(data=response_data, status=status.HTTP_201_CREATED)
        else:
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class GetAccountDetails(generics.GenericAPIView):
    """
    GetAccountDetails handles the GET request of retrieving a
    customer's account details.
    """

    serializer_class = WalletEnquirySerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        user = request.user

        try:
            acct_details = WalletModel.objects.get(user=user)
        except WalletModel.DoesNotExist:
            resp = {
                "status": "fail",
                "message": "User does not have an account.",
            }
            return Response(data=encrypt(resp), status=status.HTTP_404_NOT_FOUND)

        # Try live enquiry
        wallet_details = Wallet.getWalletDetails(
            account_number=acct_details.account_number
        )

        if wallet_details and wallet_details.get("status") == "SUCCESS":
            live_data = wallet_details.get("data", {})
            serializer = WalletEnquirySerializer(live_data)
            response = {
                "status": "success",
                "message": "Account details retrieved successfully.",
                "data": serializer.data,
            }
        else:
            # Fallback to DB data, but do not show stale balance
            serializer = WalletDetailsSerializer(acct_details)
            response = {
                "status": "warning",
                "message": "Balance temporarily unavailable. Please refresh.",
                "data": serializer.data,
            }
            response["data"]["balance"] = None  # hide stale balance
            response["data"]["live_enquiry_failed"] = True

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
        logger.info(f"Account Creation Payload: {request.data}")
        user_data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_resp.items()
        }
        authenticated_user = request.user

        try:
            user = WalletModel.objects.get(user=authenticated_user)
        except WalletModel.DoesNotExist:
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
                title="Wallet Pin",
                message="Wallet pin created successfully.",
            )

            ActivityModel.objects.create(
                user=authenticated_user,
                title="Wallet",
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
                    title="Wallet Pin",
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
            user = WalletModel.objects.get(user=authenticated_user)
        except WalletModel.DoesNotExist:
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
                title="Reset Wallet Pin",
                message="Wallet pin reset was successful.",
            )

            ActivityModel.objects.create(
                user=user,
                title="Reset Wallet Pin",
                description=f"{user.first_name} {user.last_name} has reset their wallet pin.",
            )

            # send transactional email.
            response = {"status": "success", "message": "Pin reset successfully"}
            return Response(data=encrypt(response), status=status.HTTP_200_OK)
        else:
            return Response(
                data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST
            )


class RefundFailedCardTransaction(generics.GenericAPIView):
    """
    RefundFailedCardTransaction is the POST request handler that
    initialises a refund for a guest user's card transaction.
    """

    serializer_class = RefundSerializers
    permission_classes = [IsGuestWithValidId]

    def post(self, request, *args, **kwargs):
        user_data = decrypt(request.data)
        user = user_data.get("guest_id")
        tx_ref = user_data.get("txn_reference")

        serializer = RefundSerializers(data=user_data)
        if serializer.is_valid(raise_exception=True):
            try:
                # Initiae a refiund using Paystack
                create_refund_response = Paystack.create_refund(txn_reference=tx_ref)
                if create_refund_response.status_code == 200:
                    # Log successful refund
                    refund_resp = create_refund_response.json()
                    logger.info(
                        f"Refund of failed transaction initiated successfully for guest user: {user} with reference {tx_ref}"
                    )

                    response = {
                        "status": "success",
                        "message": "Refund of failed transaction initiated successfully.",
                        "reference": tx_ref,
                        "data": refund_resp,
                    }
                    return Response(data=encrypt(response), status=status.HTTP_200_OK)
                else:
                    # Log unsuccessful URL generation attempt
                    logger.error(
                        f"Failed to inititate refund for guest user: {user}. Status code: {create_refund_response.status_code}"
                    )
                    return Response(
                        data=encrypt(create_refund_response.json()),
                        status=create_refund_response.status_code,
                    )
            except Exception as e:
                # Log exceptions in refund initiation process
                logger.exception(
                    f"Exception occurred while initiating refund for guest user: {user}: {e}"
                )
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "error": "Internal server error during refund initialisation",
                        }
                    ),
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
        else:
            # Log validation errors
            logger.warning(
                f"Validation failed for PayWithCard request by guest user: {user.id} with errors: {serializer.errors}"
            )
            return Response(
                data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST
            )
