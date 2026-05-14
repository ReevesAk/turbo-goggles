import logging
import tempfile
import os
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
from rest_framework.views import APIView
from rest_framework.parsers import JSONParser, FormParser, MultiPartParser

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
    AccountStatementSerializer,
)
from accounts.models import UserNotification, TxModel
from roles.models import ActivityModel
from .models import WalletModel, UserKYC, AddressVerificationModel
from .controllers import KYC, Wallet, Paystack
from .helpers import (
    cloudinary_to_base64,
    generate_transaction_sms,
    ExportStatement,
    get_asset_id,
)
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

        try:
            selfie_image = cloudinary_to_base64(url=user.profile_img_url)
        except Exception as e:
            logger.error(
                f"BVN verification failed: Could not process selfie image - {str(e)}"
            )
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "BVN verification failed. Please update your profile image and try again.",
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Call Dojah BVN verification API and verify the image from
        # bvn record with the selfie taken at registration.
        bvn_response = KYC.verify_bvn(img_file=selfie_image, bvn=user_data["bvn"])
        if bvn_response is None:
            logger.error("BVN verification failed: Dojah API returned no response.")
            return Response(
                data=encrypt(
                    {"status": "fail", "message": "BVN verification service failed."}
                ),
                status=status.HTTP_502_BAD_GATEWAY,
            )

        # Handle non-200 status
        if bvn_response.status_code != 200:
            logger.error(
                f"Dojah BVN returned {bvn_response.status_code}: {bvn_response.text}"
            )
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

        try:
            selfie_image = cloudinary_to_base64(url=user.profile_img_url)
        except Exception as e:
            logger.error(
                f"NIN verification failed: Could not process selfie image - {str(e)}"
            )
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "NIN verification failed. Please update your profile image and try again.",
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Call Dojah API NIN verification and verify image from nin record
        # with selfie taken at registration.
        nin_response = KYC.verify_nin(img_file=selfie_image, nin=user_data["nin"])

        if nin_response is None:
            return Response(
                data=encrypt(
                    {"status": "fail", "message": "NIN verification service failed."}
                ),
                status=status.HTTP_502_BAD_GATEWAY,
            )

        # If status is not 200
        if nin_response.status_code != 200:
            logger.error(
                f"Dojah NIN returned {nin_response.status_code}: {nin_response.text}"
            )
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
        kyc.nin_name = f"{nin_data['entity'].get('first_name', '')} {nin_data['entity'].get('last_name', '')}".strip()
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
        logger.info("Wallet Creation request initiated.")

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

            if wallet_response is None:
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "message": "Wallet service unavailable.",
                        }
                    ),
                    status=status.HTTP_502_BAD_GATEWAY,
                )

            # Wallet.Open may return requests.Response or DRF Response.
            if hasattr(wallet_response, "json"):
                try:
                    response_data = wallet_response.json()
                except ValueError:
                    provider_text = getattr(wallet_response, "text", "")
                    logging.error(
                        "Wallet provider returned non-JSON response for open_wallet: %s",
                        provider_text[:300],
                    )
                    return Response(
                        data=encrypt(
                            {
                                "status": "fail",
                                "message": "Wallet provider returned an invalid response.",
                            }
                        ),
                        status=status.HTTP_502_BAD_GATEWAY,
                    )
            else:
                response_data = (
                    wallet_response.data
                    if isinstance(getattr(wallet_response, "data", None), dict)
                    else {"message": "Wallet creation failed"}
                )

            response_message = response_data.get("message")
            wallet_status = response_data.get("status")

            # Handle different response codes explicitly
            if (
                response_message == "Account Opening successful"
                and wallet_status == "SUCCESS"
            ):
                acct_data = response_data.get("data", {})
                acct_no = acct_data.get("accountNumber")
                acct_name = acct_data.get("fullName")
                user_acc = WalletModel.objects.create(
                    user=current_user,
                    account_number=acct_no,
                    transactionTrackingRef=unique_code,
                    acct_name=acct_name,
                    address=payload.get("address"),
                    walletType="INDIVIDUAL",
                )
                logger.info(
                    "Wallet account created successfully: user=%s, account_number=%s, acct_name=%s, tracking_ref=%s",
                    current_user.id,
                    acct_no,
                    acct_name,
                    unique_code,
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

                mail_lines = [
                    f"Dear {current_user.first_name},",
                    "",
                    "CONGRATULATIONS! 🎊🎉",
                    "",
                    "Your wallet has been created successfully.",
                    "",
                    f"Account Name: {acct_name}",
                    f"Account Number: {acct_no}",
                    "",
                    "You can now start using your wallet for transactions.",
                    "",
                    "Thank you for choosing Picadailys.",
                ]

                mail_msg = "\n".join(mail_lines)

                if current_user.alert_type_choice in ("SMS", "Both"):
                    Messaging.send_sms(
                        phone_number=current_user.phone_number[1:],
                        msg="\n".join(
                            [
                                "Congratulations!",
                                "",
                                "Your wallet has been created successfully 🥳🥳🥳.",
                                "",
                                f"Account Name: {acct_name}",
                                f"Account Number: {acct_no}",
                            ]
                        ),
                    )
                if current_user.alert_type_choice in ("Email", "Both"):
                    # Render the template with values
                    text_content = render_to_string(
                        template_name="empty_email.html",
                        context={
                            "custom_text": f"Dear {current_user.first_name},<br><br>{mail_msg}.",
                            "support_email": "notifications@picadailys.com",
                            "picadailys_phone": "02012271894 02012271895",
                        },
                    )

                    Messaging.send_email(
                        email=current_user.email,
                        html_content=text_content,
                        sender_email="notifications@picadailys.com",
                        body=mail_msg,
                        subject="Picadailys Wallet Registration",
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
                    "account_number": acct_no,
                    "customer_number": unique_code,
                    "acct_name": acct_name,
                }
                return Response(data=encrypt(resp), status=status.HTTP_201_CREATED)
            else:
                return Response(
                    data=encrypt(response_data),
                    status=getattr(
                        wallet_response, "status_code", status.HTTP_400_BAD_REQUEST
                    ),
                )
        except requests.exceptions.RequestException as e:
            logging.error(f"Wallet creation API request error: {str(e)}")
            return Response(
                encrypt({"error": str(e)}), status=status.HTTP_502_BAD_GATEWAY
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
            if not user_wallet or not user_wallet.pin:
                return Response(
                    data=encrypt({"status": "fail", "message": "Wallet PIN not set. Please set your PIN first."}),
                    status=status.HTTP_400_BAD_REQUEST,
                )
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

        if user_wallet.tier2_upgrade_status == "PENDING":
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "You already have a pending upgrade request. Please wait for approval.",
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
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
                acct_name=user_kyc.nin_name or user_wallet.acct_name,
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
            user_wallet.tier2_upgrade_status = "PENDING"
            user_wallet.save(update_fields=["tier2_upgrade_status"])
            return Response(
                data=encrypt(
                    {
                        "status": "success",
                        "message": "Request to upgrade wallet to Tier 2 has been sent successfully.",
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
        reference = user_data.get("reference")

        try:
            wallet = WalletModel.objects.get(account_number=account_number)
        except WalletModel.DoesNotExist:
            return Response(
                data=encrypt(
                    {"error": "User with this account number does not exist."}
                ),
                status=status.HTTP_404_NOT_FOUND,
            )

        wallet.balance = user_data["accountBalance"]
        wallet.save()

        match transactiontype:
            case "cr":
                UserNotification.objects.create(
                    user=wallet.user, title="Credit Transaction", message=narration
                )

                ActivityModel.objects.create(
                    user=wallet.user,
                    title="Credit Transactionn.",
                    description=f"{wallet.user.first_name} {wallet.user.last_name} received a credit transaction with narraiton: {narration}.",
                )

                msg = generate_transaction_sms(
                    transaction_type="CREDIT",
                    account_number=wallet.account_number,
                    amount=amount,
                    balance=wallet.balance,
                    description=narration,
                    reference=reference,
                )

                if wallet.user.alert_type_choice in ("SMS", "Both"):
                    Messaging.send_sms(
                        phone_number=wallet.user.phone_number[1:], msg=msg
                    )

                if wallet.user.alert_type_choice in ("Email", "Both"):
                    text_content = render_to_string(
                        template_name="table_email.html",
                        context={
                            "custom_text": f"Dear {wallet.user.user.first_name},<br><br>You received a creidt transaction of {amount} and below are the detials.",
                            "narration": narration,
                            "account_number": account_number,
                            "amount": amount,
                            "datetime": date_time,
                            "tx_type": "Credit Transaction",
                            "balance": user_data["accountBalance"],
                            "support_email": "support@picadailys.com",
                            "picadailys_phone": "02012271894  02012271895",
                        },
                    )

                    Messaging.send_email(
                        sender_email="notifications@picadailys.com",
                        body=narration,
                        email=wallet.user.email,
                        html_content=text_content,
                        subject="Credit Transaction",
                    )

            case "db":
                UserNotification.objects.create(
                    user=wallet.user, title="Debit Transaction", message=narration
                )

                msg = generate_transaction_sms(
                    transaction_type="DEBIT",
                    account_number=wallet.account_number,
                    amount=amount,
                    balance=wallet.balance,
                    description=narration,
                    reference=reference,
                )

                if wallet.user.alert_type_choice in ("SMS", "Both"):
                    Messaging.send_sms(
                        phone_number=wallet.user.phone_number[1:], msg=msg
                    )
                if wallet.user.alert_type_choice in ("Email", "Both"):
                    text_content = render_to_string(
                        template_name="table_email.html",
                        context={
                            "custom_text": f"Dear {wallet.user.first_name},<br><br>You made a transaction of {amount} and below are the detials.",
                            "narration": narration,
                            "account_number": account_number,
                            "amount": amount,
                            "datetime": date_time,
                            "tx_type": "Debit Transaction",
                            "balance": user_data["accountBalance"],
                            "support_email": "support@picadailys.com",
                            "picadailys_phone": "02012271894  02012271895",
                        },
                    )

                    Messaging.send_email(
                        sender_email="notifications@picadailys.com",
                        body=narration,
                        email=wallet.user.email,
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
        wallet_data = None
        if wallet_details and hasattr(wallet_details, "json"):
            try:
                wallet_data = wallet_details.json()
            except Exception:
                wallet_data = None

        if wallet_data and wallet_data.get("status") == "SUCCESS":
            live_data = wallet_data.get("data", {})
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
        logger.info("Account Creation request initiated.")
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

            if authenticated_user.alert_type_choice in ("SMS", "Both"):
                Messaging.send_sms(
                    phone_number=request.user.phone_number[1:],
                    msg="This is to inform you that your Wallet pin was created successfully.",
                )
            if authenticated_user.alert_type_choice in ("Email", "Both"):
                text_content = render_to_string(
                    template_name="empty_email.html",
                    context={
                        "custom_text": "This is to inform you that your Wallet pin was created successfully.",
                        "support_email": "support@picadailys.com",
                        "picadailys_phone": "02012271894  02012271895",
                    },
                )

                Messaging.send_email(
                    sender_email="notifications@picadailys.com",
                    body="Your Wallet pin was created successfully.",
                    email=authenticated_user.email,
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

        response_msg = ""

        if user.alert_type_choice in ("SMS", "Both"):
            Messaging.send_sms(phone_number=phone_no, msg=msg)
            response_msg = "An OTP has been sent to your phone number."

        if user.alert_type_choice in ("Email", "Both"):
            text_content = render_to_string(
                template_name="empty_email.html",
                context={
                    "custom_text": msg,
                    "support_email": "support@picadailys.com",
                    "picadailys_phone": "02012271894  02012271895",
                },
            )

            Messaging.send_email(
                sender_email="notifications@picadailys.com",
                body=msg,
                email=user.email,
                html_content=text_content,
                subject="Forgot Wallet Pin",
            )

            response_msg = "An OTP has been sent to your email address."

            resp = {
                "status": "success",
                "message": response_msg,
            }

            ActivityModel.objects.create(
                user=user,
                title="Forgot Wallet Pin",
                description=f"{user.first_name} {user.last_name} forgot their wallet pin and sent a request to reset it.",
            )

            return Response(data=encrypt(resp), status=status.HTTP_201_CREATED)


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

        status_msg = ""
        if user.alert_type_choice in ("SMS", "Both"):
            Messaging.send_sms(phone_number=phone_number, msg=msg)
            status_msg = "Otp resent Successfully. Check your phone for validation"
        if user.alert_type_choice in ("Email", "Both"):
            text_content = render_to_string(
                template_name="empty_email.html",
                context={
                    "custom_text": msg,
                    "support_email": "support@picadailys.com",
                    "picadailys_phone": "02012271894  02012271895",
                },
            )

            Messaging.send_email(
                sender_email="notifications@picadailys.com",
                body=msg,
                email=user.email,
                html_content=text_content,
                subject="Forgot Wallet Pin",
            )
            status_msg = (
                "Otp resent Successfully. Check your email address for validation"
            )

            resp = {
                "status": "success",
                "message": status_msg,
            }
            return Response(data=encrypt(resp), status=status.HTTP_200_OK)


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

            user.pin = make_password(pin)
            user.save(update_fields=["pin"])

            UserNotification.objects.create(
                user=authenticated_user,
                title="Reset Wallet Pin",
                message="Wallet pin reset was successful.",
            )

            ActivityModel.objects.create(
                user=authenticated_user,
                title="Reset Wallet Pin",
                description=f"{authenticated_user.first_name} {authenticated_user.last_name} has reset their wallet pin.",
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


class GetCashbackBalance(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def get(self, request):
        user = request.user

        wallet = WalletModel.objects.get(user=user)

        response = {
            "status": "success",
            "message": "Cashback retrieved successful.",
            "cashback_balance": str(wallet.cashback_balance),
        }

        return Response(data=encrypt(response), status=200)


class GenerateAccountStatement(generics.GenericAPIView):
    """
    GenerateAccountStatement handles the GET request method for
    printing an account statement. It takes the start_date, end_date and
    format in which the document will be sent.
    """

    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    serializer_class = AccountStatementSerializer
    parser_classes = [JSONParser, FormParser, MultiPartParser]

    def post(self, request):
        user = request.user
        user_data = decrypt(request.data)

        serializer = AccountStatementSerializer(data=user_data)

        if not serializer.is_valid(raise_exception=True):
            return Response(
                data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST
            )

        start_date = serializer.validated_data["start_date"]
        end_date = serializer.validated_data["end_date"]
        format_type = serializer.validated_data["format"]

        transactions = TxModel.objects.filter(
            user=request.user,
            date__date__range=[start_date, end_date],
            status="SUCCESS",
        ).only("date", "tx_reference", "tx_type", "amount", "description", "status")

        if not transactions.exists():
            return Response(
                data=encrypt({"message": "No transactions found for this period"}),
                status=status.HTTP_404_NOT_FOUND,
            )

        data = []

        for tx in transactions:
            data.append(
                {
                    "date": tx.date,
                    "reference": tx.tx_reference,
                    "transaction_type": tx.tx_type,
                    "amount": tx.amount,
                    "description": tx.description,
                    "status": tx.status,
                }
            )

        match format_type:
            case "CSV":
                file_content = ExportStatement.to_csv(transactions)
                suffix = ".csv"
                mime_type = "text/csv"
            case "PDF":
                file_content = ExportStatement.to_pdf(transactions)
                suffix = ".pdf"
                mime_type = "application/pdf"
            case _:
                return Response(
                    {"error": "Invalid format requested"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Write file_content to a temporary file and pass its path to get_asset_id
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
            if isinstance(file_content, str):
                tmp_file.write(file_content.encode("utf-8"))
            else:
                tmp_file.write(file_content)
            tmp_file_path = tmp_file.name

        msg = (
            f"Your account statement from {start_date} to {end_date} "
            f"has been generated successfully. Please find the statement attached."
        )

        result = get_asset_id(file=tmp_file_path)

        # Clean up the temp file
        try:
            os.remove(tmp_file_path)
        except Exception:
            pass

        if not result["success"]:
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": f"An error occured while generating account statement: {result['message']}.",
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        media_id = result["media_id"]
        text_content = render_to_string(
            template_name="empty_email.html",
            context={
                "custom_text": f"""
                Dear {user.first_name},<br><br>
                {msg}<br><br>
                If you did not request this statement, please contact our support team immediately.
                """,
                "support_email": "support@picadailys.com",
                "picadailys_phone": "02012271894 02012271895",
            },
        )

        Messaging.send_email_with_attachment(
            email=user.email,
            html_content=text_content,
            subject="Your Picadailys Account Statement",
            body=msg,
            sender_email="notifications@picadailys.com",
            media_id=media_id,
        )

        return Response(
            data=encrypt(
                {
                    "status": "success",
                    "message": "User account statement generated succesfully.",
                    "transactions": data,
                }
            ),
            status=status.HTTP_200_OK,
        )
