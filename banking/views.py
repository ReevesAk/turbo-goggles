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
from django.contrib.auth.hashers import check_password
from django.template.loader import render_to_string

# Third party imports.
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

# from rest_framework.exceptions import NotFound
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.pagination import PageNumberPagination

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema

# In-projects imports.
from .serializers import (
    BVNSerializer,
    NINSerializer,
    WalletCreationSerializers,
    Tier2WalletUpgradeSerializer,
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
from .models import WalletModel, UserKYC, AddressVerificationModel
from .controllers import KYC, Wallet, Paystack
from .helpers import cloudinary_to_base64
from security import encrypt, decrypt

verification_link = config("DIGITAL_ADDREESS_VERIFICATION_LINK")


logger = logging.getLogger(__name__)


class PaginationStyle(PageNumberPagination):
    page_size = 20


@extend_schema(
    summary="Verify BVN",
    description="Verify a user's Bank Verification Number (BVN)",
    tags=["KYC"],
    request={
        "application/json": {
            "type": "object",
            "properties": {
                "bvn": {"type": "string", "description": "Bank Verification Number"},
            },
            "required": ["bvn"],
        }
    },
    responses={
        200: OpenApiTypes.OBJECT,
        400: OpenApiTypes.OBJECT,
        401: OpenApiTypes.OBJECT,
    },
)
class VerifYBVN(generics.GenericAPIView):
    """VerifYBVN handles the POST request of verifying a customer's bvn.
    It accepts bvn registered phone number and bvn as inputs.
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

        user = request.user

        # Ensure user has a KYC object
        kyc, _ = UserKYC.objects.get_or_create(user=user)

        # Validate serializer input
        serializer = self.serializer_class(instance=kyc, data=user_data, partial=True)
        serializer.is_valid(raise_exception=True)

        # Prevent duplicate BVNs
        if UserKYC.objects.filter(bvn=user_data["bvn"]).exists():
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": f"User with this BVN {user_data['bvn']} already exists.",
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        selfie_image = cloudinary_to_base64(url=user.profile_img_url)

        # Call Dojah BVN verification API and verify the image from
        # bvn record with the selfie taken at registration.
        bvn_response = KYC.verify_bvn(img_file=selfie_image, bvn=user_data["bvn"])
        print(bvn_response)
        if not bvn_response:
            return Response(
                data=encrypt(
                    {"status": "fail", "message": "BVN verification service failed."}
                ),
                status=status.HTTP_502_BAD_GATEWAY,
            )

        # Handle non-200 status
        if bvn_response.status_code != 200:
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "BVN verification failed, BVN is wrong or incomplete.",
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        # BVN success response
        bvn_data = bvn_response.json()
        entity = bvn_data.get("entity", {})

        # Remove heavy base64 image
        entity.pop("image", None)

        img_resp = entity.get("selfie_verification")
        if img_resp.get("match") is not True or img_resp.get("confidence_value") < 90:
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "BVN verification failed, selfie does not match.",
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        doj_phone = entity.get("phone_number1")
        supplied_phone = user_data.get("bvn_phone")
        if doj_phone != supplied_phone:
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "BVN verification failed, phone number mismatch.",
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        # --- SUCCESS: Update records ---
        kyc.bvn = user_data["bvn"]
        kyc.bvn_phone = supplied_phone
        kyc.is_bvn_img_a_match = True
        kyc.save()

        user.is_bvn_verified = True
        user.save()

        UserNotification.objects.create(
            user=user,
            title="BVN Verification",
            message="Your BVN verification was successful.",
        )

        ActivityModel.objects.create(
            user=user,
            title="BVN Verification",
            description=f"{user.first_name}, {user.last_name} verified their BVN successfully.",
        )

        response_data = {
            "status": "success",
            "message": "BVN verification successful.",
            "bvn_data": {
                "first_name": entity.get("first_name"),
                "last_name": entity.get("last_name"),
                "middle_name": entity.get("middle_name"),
                "date_of_birth": entity.get("date_of_birth"),
                "gender": entity.get("gender"),
                "phone_number": entity.get("phone_number1"),
                "bvn": user_data["bvn"],
            },
        }

        return Response(data=encrypt(response_data), status=status.HTTP_200_OK)


@extend_schema(
    summary="Verify NIN",
    description="Verify a user's National Identification Number (NIN)",
    tags=["KYC"],
    request={
        "application/json": {
            "type": "object",
            "properties": {
                "nin": {
                    "type": "string",
                    "description": "National Identification Number",
                },
            },
            "required": ["nin"],
        }
    },
    responses={
        200: OpenApiTypes.OBJECT,
        400: OpenApiTypes.OBJECT,
        401: OpenApiTypes.OBJECT,
    },
)
class VerifYNIN(generics.GenericAPIView):
    """VerifYNIN handles the POST request of verifying a customer's nin.
    It accepts DOB and user NIN in this format: 1650-12-30.
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

        user = request.user

        # Ensure the user has a KYC instance
        kyc, _ = UserKYC.objects.get_or_create(user=user)

        # Validate serializer
        serializer = self.serializer_class(instance=kyc, data=user_data, partial=True)
        serializer.is_valid(raise_exception=True)

        # Prevent duplicate NIN
        if UserKYC.objects.filter(nin=user_data["nin"]).exists():
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": f"User with this NIN {user_data['nin']} already exists.",
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        selfie_image = cloudinary_to_base64(url=user.profile_img_url)

        # Call Dojah API NIN verification and verify image from nin record
        # with selfie taken at registration.
        nin_response = KYC.verify_nin(img_file=selfie_image, nin=user_data["nin"])

        if not nin_response:
            return Response(
                data=encrypt(
                    {"status": "fail", "message": "NIN verification service failed."}
                ),
                status=status.HTTP_502_BAD_GATEWAY,
            )

        # If status is not 200
        if nin_response.status_code != 200:
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "NIN verification failed. NIN is wrong or incomplete.",
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Parse valid response
        nin_data = nin_response.json()
        entity = nin_data.get("entity", {})

        # Remove heavy image if present
        nin_data.pop("image", None)

        img_resp = entity.get("selfie_verification")
        if img_resp.get("match") is not True or img_resp.get("confidence_value") < 90:
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "NIN verification failed. Selfie does not match.",
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        supplied_dob = user_data.get("nin_dob")
        verified_dob = nin_data["entity"].get("date_of_birth")

        if verified_dob != supplied_dob:
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "NIN verification failed. Date of birth mismatch.",
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        # SUCCESS ---- update DB
        kyc.nin = user_data["nin"]
        kyc.nin_dob = supplied_dob
        kyc.is_nin_img_a_match = True
        kyc.save()

        user.is_nin_verified = True
        user.save()

        UserNotification.objects.create(
            user=user,
            title="NIN Verification",
            message="Your NIN verification was successful.",
        )

        ActivityModel.objects.create(
            user=user,
            title="NIN Verification",
            description=f"{user.first_name}, {user.last_name} verified their NIN successfully.",
        )

        # Clean response
        response_data = {
            "status": "success",
            "message": "NIN verification successful.",
            "nin_data": {
                "first_name": nin_data["entity"].get("first_name"),
                "last_name": nin_data["entity"].get("last_name"),
                "middle_name": nin_data["entity"].get("middle_name"),
                "date_of_birth": nin_data["entity"].get("date_of_birth"),
                "gender": nin_data["entity"].get("gender"),
                "nin": user_data["nin"],
            },
        }

        return Response(data=encrypt(response_data), status=status.HTTP_200_OK)


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
                accountName=payload.get("acct_name"),
                gender=payload.get("gender"),
                bvn=payload.get("bvn"),
                dateOfBirth=payload.get("dateOfBirth"),
                email=current_user.email,
                phoneNo=current_user.phone_number,
            )

            response_data = wallet_response.json()
            response_message = response_data.get("message")
            wallet_status = response_data.get("status")

            # Handle different response codes explicitly
            if (
                response_message == "Account Opening successful"
                and wallet_status == "SUCCESS"
            ):
                user_acc = WalletModel.objects.create(
                    user=current_user,
                    account_number=wallet_response.json()["data"]["accountNumber"],
                    transactionTrackingRef=unique_code,
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

    serializer_class = Tier2WalletUpgradeSerializer
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

        # Check authorization
        pin = serializer.validated_data.get("pin")
        use_biometrics = serializer.validated_data.get("use_biometrics", False)
        user_wallet = WalletModel.objects.filter(user=current_user).first()

        if pin:
            if not check_password(pin, user_wallet.pin):
                return Response(
                    data=encrypt({"status": "fail", "message": "Invalid PIN."}),
                    status=status.HTTP_401_UNAUTHORIZED,
                )
        elif use_biometrics:
            if not current_user.is_biometric_enabled:
                return Response(
                    data=encrypt(
                        {"status": "fail", "message": "Biometric not enabled."}
                    ),
                    status=status.HTTP_401_UNAUTHORIZED,
                )
        else:
            return Response(
                data=encrypt({"status": "fail", "message": "Authorization required."}),
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if current_user.is_nin_verified is False:
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "You have to verify your NIN before upgrade.",
                    }
                ),
                status=status.HTTP_202_ACCEPTED,
            )

        user_kyc = UserKYC.objects.filter(user=current_user).first()
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
                acct_name=user_wallet.acct_name,
                phone_number=current_user.phone_number,
                email=current_user.email,
                acct_no=user_wallet.account_number,
                bvn=user_kyc.bvn,
                nin=payload.get("nin"),
                userPhoto=payload.get("userPhoto"),
                idType=payload.get("idType"),
                idNumber=payload.get("idNumber"),
                idIssueDate=payload.get("idIssueDate"),
                idExpiryDate=payload.get("idExpiryDate"),
                idCardFront=payload.get("idCardFront"),
                idCardBack=payload.get("idCardBack"),
                utilityBill=payload.get("utilityBill"),
                nearestLandmark=payload.get("nearestLandmark"),
                placeOfBirth=payload.get("placeOfBirth"),
                state=payload.get("state"),
                localGovernment=payload.get("localGovernment"),
                houseNumber=payload.get("houseNumber"),
                streetName=payload.get("streetName"),
                city=payload.get("city"),
                pep=payload.get("pep"),
                customerSignature=payload.get("customerSignature"),
            )
            try:
                response_data = upgrade_response.json()
            except ValueError:
                response_data = {"text": upgrade_response.text}

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


