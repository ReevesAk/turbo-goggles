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
from rest_framework.pagination import PageNumberPagination

import rest_framework.serializers as s
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, OpenApiParameter, inline_serializer

# In-projects imports.
from .serializers import (
    BVNSerializer,
    NINSerializer,
    WalletCreationSerializers,
    Tier2WalletUpgradeSerializer,
    CreateWalletPinSerializer,
    VerifyPinOTPSerializer,
    ResetPinSerializer,
    ChangePinSerializer,
    BankNtfnSerializer,
    BankingStatusSerializer,
    RefundSerializers,
    WalletDetailsSerializer,
    WalletEnquirySerializer,
    AccountStatementSerializer,
    SubmitCorporateSerializer,
)
from accounts.models import UserNotification, TxModel, User
from agents.services import ReferralAgentService
from roles.models import ActivityModel
from .tasks import create_notification, create_activity, send_alert_notification
from .models import WalletModel, UserKYC, AddressVerificationModel
from .controllers import KYC, Wallet, Paystack, Corporate, CorporateKYC
from .helpers import (
    cloudinary_to_base64,
    generate_transaction_sms,
    ExportStatement,
    get_asset_id,
    Pin,
    summarize_transactions,
    is_credit_tx,
    describe_transaction,
)
from .utils import normalize_ng_phone, parse_dojah_dob, format_dob_for_9psb
from cloudinary import uploader as cloud
from security import encrypt, decrypt

verification_link = config("DIGITAL_ADDREESS_VERIFICATION_LINK")


logger = logging.getLogger(__name__)


class PaginationStyle(PageNumberPagination):
    page_size = 20


@extend_schema(
    summary="Verify BVN",
    tags=["KYC"],
    description="Submit the user's BVN for verification via Dojah. The BVN photo is matched against the user's profile selfie; both must agree before the KYC record is updated.",
    request=BVNSerializer,
    responses={
        200: inline_serializer(
            name="BVNVerifyResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "bvn_data": inline_serializer(
                    name="BVNData",
                    fields={
                        "first_name": s.CharField(),
                        "last_name": s.CharField(),
                        "date_of_birth": s.CharField(),
                        "gender": s.CharField(),
                        "phone_number": s.CharField(),
                        "bvn": s.CharField(),
                    },
                ),
            },
        ),
        400: inline_serializer(
            name="BVNVerifyErrorResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        502: inline_serializer(
            name="BVNVerifyServiceError",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class VerifYBVN(generics.GenericAPIView):
    """VerifYBVN handles the POST request of verifying a customer's bvn.
    It accepts a BVN as input.
    """

    serializer_class = BVNSerializer
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
        if UserKYC.objects.filter(bvn=user_data["bvn"]).exclude(user=user).exists():
            logger.warning(
                f"BVN verification failed for user {user.id}: BVN {user_data['bvn']} already registered."
            )
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

        img_resp = entity.get("selfie_verification") or {}
        confidence = img_resp.get("confidence_value")

        if (
            img_resp.get("match") is not True
            or not isinstance(confidence, (int, float))
            or confidence < 90
        ):
            logger.warning(
                f"BVN verification failed for user {user.id}: selfie mismatch "
                f"(match={img_resp.get('match')}, confidence_value={confidence!r})."
            )
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "BVN verification failed, selfie does not match.",
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        normalized_phone = normalize_ng_phone(entity.get("phone_number1"))
        parsed_dob = parse_dojah_dob(entity.get("date_of_birth"))

        if not normalized_phone:
            logger.warning(
                "BVN verification failed for user %s: Dojah returned no usable phone (raw=%r).",
                user.id,
                entity.get("phone_number1"),
            )

        if not parsed_dob:
            logger.warning(
                "BVN verification failed for user %s: Dojah returned unparseable DOB (raw=%r).",
                user.id,
                entity.get("date_of_birth"),
            )

        if not normalized_phone or not parsed_dob:
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "BVN verification failed: the BVN record is missing a usable phone number or date of birth. Please contact support.",
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        kyc.bvn = user_data["bvn"]
        kyc.bvn_phone = normalized_phone
        kyc.bvn_dob = parsed_dob.isoformat()
        kyc.is_bvn_img_a_match = True
        kyc.save()

        user.is_bvn_verified = True
        user.save()

        create_notification.delay(
            user_id=user.id,
            title="BVN Verification",
            message="Your BVN verification was successful.",
        )

        create_activity.delay(
            user_id=user.id,
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
                "phone_number": normalized_phone,
                "bvn": user_data["bvn"],
            },
        }

        return Response(data=encrypt(response_data), status=status.HTTP_200_OK)


