import logging

from accounts.otp import otp_manager
from permissions import IsPartnerUserOrMember
from commons import Messaging

from django.contrib.auth.hashers import make_password
from django.template.loader import render_to_string

from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication

from .serializers import (
    TreasuryStatusSerializer,
    CreateTreasuryAccountSerializer,
    CreateAccountPinSerializer,
    VerifyPinOTPSerializer,
    ResetAccountPinSerializer,
    TreasuryAccountDetailsSerializer,
)
from .models import TreasuryAccount
from .controllers import Anchor
from .tasks import create_notification, create_activity
from .helpers import Pin
from security import encrypt, decrypt
from accounts.models import UserNotification
from roles.models import ActivityModel

logger = logging.getLogger(__name__)


class CreateTreasuryAccount(generics.GenericAPIView):
    """
    Create an Anchor customer + deposit account for the authenticated user.
    """

    serializer_class = CreateTreasuryAccountSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        decrypted_payload = decrypt(request.data)
        payload = {
            k: v.strip() if isinstance(v, str) else v
            for k, v in decrypted_payload.items()
        }

        if hasattr(user, "treasury_account"):
            return Response(
                data=encrypt({"status": "fail", "message": "Account already exists."}),
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = self.serializer_class(data=payload)
        if not serializer.is_valid():
            return Response(data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST)

        acct_name = payload.get("acct_name") or f"{user.first_name} {user.last_name}".strip()

        # Convert phone to E.164 (+234...)
        phone = user.phone_number or ""
        if phone.startswith("0"):
            phone = "+234" + phone[1:]

        # Step 1: create customer
        customer_resp = Anchor.create_customer(
            first_name=user.first_name,
            last_name=user.last_name,
            email=user.email,
            phone=phone,
        )
        if not customer_resp or not Anchor.is_success(customer_resp):
            logger.error("Anchor create_customer failed: %s", getattr(customer_resp, "text", "no response"))
            return Response(
                data=encrypt({"status": "fail", "message": "Account service unavailable."}),
                status=status.HTTP_502_BAD_GATEWAY,
            )

        customer_data = customer_resp.json()
        customer_id = customer_data.get("data", {}).get("id")
        if not customer_id:
            return Response(
                data=encrypt({"status": "fail", "message": "Failed to create customer."}),
                status=status.HTTP_502_BAD_GATEWAY,
            )

        # Step 2: create deposit account
        acct_resp = Anchor.create_deposit_account(customer_id=customer_id, account_name=acct_name)
        if not acct_resp or not Anchor.is_success(acct_resp):
            logger.error("Anchor create_deposit_account failed: %s", getattr(acct_resp, "text", "no response"))
            return Response(
                data=encrypt({"status": "fail", "message": "Failed to create deposit account."}),
                status=status.HTTP_502_BAD_GATEWAY,
            )

        acct_data = acct_resp.json()
        acct_attrs = acct_data.get("data", {}).get("attributes", {})
        anchor_account_id = acct_data.get("data", {}).get("id")
        account_number = acct_attrs.get("accountNumber")
        bank_name = acct_attrs.get("bankName", "")

        if not anchor_account_id or not account_number:
            return Response(
                data=encrypt({"status": "fail", "message": "Invalid response from account service."}),
                status=status.HTTP_502_BAD_GATEWAY,
            )

        TreasuryAccount.objects.create(
            user=user,
            anchor_customer_id=customer_id,
            anchor_account_id=anchor_account_id,
            account_number=account_number,
            bank_name=bank_name,
            acct_name=acct_name,
        )

        logger.info("Treasury account created: user=%s acct=%s", user.id, account_number)

        create_notification.delay(
            user_id=user.id,
            title="Account Created",
            message="Your account has been created successfully.",
        )
        create_activity.delay(
            user_id=user.id,
            title="Account Creation",
            description=f"{user.first_name} {user.last_name} created an account.",
        )

        if user.alert_type_choice in ("SMS", "Both"):
            Messaging.send_sms(
                phone_number=user.phone_number[1:],
                msg=f"Your account {account_number} has been created successfully.",
            )
        if user.alert_type_choice in ("Email", "Both"):
            html = render_to_string(
                "empty_email.html",
                {
                    "custom_text": (
                        f"Dear {user.first_name},<br><br>"
                        f"Your account has been created successfully.<br>"
                        f"Account Name: {acct_name}<br>Account Number: {account_number}"
                    ),
                    "support_email": "notifications@picadailys.com",
                    "picadailys_phone": "02012271894 02012271895",
                },
            )
            Messaging.send_email(
                email=user.email,
                html_content=html,
                sender_email="notifications@picadailys.com",
                body=f"Account {account_number} created.",
                subject="Account Created",
            )

        return Response(
            data=encrypt({
                "status": "success",
                "message": "Account created successfully.",
                "account_number": account_number,
                "bank_name": bank_name,
                "acct_name": acct_name,
            }),
            status=status.HTTP_201_CREATED,
        )


class GetTreasuryAccountDetails(generics.GenericAPIView):
    """
    Return account details with live balance from Anchor.
    Equivalent to GetAccountDetails in banking.
    """

    serializer_class = TreasuryAccountDetailsSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        try:
            account = TreasuryAccount.objects.get(user=user)
        except TreasuryAccount.DoesNotExist:
            return Response(
                data=encrypt({"status": "fail", "message": "Account not found."}),
                status=status.HTTP_404_NOT_FOUND,
            )

        live_balance = None
        if account.anchor_account_id:
            bal_resp = Anchor.get_balance(account.anchor_account_id)
            if bal_resp and Anchor.is_success(bal_resp):
                try:
                    bal_data = bal_resp.json()
                    kobo = bal_data.get("data", {}).get("availableBalance", 0)
                    live_balance = round(kobo / 100, 2)
                    account.balance = live_balance
                    account.save(update_fields=["balance"])
                except Exception:
                    pass

        serializer = TreasuryAccountDetailsSerializer(account)
        resp_data = dict(serializer.data)

        if live_balance is not None:
            resp_data["balance"] = str(live_balance)
            resp_data["is_live_balance"] = True
        else:
            resp_data["is_live_balance"] = False
            resp_data["live_enquiry_failed"] = True

        resp_data["upgrade_status"] = account.tier2_upgrade_status
        resp_data["transfer_fee"] = "15.00"
        resp_data["vat"] = "1.13"

        return Response(
            data=encrypt({"status": "success", "message": "Account details retrieved.", "data": resp_data}),
            status=status.HTTP_200_OK,
        )


class SetAccountPin(generics.CreateAPIView):
    """
    Set a PIN for the treasury account (first time).
    Equivalent to SetWalletPin in banking.
    """

    serializer_class = CreateAccountPinSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, IsPartnerUserOrMember]

    def create(self, request, *args, **kwargs):
        decrypted_resp = decrypt(request.data)
        user_data = {k: v.strip() if isinstance(v, str) else v for k, v in decrypted_resp.items()}
        user = request.user

        try:
            account = TreasuryAccount.objects.get(user=user)
        except TreasuryAccount.DoesNotExist:
            return Response(
                data=encrypt({"error": "Account not found."}),
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = self.serializer_class(data=user_data)
        if not serializer.is_valid(raise_exception=True):
            return Response(data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST)

        pin = user_data.get("pin")
        pin2 = user_data.get("pin2")
        if pin != pin2:
            return Response(
                data=encrypt({"error": "PINs do not match."}),
                status=status.HTTP_400_BAD_REQUEST,
            )

        account.pin = make_password(pin)
        account.save(update_fields=["pin"])

        user.has_created_pin = True
        user.save()

        UserNotification.objects.create(user=user, title="Account PIN", message="PIN created successfully.")
        ActivityModel.objects.create(
            user=user,
            title="Account PIN",
            description=f"{user.first_name} {user.last_name} set their account PIN.",
        )

        if user.alert_type_choice in ("SMS", "Both"):
            Messaging.send_sms(
                phone_number=user.phone_number[1:],
                msg="Your account PIN has been created successfully.",
            )
        if user.alert_type_choice in ("Email", "Both"):
            html = render_to_string(
                "empty_email.html",
                {
                    "custom_text": "Your account PIN has been created successfully.",
                    "support_email": "support@picadailys.com",
                    "picadailys_phone": "02012271894 02012271895",
                },
            )
            Messaging.send_email(
                sender_email="notifications@picadailys.com",
                body="Account PIN created successfully.",
                email=user.email,
                html_content=html,
                subject="Account PIN",
            )

        return Response(
            data=encrypt({"status": "success", "message": "PIN created successfully."}),
            status=status.HTTP_201_CREATED,
        )


class ForgotAccountPin(generics.GenericAPIView):
    """
    Send an OTP to initiate PIN reset.
    Equivalent to ForgotWalletPin in banking.
    """

    serializer_class = TreasuryStatusSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, IsPartnerUserOrMember]

    def post(self, request):
        user = request.user
        phone_no = user.phone_number[1:]
        otp = otp_manager.create_otp(user_id=str(user.id))
        msg = f"Your Picadailys verification code is {otp}. Do not share this. Expires in 5 minutes."
        response_msg = ""

        if user.alert_type_choice in ("SMS", "Both"):
            Messaging.send_sms(phone_number=phone_no, msg=msg)
            response_msg = "An OTP has been sent to your phone number."

        if user.alert_type_choice in ("Email", "Both"):
            html = render_to_string(
                "empty_email.html",
                {
                    "custom_text": msg,
                    "support_email": "support@picadailys.com",
                    "picadailys_phone": "02012271894 02012271895",
                },
            )
            Messaging.send_email(
                sender_email="notifications@picadailys.com",
                body=msg,
                email=user.email,
                html_content=html,
                subject="Forgot Account PIN",
            )
            response_msg = "An OTP has been sent to your email."

        ActivityModel.objects.create(
            user=user,
            title="Forgot Account PIN",
            description=f"{user.first_name} {user.last_name} requested a PIN reset.",
        )

        return Response(
            data=encrypt({"status": "success", "message": response_msg}),
            status=status.HTTP_201_CREATED,
        )