class RequestToUpgradeToTier3Wallet(generics.GenericAPIView):
    """RequestToUpgradeToTier3Wallet Handles the POST request to request upgrade of a wallet to Tier 3."""

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        current_user = request.user

        user_wallet = WalletModel.objects.filter(user=current_user).first()
        if not user_wallet:
            return Response(
                data=encrypt(
                    {"status": "fail", "message": "Wallet not found for user."}
                ),
                status=status.HTTP_404_NOT_FOUND,
            )

        if user_wallet.tier_level >= 3:
            return Response(
                data=encrypt(
                    {
                        "status": "success",
                        "message": "Wallet is already on Tier 3.",
                    }
                ),
                status=status.HTTP_202_ACCEPTED,
            )

        try:
            reference_id = f"DOJAH_{current_user.id}"

            # Build the verification URL with user data appended
            # Format: https://identity.dojah.io?widget_id=12345678&user_data[first_name]=John&...&metadata[user_id]=
            base_url = "https://identity.dojah.io"
            dojah_widget_id_and_token = config("DOJAH_WIDGET_ID_AND_TOKEN")

            # Extract user details
            first_name = current_user.first_name or ""
            middle_name = ""
            last_name = current_user.last_name or ""
            email = current_user.email or ""
            phone = current_user.phone_number or ""
            dob = ""

            # Store with user_id as reference_id for webhook matching
            address_verification, created = (
                AddressVerificationModel.objects.get_or_create(
                    reference_id=reference_id,
                    defaults={"user": current_user},
                )
            )
            if created:
                logger.info(f"Created new address verification for {reference_id}")

            status_options = ["Approved", "Successful"]
            if address_verification.status in status_options:
                logger.info(f"Reused existing address verification for {reference_id}")
                return Response(
                    data=encrypt(
                        {
                            "status": "success",
                            "message": "You have already submitted a request to upgrade to Tier 3 and your request is being processed.",
                        }
                    ),
                    status=status.HTTP_200_OK,
                )
            else:
                # Build query string with user data
                verification_url = (
                    f"{base_url}?"
                    f"widget_id={dojah_widget_id_and_token}"
                    f"&user_data[first_name]={first_name}"
                    f"&user_data[middle_name]={middle_name}"
                    f"&user_data[last_name]={last_name}"
                    f"&user_data[email]={email}"
                    f"&user_data[phone]={phone}"
                    f"&user_data[dob]={dob}"
                    f"&metadata[user_id]={reference_id}"
                )

                logger.info(f"Generated verification URL: {verification_url}")
                logger.info(f"Reference ID for webhook matching: {reference_id}")
                resp = {
                    "status": "success",
                    "message": "Request to upgrade to Tier 3 submitted successfully. Please proceed to address verification.",
                    "verification_link": verification_url,
                    "reference_id": reference_id,
                }

                return Response(data=encrypt(resp), status=status.HTTP_200_OK)
        except Exception as e:
            logging.error(f"Wallet upgrade to tier 3 request error: {str(e)}")
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
                        "picadailys_phone": [
                            "02012271894",
                            "02012271895",
                        ],
                    },
                )

                Messaging.send_email(
                    sender_email="notifications@picadailys.com",
                    body=narration,
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
                        "picadailys_phone": [
                            "02012271894",
                            "02012271895",
                        ],
                    },
                )

                Messaging.send_email(
                    sender_email="notifications@picadailys.com",
                    body=narration,
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
            response["data"]["balance"] = serializer.data.get("balance")
            response["data"]["live_enquiry_failed"] = True
            response["data"]["is_live_balance"] = False

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
                    "picadailys_phone": [
                        "02012271894",
                        "02012271895",
                    ],
                },
            )

            Messaging.send_email(
                sender_email="notifications@picadailys.com",
                body="Your Wallet pin was created successfully.",
                email=request.user.email,
                html_content=text_content,
                subject="Wallet Pin",
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
        phone_no = user.phone_number[1:]
        # Create and send OTP.
        otp = otp_manager.create_otp(user_id=str(user.id))
        msg = "Your Picadailys verification code is {otp}. Do not share this code with anyone. Expires in 5 minutes.".format(
            otp=otp
        )

        response = Messaging.send_sms(phone_number=phone_no, msg=msg)
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
        phone_number = user.phone_number[1:]

        # Generate otp.
        otp = otp_manager.create_otp(user_id=str(user.id))
        msg = "Your Picadailys verification code is {otp}. Do not share this code with anyone. Expires in 5 minutes.".format(
            otp=otp
        )

        response = Messaging.send_sms(phone_number=phone_number, msg=msg)
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