@extend_schema(
    summary="Verify NIN",
    tags=["KYC"],
    description="Submit the user's NIN and date of birth for verification via Dojah. The NIN photo is matched against the profile selfie before the KYC record is updated.",
    request=NINSerializer,
    responses={
        200: inline_serializer(
            name="NINVerifyResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "nin_data": inline_serializer(
                    name="NINData",
                    fields={
                        "first_name": s.CharField(),
                        "last_name": s.CharField(),
                        "date_of_birth": s.CharField(),
                        "gender": s.CharField(),
                        "nin": s.CharField(),
                    },
                ),
            },
        ),
        400: inline_serializer(
            name="NINVerifyErrorResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        502: inline_serializer(
            name="NINVerifyServiceError",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class VerifYNIN(generics.GenericAPIView):
    """VerifYNIN handles the POST request of verifying a customer's nin.
    It accepts DOB and user NIN in this format: 1650-12-30.
    """

    serializer_class = NINSerializer
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
        if UserKYC.objects.filter(nin=user_data["nin"]).exclude(user=user).exists():
            logger.warning(
                f"NIN verification failed for user {user.id}: NIN {user_data['nin']} already registered."
            )
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
        entity.pop("image", None)

        img_resp = entity.get("selfie_verification") or {}
        confidence = img_resp.get("confidence_value")

        if (
            img_resp.get("match") is not True
            or not isinstance(confidence, (int, float))
            or confidence < 90
        ):
            logger.warning(
                f"NIN verification failed for user {user.id}: selfie mismatch "
                f"(match={img_resp.get('match')}, confidence_value={confidence!r})."
            )
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "NIN verification failed, selfie does not match.",
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        supplied_dob = user_data.get("nin_dob")
        verified_dob = nin_data["entity"].get("date_of_birth")

        if verified_dob != supplied_dob:
            logger.warning(
                f"NIN verification failed for user {user.id}: date of birth mismatch "
                f"(verified={verified_dob!r}, supplied={supplied_dob!r})."
            )
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

        create_notification.delay(
            user_id=user.id,
            title="NIN Verification",
            message="Your NIN verification was successful.",
        )

        create_activity.delay(
            user_id=user.id,
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


@extend_schema(
    summary="Create 9PSB wallet for user",
    tags=["Wallet"],
    description="Open a Tier-1 individual wallet via 9PSB for the authenticated user. BVN and date of birth are required for identity matching.",
    request=WalletCreationSerializers,
    responses={
        201: inline_serializer(
            name="CreateWalletResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "account_number": s.CharField(),
                "customer_number": s.CharField(),
                "acct_name": s.CharField(),
            },
        ),
        400: inline_serializer(
            name="CreateWalletErrorResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        502: inline_serializer(
            name="CreateWalletServiceError",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class CreateUserWallet(generics.GenericAPIView):
    """
    CreateUserWallet handles the POST request of creating a
    wallet for individuals(Members and BrandAds).
    """

    serializer_class = WalletCreationSerializers
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

        kyc = UserKYC.objects.filter(user=current_user).first()

        if kyc is None:
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "KYC record not found. Please complete your BVN verification.",
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not kyc.bvn:
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "BVN is required for wallet creation. Please complete your BVN verification.",
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        phone_no = kyc.bvn_phone

        if not phone_no:
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "BVN phone number is missing. Please re-verify your BVN.",
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        date_of_birth_9psb = format_dob_for_9psb(kyc.bvn_dob)
        if not date_of_birth_9psb:
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "Date of birth is missing or invalid. Please re-verify your BVN.",
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            wallet_response = Wallet.Open(
                transactionTrackingRef=unique_code,
                lastName=current_user.last_name,
                otherNames=current_user.first_name,
                accountName=payload.get("acct_name"),
                gender=payload.get("gender"),
                bvn=kyc.bvn,
                dateOfBirth=date_of_birth_9psb,
                email=current_user.email,
                phoneNo=phone_no,
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
                create_notification.delay(
                    user_id=current_user.id,
                    title="Wallet Creation 🎉🎉🎉",
                    message="Congratulations! 🎊🎉🎊🎉 Your wallet has been created successfully. 🥳🥳🥳",
                )

                create_activity.delay(
                    user_id=current_user.id,
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
                            "picadailys_phone": "02012271894 02012271895 08134032631",
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

                ReferralAgentService.credit_signup_bonus(current_user)

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
            logging.error(f"Wallet creation API request error: {str(e)}", exc_info=True)
            return Response(
                encrypt(
                    {
                        "status": "fail",
                        "message": "Wallet creation failed. Please try again.",
                    }
                ),
                status=status.HTTP_502_BAD_GATEWAY,
            )


@extend_schema(
    summary="Upgrade wallet to Tier 2",
    tags=["Wallet"],
    description="Submit ID documents and a selfie to upgrade an individual wallet from Tier 1 to Tier 2. NIN verification must be completed first. Authorization via PIN or biometrics is required.",
    request=Tier2WalletUpgradeSerializer,
    responses={
        200: inline_serializer(
            name="Tier2UpgradeResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        400: inline_serializer(
            name="Tier2UpgradeErrorResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        401: inline_serializer(
            name="Tier2UpgradeUnauthorizedResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class UpgradeToTier2Wallet(generics.GenericAPIView):
    """UpgradeToTier2Wallet Handles the POST request upgrade of a wallet to Tier 2."""

    serializer_class = Tier2WalletUpgradeSerializer
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
        user_wallet = WalletModel.objects.filter(
            user=current_user, walletType="INDIVIDUAL"
        ).first()

        if pin:
            if not user_wallet or not user_wallet.pin:
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "message": "Wallet PIN not set. Please set your PIN first.",
                        }
                    ),
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
            logging.error(
                f"Wallet upgrade to tier 2 API request error: {str(e)}", exc_info=True
            )
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "Wallet upgrade request failed. Please try again.",
                    }
                ),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


@extend_schema(
    summary="Request wallet upgrade to Tier 3",
    tags=["Wallet"],
    description="Retrieve a Dojah address-verification link to initiate a Tier 3 wallet upgrade. A webhook will be fired by Dojah when address verification completes.",
    responses={
        200: inline_serializer(
            name="Tier3UpgradeResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "verification_link": s.CharField(required=False),
                "reference_id": s.CharField(required=False),
            },
        ),
        404: inline_serializer(
            name="Tier3UpgradeNotFoundResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class RequestToUpgradeToTier3Wallet(generics.GenericAPIView):
    """RequestToUpgradeToTier3Wallet Handles the POST request to request upgrade of a wallet to Tier 3."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        current_user = request.user

        user_wallet = WalletModel.objects.filter(
            user=current_user, walletType="INDIVIDUAL"
        ).first()
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
            logging.error(
                f"Wallet upgrade to tier 3 request error: {str(e)}", exc_info=True
            )
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "Wallet upgrade request failed. Please try again.",
                    }
                ),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


@extend_schema(
    summary="Receive 9PSB transaction notification",
    tags=["Wallet"],
    description="Internal endpoint called by 9PSB to push credit and debit transaction notifications. Updates wallet balance and sends SMS/email alerts to the account holder.",
    request=BankNtfnSerializer,
    responses={
        201: inline_serializer(
            name="NotificationSuccessResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        404: inline_serializer(
            name="NotificationNotFoundResponse",
            fields={"error": s.CharField()},
        ),
    },
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
                            "picadailys_phone": "02012271894  02012271895  08134032631",
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
                            "picadailys_phone": "02012271894  02012271895  08134032631",
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


@extend_schema(
    summary="Get wallet account details and live balance",
    tags=["Wallet"],
    description="Fetch the authenticated user's individual wallet details including a live balance from 9PSB. Falls back to the last known DB balance if the live enquiry fails.",
    responses={
        200: inline_serializer(
            name="AccountDetailsResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "data": inline_serializer(
                    name="AccountDetailsData",
                    fields={
                        "account_number": s.CharField(),
                        "acct_name": s.CharField(),
                        "balance": s.DecimalField(max_digits=20, decimal_places=2),
                        "tier_level": s.IntegerField(),
                        "upgrade_status": s.CharField(),
                        "transfer_fee": s.CharField(),
                        "vat": s.CharField(),
                        "stamp_duty": s.CharField(),
                        "stamp_duty_threshold": s.CharField(),
                    },
                ),
            },
        ),
        404: inline_serializer(
            name="AccountDetailsNotFoundResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class GetAccountDetails(generics.GenericAPIView):
    """
    GetAccountDetails handles the GET request of retrieving a
    customer's account details.
    """

    serializer_class = WalletEnquirySerializer
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        user = request.user

        try:
            acct_details = WalletModel.objects.get(user=user, walletType="INDIVIDUAL")
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

            # Keep DB in sync so the fallback is never stale
            live_balance = live_data.get("availableBalance")
            if live_balance is not None:
                acct_details.balance = live_balance
                acct_details.save(update_fields=["balance"])

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

        response["data"]["upgrade_status"] = acct_details.tier2_upgrade_status
        response["data"]["transfer_fee"] = "20.00"
        response["data"]["vat"] = "1.50"
        response["data"]["stamp_duty"] = "50.00"
        response["data"]["stamp_duty_threshold"] = "10000.00"

        return Response(data=encrypt(response), status=status.HTTP_200_OK)


@extend_schema(
    summary="Set wallet PIN",
    tags=["Wallet"],
    description="Create a 4-digit PIN for the authenticated user's wallet. The PIN is stored hashed and is required to authorise future transfers.",
    request=CreateWalletPinSerializer,
    responses={
        201: inline_serializer(
            name="SetWalletPinResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        400: inline_serializer(
            name="SetWalletPinErrorResponse",
            fields={"error": s.CharField()},
        ),
        404: inline_serializer(
            name="SetWalletPinNotFoundResponse",
            fields={"error": s.CharField()},
        ),
    },
)
class SetWalletPin(generics.CreateAPIView):
    """
    SetWalletPin handles the POST request of creating a pin for a
    customer wallet.
    """

    serializer_class = CreateWalletPinSerializer
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
            user = WalletModel.objects.get(
                user=authenticated_user, walletType="INDIVIDUAL"
            )
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

            hashed_pin = make_password(pin)
            user.pin = hashed_pin
            user.save(update_fields=["pin"])

            authenticated_user.has_created_pin = True
            authenticated_user.save()

            create_notification.delay(
                user_id=authenticated_user.id,
                title="Wallet Pin",
                message="Wallet pin created successfully.",
            )
            create_activity.delay(
                user_id=authenticated_user.id,
                title="Wallet",
                description=f"{authenticated_user.first_name} {authenticated_user.last_name} set their wallet pin successfully.",
            )

            # Backgrounded - see send_alert_notification's docstring
            # (banking/tasks.py). This used to send SMS/email inline here
            # before responding, with no timeout on the outbound HTTP
            # call, so a slow notification gateway could hang the whole
            # "Create PIN" request even though the PIN itself was already
            # saved above.
            text_content = render_to_string(
                template_name="empty_email.html",
                context={
                    "custom_text": "This is to inform you that your Wallet pin was created successfully.",
                    "support_email": "support@picadailys.com",
                    "picadailys_phone": "02012271894  02012271895  08134032631",
                },
            )
            send_alert_notification.delay(
                phone_number=request.user.phone_number[1:],
                email=authenticated_user.email,
                alert_type=authenticated_user.alert_type_choice,
                sms_msg="This is to inform you that your Wallet pin was created successfully.",
                email_subject="Wallet Pin",
                email_body="Your Wallet pin was created successfully.",
                html_content=text_content,
            )

            response = {
                "status": "success",
                "message": "Wallet pin created succesfully!",
            }
            return Response(data=encrypt(response), status=status.HTTP_201_CREATED)


@extend_schema(
    summary="Send OTP to reset forgotten wallet PIN",
    tags=["Wallet"],
    description="Trigger an OTP to be sent to the authenticated user's phone or email as the first step of the wallet-PIN reset flow.",
    responses={
        201: inline_serializer(
            name="ForgotWalletPinResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class ForgotWalletPin(generics.GenericAPIView):
    """
    ForgotWalletPin handles the POST request of sending a requeest to
    reset a pin for a customer's wallet.
    """

    serializer_class = BankingStatusSerializer
    permission_classes = (IsAuthenticated, IsPartnerUserOrMember)

    def post(self, request):
        user = request.user
        phone_no = user.phone_number[1:]
        # Create and send OTP.
        otp = otp_manager.create_otp(user_id=str(user.id))
        msg = "Your Picadailys verification code is {otp}. Do not share this code with anyone. Expires in 5 minutes.".format(
            otp=otp
        )

        # Backgrounded - see send_alert_notification's docstring
        # (banking/tasks.py): sending SMS/email inline here had no
        # timeout on the outbound HTTP call, so a slow gateway could hang
        # this request. The response/return used to live nested inside
        # the "Email" branch below, so a user on alert_type_choice="SMS"
        # (not "Both"/"Email") never got a response at all - the OTP sent
        # fine, but the request just returned None and errored out.
        text_content = render_to_string(
            template_name="empty_email.html",
            context={
                "custom_text": msg,
                "support_email": "support@picadailys.com",
                "picadailys_phone": "02012271894  02012271895  08134032631",
            },
        )
        send_alert_notification.delay(
            phone_number=phone_no,
            email=user.email,
            alert_type=user.alert_type_choice,
            sms_msg=msg,
            email_subject="Forgot Wallet Pin",
            email_body=msg,
            html_content=text_content,
        )

        if user.alert_type_choice == "Email":
            response_msg = "An OTP has been sent to your email address."
        elif user.alert_type_choice == "SMS":
            response_msg = "An OTP has been sent to your phone number."
        else:
            response_msg = (
                "An OTP has been sent to your phone number and email address."
            )

        create_activity.delay(
            user_id=user.id,
            title="Forgot Wallet Pin",
            description=f"{user.first_name} {user.last_name} forgot their wallet pin and sent a request to reset it.",
        )

        resp = {
            "status": "success",
            "message": response_msg,
        }
        return Response(data=encrypt(resp), status=status.HTTP_201_CREATED)


@extend_schema(
    summary="Resend OTP for wallet PIN reset",
    tags=["Wallet"],
    description="Resend the wallet-PIN reset OTP to the authenticated user via their preferred notification channel (SMS or email).",
    responses={
        200: inline_serializer(
            name="BankingPinResendOTPResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class PinResendOTP(generics.GenericAPIView):
    """
    PinResendOTP handles the POST request of resending an
    OTP to a user.
    """

    serializer_class = BankingStatusSerializer
    permission_classes = (IsAuthenticated, IsPartnerUserOrMember)

    def post(self, request):
        user = request.user
        phone_number = user.phone_number[1:]

        # Generate otp.
        otp = otp_manager.create_otp(user_id=str(user.id))
        msg = "Your Picadailys verification code is {otp}. Do not share this code with anyone. Expires in 5 minutes.".format(
            otp=otp
        )

        # Backgrounded - see send_alert_notification's docstring
        # (banking/tasks.py). The response used to be built and returned
        # only inside the "Email" branch below, so a user on
        # alert_type_choice="SMS" (not "Both"/"Email") never got a
        # response at all - the OTP resent fine, but the request just
        # returned None and errored out.
        text_content = render_to_string(
            template_name="empty_email.html",
            context={
                "custom_text": msg,
                "support_email": "support@picadailys.com",
                "picadailys_phone": "02012271894  02012271895  08134032631",
            },
        )
        send_alert_notification.delay(
            phone_number=phone_number,
            email=user.email,
            alert_type=user.alert_type_choice,
            sms_msg=msg,
            email_subject="Forgot Wallet Pin",
            email_body=msg,
            html_content=text_content,
            otp=otp,
        )

        if user.alert_type_choice == "Email":
            status_msg = (
                "Otp resent Successfully. Check your email address for validation"
            )
        elif user.alert_type_choice == "SMS":
            status_msg = "Otp resent Successfully. Check your phone for validation"
        else:
            status_msg = "Otp resent Successfully. Check your phone and email address for validation"

        resp = {
            "status": "success",
            "message": status_msg,
        }
        return Response(data=encrypt(resp), status=status.HTTP_200_OK)


@extend_schema(
    summary="Verify OTP for wallet PIN reset",
    tags=["Wallet"],
    description="Validate the OTP sent during the forgot-wallet-PIN flow to confirm the user's identity before allowing a PIN change.",
    request=VerifyPinOTPSerializer,
    responses={
        200: inline_serializer(
            name="BankingPinVerifyOTPResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        400: inline_serializer(
            name="PinVerifyOTPErrorResponse",
            fields={"error": s.CharField()},
        ),
    },
)
class PinVerifyOTP(generics.GenericAPIView):
    """
    PinVerifyOTP handles the POST request of verifying an
    OTP after wallet pin change request.
    """

    serializer_class = VerifyPinOTPSerializer
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


@extend_schema(
    summary="Reset wallet PIN",
    tags=["Wallet"],
    description="Set a new wallet PIN after the OTP verification step. Both the new PIN and its confirmation are required and must match.",
    request=ResetPinSerializer,
    responses={
        200: inline_serializer(
            name="BankingResetPinResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        400: inline_serializer(
            name="ResetPinErrorResponse",
            fields={"error": s.CharField()},
        ),
        404: inline_serializer(
            name="ResetPinNotFoundResponse",
            fields={"error": s.CharField()},
        ),
    },
)
class ResetPin(generics.CreateAPIView):
    serializer_class = ResetPinSerializer
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
            user = WalletModel.objects.get(
                user=authenticated_user, walletType="INDIVIDUAL"
            )
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


@extend_schema(
    summary="Change wallet PIN",
    tags=["Wallet"],
    description="Change the authenticated user's wallet PIN. Unlike the forgot-pin/OTP flow, this requires the user's current PIN as proof of identity.",
    request=ChangePinSerializer,
    responses={
        200: inline_serializer(
            name="ChangePinResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        400: inline_serializer(
            name="ChangePinErrorResponse",
            fields={"error": s.CharField()},
        ),
        404: inline_serializer(
            name="ChangePinNotFoundResponse",
            fields={"error": s.CharField()},
        ),
    },
)
class ChangePin(generics.CreateAPIView):
    """
    ChangePin lets a logged-in user who still remembers their current
    PIN set a new one, without going through the OTP-based forgot-pin flow.
    """

    serializer_class = ChangePinSerializer
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
            account = WalletModel.objects.get(
                user=authenticated_user, walletType="INDIVIDUAL"
            )
        except WalletModel.DoesNotExist:
            return Response(
                data=encrypt({"error": "Wallet not found for the authenticated user."}),
                status=status.HTTP_404_NOT_FOUND,
            )

        if serializer.is_valid(raise_exception=True):
            old_pin = user_data.get("old_pin")
            pin = user_data.get("pin")
            pin2 = user_data.get("pin2")

            verification = Pin.verify(
                user=authenticated_user, pin=old_pin, hashed_pin=account.pin
            )
            if isinstance(verification, Response):
                return verification
            if verification is not True:
                return Response(
                    data=encrypt({"error": "Incorrect current PIN"}),
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if pin != pin2:
                return Response(
                    data=encrypt({"error": "Pins do not match!"}),
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if pin == old_pin:
                return Response(
                    data=encrypt(
                        {"error": "New pin cannot be the same as the current pin"}
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )

            account.pin = make_password(pin)
            account.save(update_fields=["pin"])

            UserNotification.objects.create(
                user=authenticated_user,
                title="Change Wallet Pin",
                message="Wallet pin was changed successfully.",
            )

            ActivityModel.objects.create(
                user=authenticated_user,
                title="Change Wallet Pin",
                description=f"{authenticated_user.first_name} {authenticated_user.last_name} changed their wallet pin.",
            )

            response = {"status": "success", "message": "Pin changed successfully"}
            return Response(data=encrypt(response), status=status.HTTP_200_OK)
        else:
            return Response(
                data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST
            )


@extend_schema(
    summary="Refund a failed card transaction",
    tags=["Wallet"],
    description="Initiate a Paystack refund for a failed card payment on behalf of a guest user identified by X-Guest-ID.",
    request=RefundSerializers,
    responses={
        200: inline_serializer(
            name="RefundResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "reference": s.CharField(),
            },
        ),
        400: inline_serializer(
            name="RefundErrorResponse",
            fields={"status": s.CharField(), "error": s.CharField()},
        ),
    },
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


@extend_schema(
    summary="Get cashback balance",
    tags=["Wallet"],
    description="Retrieve the cashback balance stored in the authenticated user's individual wallet.",
    responses={
        200: inline_serializer(
            name="BankingCashbackBalanceResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "cashback_balance": s.CharField(),
            },
        ),
    },
)
class GetCashbackBalance(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        try:
            wallet = WalletModel.objects.get(user=user, walletType="INDIVIDUAL")
        except WalletModel.DoesNotExist:
            resp = {
                "status": "fail",
                "message": "User does not have an account.",
            }
            return Response(data=encrypt(resp), status=status.HTTP_404_NOT_FOUND)

        response = {
            "status": "success",
            "message": "Cashback retrieved successful.",
            "cashback_balance": str(wallet.cashback_balance),
        }

        return Response(data=encrypt(response), status=200)


_CORPORATE_REQUIRED_FILES = [
    "cacCertificate",
    "scumlCertificate",
    "utilityBill",
    "memart",
    "tinCertificate",
    "cacOrStatusReport",
    "letterOfBoardResolution",
    "directors[0].passportPhoto",
    "directors[0].idCardFront",
]


@extend_schema(
    summary="Submit corporate account opening",
    tags=["Wallet"],
    description="Upload CAC, SCUML, TIN, and director documents to open a corporate wallet. An admin must complete Dojah address verification before the account is submitted to 9PSB.",
    request=SubmitCorporateSerializer,
    responses={
        201: inline_serializer(
            name="CreateCorporateWalletResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "tax_id_no": s.CharField(),
            },
        ),
        400: inline_serializer(
            name="CreateCorporateWalletErrorResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class CreateCorporateWallet(generics.GenericAPIView):
    serializer_class = SubmitCorporateSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        user = request.user
        decrypted = decrypt(request.data.get("data"))
        data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted.items()
        }

        serializer = self.serializer_class(data=data)
        if not serializer.is_valid():
            return Response(
                data=encrypt(serializer.errors),
                status=status.HTTP_400_BAD_REQUEST,
            )

        tax_id_no = data.get("taxIDNo")

        if WalletModel.objects.filter(tax_id_no=tax_id_no).exists():
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "A corporate account with this TIN has already been submitted.",
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        business_name = data.get("businessName", "")
        business_type = data.get("businessType", "")
        registration_number = data.get("registrationNumber", "")

        cac_ok, cac_result = CorporateKYC.verify_registration(
            rc_number=registration_number,
            business_type=business_type,
            business_name=business_name,
            company_reg_date=data.get("companyRegDate"),
        )
        if not cac_ok:
            return Response(
                data=encrypt({"status": "fail", "message": cac_result}),
                status=status.HTTP_400_BAD_REQUEST,
            )

        tin_ok, tin_result = CorporateKYC.verify_tin(
            tin=tax_id_no,
            business_name=business_name,
            registration_number=registration_number,
        )
        if not tin_ok:
            return Response(
                data=encrypt({"status": "fail", "message": tin_result}),
                status=status.HTTP_400_BAD_REQUEST,
            )

        missing = [k for k in _CORPORATE_REQUIRED_FILES if k not in request.FILES]
        if missing:
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": f"Missing required files: {', '.join(missing)}",
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Upload each document to Cloudinary and store the URLs.
        # The actual 9PSB submission happens later when the admin completes
        # the Dojah address verification and triggers SubmitCorporateTo9PSB.
        documents = {}
        try:
            for key in _CORPORATE_REQUIRED_FILES:
                file_obj = request.FILES.get(key)
                if file_obj:
                    result = cloud.upload(file_obj, resource_type="raw")
                    documents[key] = result["url"]
        except Exception as e:
            logger.error("Cloudinary upload error during corporate submission: %s", e)
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "Document upload failed. Please try again.",
                    }
                ),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        WalletModel.objects.create(
            user=user,
            walletType="CORPORATE",
            tax_id_no=tax_id_no,
            acct_name=data.get("businessName", ""),
            email=data.get("email", ""),
            phoneNo=data.get("phoneNo", ""),
            address=data.get("address", ""),
            registration_number=data.get("registrationNumber", ""),
            business_type=data.get("businessType"),
            corporate_status="PENDING",
            documents=documents,
            submission_data=data,
        )

        # Notify all wallet admins so they know to review and trigger address verification.
        business_name = data.get("businessName", "")
        notification_message = (
            f"New corporate account application from {business_name} (TIN: {tax_id_no}). "
            f"Review and initiate address verification."
        )
        wallet_admins = User.objects.filter(
            active_role__in=["WalletAdmin", "SuperAdmin"]
        )
        notifications = [
            UserNotification(
                user=admin,
                title="New Corporate Application",
                message=notification_message,
            )
            for admin in wallet_admins
        ]
        if notifications:
            UserNotification.objects.bulk_create(notifications)

        return Response(
            data=encrypt(
                {
                    "status": "success",
                    "message": "Corporate account application received. An admin will complete address verification before submission.",
                    "tax_id_no": tax_id_no,
                }
            ),
            status=status.HTTP_201_CREATED,
        )


@extend_schema(
    summary="Resubmit/update a corporate account application",
    tags=["Wallet"],
    description="Update an existing corporate wallet application identified by TIN. Forwards the revised data directly to 9PSB.",
    request=SubmitCorporateSerializer,
    responses={
        200: inline_serializer(
            name="UpdateCorporateWalletResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        404: inline_serializer(
            name="UpdateCorporateWalletNotFoundResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        502: inline_serializer(
            name="UpdateCorporateWalletServiceError",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class UpdateCorporateWallet(generics.GenericAPIView):
    serializer_class = SubmitCorporateSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        user = request.user
        decrypted = decrypt(request.data.get("data"))
        data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted.items()
        }

        serializer = self.serializer_class(data=data)
        if not serializer.is_valid():
            return Response(
                data=encrypt(serializer.errors),
                status=status.HTTP_400_BAD_REQUEST,
            )

        tax_id_no = data.get("taxIDNo")

        if not WalletModel.objects.filter(
            tax_id_no=tax_id_no, user=user, walletType="CORPORATE"
        ).exists():
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "No existing corporate submission found for this TIN.",
                    }
                ),
                status=status.HTTP_404_NOT_FOUND,
            )

        psb_response = Corporate.update(data=data, files=request.FILES)
        if psb_response is None:
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "Corporate account service unavailable.",
                    }
                ),
                status=status.HTTP_502_BAD_GATEWAY,
            )

        try:
            psb_data = psb_response.json()
        except ValueError:
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "Invalid response from banking provider.",
                    }
                ),
                status=status.HTTP_502_BAD_GATEWAY,
            )

        if psb_data.get("status") == "SUCCESS":
            return Response(
                data=encrypt(
                    {
                        "status": "success",
                        "message": "Corporate account update submitted successfully.",
                    }
                ),
                status=status.HTTP_200_OK,
            )

        return Response(
            data=encrypt(psb_data),
            status=psb_response.status_code,
        )


@extend_schema(
    summary="Get corporate account application status",
    tags=["Wallet"],
    description="Poll 9PSB for the current status of a corporate wallet application using the company TIN. Updates the local record if an account number or final status is returned.",
    parameters=[
        OpenApiParameter(
            name="tin",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            required=True,
            description="Company Tax Identification Number used to look up the application.",
        )
    ],
    responses={
        200: OpenApiTypes.OBJECT,
        400: inline_serializer(
            name="GetCorporateStatusErrorResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        404: inline_serializer(
            name="GetCorporateStatusNotFoundResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class GetCorporateWalletStatus(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        tin = request.query_params.get("tin")

        if not tin:
            return Response(
                data=encrypt(
                    {"status": "fail", "message": "TIN query parameter is required."}
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        corporate = WalletModel.objects.filter(
            tax_id_no=tin, user=user, walletType="CORPORATE"
        ).first()
        if not corporate:
            return Response(
                data=encrypt(
                    {"status": "fail", "message": "Corporate account not found."}
                ),
                status=status.HTTP_404_NOT_FOUND,
            )

        psb_response = Corporate.get_status(tin=tin)
        if psb_response is None:
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "Corporate account service unavailable.",
                    }
                ),
                status=status.HTTP_502_BAD_GATEWAY,
            )

        try:
            psb_data = psb_response.json()
        except ValueError:
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "Invalid response from banking provider.",
                    }
                ),
                status=status.HTTP_502_BAD_GATEWAY,
            )

        if psb_data.get("status") == "SUCCESS":
            org = psb_data.get("data", {}).get("organization", {})
            final_status = psb_data.get("data", {}).get("finalStatus")
            acct_no = org.get("accountNumber")
            acct_name = org.get("accountName")

            update_fields = []
            if acct_no and corporate.account_number != acct_no:
                corporate.account_number = acct_no
                update_fields.append("account_number")
            if acct_name and corporate.acct_name != acct_name:
                corporate.acct_name = acct_name
                update_fields.append("acct_name")
            if final_status and corporate.corporate_status != final_status:
                corporate.corporate_status = final_status
                update_fields.append("corporate_status")
            if update_fields:
                corporate.save(update_fields=update_fields)

        return Response(
            data=encrypt(psb_data),
            status=status.HTTP_200_OK,
        )


@extend_schema(
    summary="Generate and email account statement (CSV or PDF)",
    tags=["Wallet"],
    description="Generate an account statement for a date range and deliver it as a CSV or PDF attachment to the user's email address.",
    request=AccountStatementSerializer,
    responses={
        200: inline_serializer(
            name="GenerateStatementResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "account_name": s.CharField(),
                "account_number": s.CharField(),
                "start_date": s.DateField(),
                "end_date": s.DateField(),
                "total_credit": s.FloatField(),
                "total_debit": s.FloatField(),
                "net_movement": s.FloatField(),
                "transactions": s.ListField(child=s.DictField()),
            },
        ),
        400: inline_serializer(
            name="GenerateStatementErrorResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        404: inline_serializer(
            name="GenerateStatementNotFoundResponse",
            fields={"message": s.CharField()},
        ),
    },
)
class GenerateAccountStatement(generics.GenericAPIView):
    """
    GenerateAccountStatement handles the GET request method for
    printing an account statement. It takes the start_date, end_date and
    format in which the document will be sent.
    """

    permission_classes = [IsAuthenticated]
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

        transactions = (
            TxModel.objects.filter(
                user=request.user,
                date__date__range=[start_date, end_date],
                status="SUCCESS",
            )
            .prefetch_related("transfers")
            .only("date", "tx_reference", "tx_type", "amount", "description", "status")
        )

        if not transactions.exists():
            return Response(
                data=encrypt({"message": "No transactions found for this period"}),
                status=status.HTTP_404_NOT_FOUND,
            )

        wallet = WalletModel.objects.filter(
            user=request.user, walletType="INDIVIDUAL"
        ).first()
        account_name = wallet.acct_name if wallet else None
        account_number = wallet.account_number if wallet else None

        total_credit, total_debit, net_movement = summarize_transactions(transactions)

        data = []

        for tx in transactions:
            data.append(
                {
                    "date": tx.date,
                    "reference": tx.tx_reference,
                    "transaction_type": tx.tx_type,
                    "direction": "Credit" if is_credit_tx(tx.tx_type) else "Debit",
                    "amount": tx.amount,
                    "description": describe_transaction(tx),
                    "status": tx.status,
                }
            )

        statement_kwargs = dict(
            account_name=account_name,
            account_number=account_number,
            start_date=start_date,
            end_date=end_date,
        )

        match format_type:
            case "CSV":
                file_content = ExportStatement.to_csv(transactions, **statement_kwargs)
                suffix = ".csv"
            case "PDF":
                file_content = ExportStatement.to_pdf(transactions, **statement_kwargs)
                suffix = ".pdf"
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
                "picadailys_phone": "02012271894 02012271895 08134032631",
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
                    "account_name": account_name,
                    "account_number": account_number,
                    "start_date": start_date,
                    "end_date": end_date,
                    "total_credit": total_credit,
                    "total_debit": total_debit,
                    "net_movement": net_movement,
                    "transactions": data,
                }
            ),
            status=status.HTTP_200_OK,
        )