class PinResendOTP(generics.GenericAPIView):
    """
    Resend OTP for PIN reset.
    Equivalent to PinResendOTP in banking.
    """

    serializer_class = TreasuryStatusSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, IsPartnerUserOrMember]

    def post(self, request):
        user = request.user
        phone_number = user.phone_number[1:]
        otp = otp_manager.create_otp(user_id=str(user.id))
        msg = f"Your Picadailys verification code is {otp}. Do not share this. Expires in 5 minutes."
        status_msg = ""

        if user.alert_type_choice in ("SMS", "Both"):
            Messaging.send_otp_whatsapp_fallback(phone_number=phone_number, otp=otp, msg=msg)
            status_msg = "OTP resent. Check your phone."
        if user.alert_type_choice in ("Email", "Both"):
            html = render_to_string(
                "empty_email.html",
                {
                    "custom_text": msg,
                    "support_email": "support@picadailys.com",
                    "picadailys_phone": "02012271894 02012271895",
                },
            )
            Messaging.send_email(
                sender_email="notifications@picadailys.com",
                body=msg,
                email=user.email,
                html_content=html,
                subject="Account PIN OTP",
            )
            status_msg = "OTP resent. Check your email."

        return Response(
            data=encrypt({"status": "success", "message": status_msg}),
            status=status.HTTP_200_OK,
        )


class PinVerifyOTP(generics.GenericAPIView):
    """
    Verify OTP submitted during PIN reset.
    Equivalent to PinVerifyOTP in banking.
    """

    serializer_class = VerifyPinOTPSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, IsPartnerUserOrMember]

    def post(self, request):
        decrypted_resp = decrypt(request.data)
        user_data = {k: v.strip() if isinstance(v, str) else v for k, v in decrypted_resp.items()}
        user = request.user
        serializer = self.serializer_class(data=user_data)
        if not serializer.is_valid(raise_exception=True):
            return Response(data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST)

        received_otp = serializer.data["otp"]
        user_id = otp_manager.validate_user_otp(received_otp)
        if not user_id:
            return Response(
                data=encrypt({"error": "Invalid or expired OTP."}),
                status=status.HTTP_400_BAD_REQUEST,
            )

        ActivityModel.objects.create(
            user=user,
            title="Account PIN",
            description=f"{user.first_name} {user.last_name} verified OTP for PIN reset.",
        )
        return Response(
            data=encrypt({"status": "success", "message": "OTP verified."}),
            status=status.HTTP_200_OK,
        )


class ResetAccountPin(generics.CreateAPIView):
    """
    Reset account PIN after OTP verification.
    Equivalent to ResetPin in banking.
    """

    serializer_class = ResetAccountPinSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, IsPartnerUserOrMember]

    def create(self, request):
        user = request.user
        decrypted_data = decrypt(request.data)
        user_data = {k: v.strip() if isinstance(v, str) else v for k, v in decrypted_data.items()}
        serializer = self.get_serializer(data=user_data)

        try:
            account = TreasuryAccount.objects.get(user=user)
        except TreasuryAccount.DoesNotExist:
            return Response(
                data=encrypt({"error": "Account not found."}),
                status=status.HTTP_404_NOT_FOUND,
            )

        if not serializer.is_valid(raise_exception=True):
            return Response(data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST)

        otp = user_data["otp"]
        user_id = otp_manager.validate_user_otp(otp=otp)
        if not user_id:
            return Response(
                data=encrypt({"error": "Invalid or expired OTP."}),
                status=status.HTTP_400_BAD_REQUEST,
            )

        pin = user_data.get("pin")
        pin2 = user_data.get("pin2")
        if pin != pin2:
            return Response(
                data=encrypt({"error": "PINs do not match."}),
                status=status.HTTP_400_BAD_REQUEST,
            )

        account.pin = make_password(pin)
        account.save(update_fields=["pin"])

        UserNotification.objects.create(user=user, title="Account PIN Reset", message="PIN reset successfully.")
        ActivityModel.objects.create(
            user=user,
            title="Account PIN Reset",
            description=f"{user.first_name} {user.last_name} reset their account PIN.",
        )

        return Response(
            data=encrypt({"status": "success", "message": "PIN reset successfully."}),
            status=status.HTTP_200_OK,
        )


class GetTreasuryCashbackBalance(generics.GenericAPIView):
    """
    Return the cached cashback balance on the treasury account.
    Equivalent to GetCashbackBalance in banking.
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        try:
            account = TreasuryAccount.objects.get(user=user)
        except TreasuryAccount.DoesNotExist:
            return Response(
                data=encrypt({"status": "fail", "message": "Account not found."}),
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            data=encrypt({
                "status": "success",
                "message": "Cashback balance retrieved.",
                "cashback_balance": str(account.cashback_balance),
            }),
            status=status.HTTP_200_OK,
        )
