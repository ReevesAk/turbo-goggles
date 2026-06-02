import logging
import string
import random
import time
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from django.template.loader import render_to_string

from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication

from drf_spectacular.utils import extend_schema

from permissions import IsPartnerUserOrMember, IsBrandAd
from commons import generate_txId, Messaging, Biometrics
from security import encrypt, decrypt

from .serializers import (
    ValidateTreasuryAccountSerializer,
    ValidateExternalAccountSerializer,
    TreasuryTransferSerializer,
    CardFundingSerializer,
)
from .models import TreasuryAccount, TreasuryTransfer, TreasuryCardFunding, TreasuryBeneficiary
from .controllers import Anchor
from .helpers import Pin
from .tasks import post_transfer_update, post_beneficiary_credit, send_transfer_notifications
from banking.controllers import Paystack
from banking.transfer_charge import TransferCharge
from accounts.models import TxModel, UserNotification

logger = logging.getLogger(__name__)


def _generate_tx_id(prefix="TRX"):
    timestamp = str(int(time.time()))[-10:]
    rand = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"{prefix}{timestamp}{rand}"


@extend_schema(summary="Validate a Picadailys treasury account number", tags=["Treasury"])
class ValidateTreasuryAccount(generics.GenericAPIView):
    """
    Look up another user's treasury account by account number.
    Equivalent to Get9PSBWallet in banking.
    """

    serializer_class = ValidateTreasuryAccountSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, (IsPartnerUserOrMember | IsBrandAd)]

    def post(self, request):
        decrypted_payload = decrypt(request.data)
        payload = {k: v.strip() if isinstance(v, str) else v for k, v in decrypted_payload.items()}

        serializer = self.serializer_class(data=payload)
        if not serializer.is_valid():
            return Response(data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST)

        acct_no = payload.get("account_number")
        try:
            acct = TreasuryAccount.objects.get(account_number=acct_no)
        except TreasuryAccount.DoesNotExist:
            return Response(
                data=encrypt({"status": "fail", "message": "Account not found."}),
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            data=encrypt({
                "status": "success",
                "message": "Account found.",
                "data": {
                    "account_number": acct.account_number,
                    "acct_name": acct.acct_name,
                    "bank_name": acct.bank_name,
                },
            }),
            status=status.HTTP_200_OK,
        )


@extend_schema(summary="Validate an external bank account via Anchor NIP enquiry", tags=["Treasury"])
class ValidateExternalAccount(generics.GenericAPIView):
    """
    NIP name enquiry for any Nigerian bank account via Anchor.
    Equivalent to ValidateAccountOfOtherBank in banking.
    """

    serializer_class = ValidateExternalAccountSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, (IsPartnerUserOrMember | IsBrandAd)]

    def post(self, request):
        decrypted_payload = decrypt(request.data)
        payload = {k: v.strip() if isinstance(v, str) else v for k, v in decrypted_payload.items()}

        serializer = self.serializer_class(data=payload)
        if not serializer.is_valid():
            return Response(data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST)

        resp = Anchor.verify_bank_account(
            bank_code=payload["bank_code"],
            account_number=payload["account_number"],
        )

        if resp and Anchor.is_success(resp):
            resp_data = resp.json()
            account_name = (
                resp_data.get("data", {}).get("attributes", {}).get("accountName")
                or resp_data.get("data", {}).get("attributes", {}).get("name")
            )
            return Response(
                data=encrypt({
                    "status": "success",
                    "message": "Account validated.",
                    "data": {"account_name": account_name, **resp_data.get("data", {}).get("attributes", {})},
                }),
                status=status.HTTP_200_OK,
            )
        else:
            err = {}
            if resp:
                try:
                    err = resp.json()
                except Exception:
                    err = {"detail": resp.text}
            return Response(
                data=encrypt({"status": "fail", "message": "Account validation failed.", "data": err}),
                status=getattr(resp, "status_code", status.HTTP_400_BAD_REQUEST),
            )


@extend_schema(summary="Transfer between two treasury accounts (internal)", tags=["Treasury"])
class InternalTransfer(generics.CreateAPIView):
    """
    Transfer between two treasury (Anchor sub-) accounts.
    Equivalent to IntraBankTransfer in banking.
    """

    serializer_class = TreasuryTransferSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, (IsPartnerUserOrMember | IsBrandAd)]
    throttle_scope = "wallet_transfer"

    def post(self, request):
        user = request.user
        idempotency_key = request.headers.get("Idempotency-Key")
        if not idempotency_key:
            return Response(
                data=encrypt({"status": "fail", "error": "Idempotency-Key header required."}),
                status=status.HTTP_400_BAD_REQUEST,
            )

        decrypted_payload = decrypt(request.data)
        payload = {k: v.strip() if isinstance(v, str) else v for k, v in decrypted_payload.items()}

        serializer = self.serializer_class(data=payload)
        if not serializer.is_valid():
            return Response(data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST)

        # Guard: beneficiary must be a Picadailys treasury account
        beneficiary_acct_no = payload.get("beneficiary_account_number")
        if not TreasuryAccount.objects.filter(account_number=beneficiary_acct_no).exists():
            return Response(
                data=encrypt({
                    "status": "fail",
                    "error": "Beneficiary account not found on Picadailys. Use external transfer for other banks.",
                }),
                status=status.HTTP_404_NOT_FOUND,
            )

        # Idempotency: return same result for duplicate requests
        existing_tx = TxModel.objects.filter(user=user, tx_reference=idempotency_key).first()
        if existing_tx:
            if existing_tx.status == "PENDING":
                return Response(
                    data=encrypt({"status": "pending", "message": "Transfer in progress."}),
                    status=status.HTTP_202_ACCEPTED,
                )
            if existing_tx.status == "SUCCESS":
                transfer = TreasuryTransfer.objects.filter(tx=existing_tx).first()
                return Response(
                    data=encrypt({
                        "status": "success",
                        "message": "Transfer successful.",
                        "data": {
                            "credit_account": transfer.beneficiary_account_number if transfer else payload.get("beneficiary_account_number"),
                            "debit_account": transfer.sender_account_number if transfer else payload.get("sender_account_number"),
                            "amount": str(existing_tx.amount),
                            "transactionReference": idempotency_key,
                        },
                    }),
                    status=status.HTTP_200_OK,
                )
            return Response(
                data=encrypt({"status": "fail", "error": "Previous transfer failed."}),
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():
                account = TreasuryAccount.objects.select_for_update().get(user=user)

                pin = payload.get("pin")
                biometrics = payload.get("use_biometrics")

                if biometrics:
                    verification = Biometrics.authenticate(user.phone_number)
                else:
                    verification = Pin.verify(user=user, pin=pin, hashed_pin=account.pin)

                if not verification:
                    return Response(
                        data=encrypt({"status": "fail", "error": "Incorrect PIN."}),
                        status=status.HTTP_401_UNAUTHORIZED,
                    )

                amount = Decimal(str(payload.get("amount")))

                # Free intra-treasury transfers (no NIP fee, but apply merchant fee)
                today = timezone.now().date()
                intra_count = TxModel.objects.filter(
                    user=user,
                    tx_type="Internal Transfer",
                    date__date=today,
                ).count()
                merchant_fee = Decimal("10") if intra_count >= 5 else Decimal("0")
                total = amount + merchant_fee

                if account.balance < total:
                    return Response(
                        data=encrypt({"status": "fail", "error": "Insufficient balance."}),
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                # Look up destination account
                beneficiary_acct_no = payload.get("beneficiary_account_number")
                dest_account = TreasuryAccount.objects.filter(account_number=beneficiary_acct_no).first()
                if not dest_account or not dest_account.anchor_account_id:
                    return Response(
                        data=encrypt({"status": "fail", "error": "Beneficiary account not found."}),
                        status=status.HTTP_404_NOT_FOUND,
                    )

                user_narration = payload.get("narration") or ""
                anchor_narration = f"From {account.acct_name}: {user_narration}".strip(": ")

                tx = TxModel.objects.create(
                    user=user,
                    tx_reference=idempotency_key,
                    tx_type="Internal Transfer",
                    amount=str(total),
                    description=anchor_narration,
                    status="PENDING",
                )

            transfer_resp = Anchor.internal_transfer(
                source_account_id=account.anchor_account_id,
                destination_account_id=dest_account.anchor_account_id,
                amount_naira=float(amount),
                narration=anchor_narration,
                reference=idempotency_key,
            )

            if transfer_resp and Anchor.is_success(transfer_resp):
                tx.status = "SUCCESS"
                tx.save(update_fields=["status"])
                anchor_data = transfer_resp.json()
                anchor_transfer_id = anchor_data.get("data", {}).get("id")

                post_transfer_update.delay(
                    user_id=user.id,
                    tx_id=tx.id,
                    anchor_account_id=account.anchor_account_id,
                    account_number=account.account_number,
                    beneficiary_account_number=beneficiary_acct_no,
                    sender_full_name=account.acct_name,
                    amount_str=str(amount),
                    narration=payload.get("narration"),
                    idempotency_key=idempotency_key,
                    alert_type=getattr(user, "alert_type_choice", "Both"),
                    phone_number=getattr(user, "phone_number", None),
                    email=getattr(user, "email", None),
                    beneficiary_name=payload.get("beneficiary_name"),
                    transfer_type="INTERNAL",
                )

                # Immediately credit User B without waiting for the webhook
                dest_user = dest_account.user
                post_beneficiary_credit.delay(
                    beneficiary_user_id=dest_user.id,
                    beneficiary_anchor_account_id=dest_account.anchor_account_id,
                    beneficiary_account_number=beneficiary_acct_no,
                    sender_name=account.acct_name,
                    amount_str=str(amount),
                    narration=anchor_narration,
                    tx_reference=idempotency_key,
                    alert_type=getattr(dest_user, "alert_type_choice", "Both"),
                    phone_number=getattr(dest_user, "phone_number", None),
                    email=getattr(dest_user, "email", None),
                )

                resp_data = {
                    "credit_account": beneficiary_acct_no,
                    "debit_account": account.account_number,
                    "amount": str(amount),
                    "narration": payload.get("narration"),
                    "transactionReference": idempotency_key,
                    "total_debited": str(total),
                }
                if merchant_fee:
                    resp_data["merchant_fee"] = str(merchant_fee)

                return Response(
                    data=encrypt({"status": "success", "message": "Transfer successful.", "data": resp_data}),
                    status=status.HTTP_200_OK,
                )
            else:
                tx.status = "FAILED"
                tx.save(update_fields=["status"])
                err = {}
                if transfer_resp:
                    try:
                        err = transfer_resp.json()
                    except Exception:
                        err = {"detail": getattr(transfer_resp, "text", "")}
                return Response(
                    data=encrypt({"status": "fail", "error": "Transfer failed.", "data": err}),
                    status=getattr(transfer_resp, "status_code", status.HTTP_400_BAD_REQUEST),
                )

        except TreasuryAccount.DoesNotExist:
            return Response(
                data=encrypt({"status": "fail", "error": "Account not found."}),
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as e:
            logger.exception("Unexpected error during internal transfer: %s", e)
            return Response(
                data=encrypt({"status": "fail", "error": "An error occurred. Please try again."}),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


@extend_schema(summary="Send NIP transfer to any Nigerian bank via Anchor", tags=["Treasury"])
class ExternalTransfer(generics.CreateAPIView):
    """
    NIP transfer to any Nigerian bank via Anchor payouts.
    Equivalent to InterBankTransfer in banking.
    """

    serializer_class = TreasuryTransferSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, (IsPartnerUserOrMember | IsBrandAd)]
    throttle_scope = "wallet_transfer"

    def post(self, request):
        user = request.user
        idempotency_key = request.headers.get("Idempotency-Key")
        if not idempotency_key:
            return Response(
                data=encrypt({"status": "fail", "error": "Idempotency-Key header required."}),
                status=status.HTTP_400_BAD_REQUEST,
            )

        decrypted_payload = decrypt(request.data)
        payload = {k: v.strip() if isinstance(v, str) else v for k, v in decrypted_payload.items()}

        serializer = self.serializer_class(data=payload)
        if not serializer.is_valid():
            return Response(data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST)

        existing_tx = TxModel.objects.filter(user=user, tx_reference=idempotency_key).first()
        if existing_tx:
            if existing_tx.status == "PENDING":
                return Response(
                    data=encrypt({"status": "pending", "message": "Transfer in progress."}),
                    status=status.HTTP_202_ACCEPTED,
                )
            if existing_tx.status == "SUCCESS":
                transfer = TreasuryTransfer.objects.filter(tx=existing_tx).first()
                return Response(
                    data=encrypt({
                        "status": "success",
                        "message": "Transfer successful.",
                        "data": {
                            "credit_account": transfer.beneficiary_account_number if transfer else payload.get("beneficiary_account_number"),
                            "debit_account": transfer.sender_account_number if transfer else payload.get("sender_account_number"),
                            "amount": str(existing_tx.amount),
                            "transactionReference": idempotency_key,
                        },
                    }),
                    status=status.HTTP_200_OK,
                )
            return Response(
                data=encrypt({"status": "fail", "error": "Previous transfer failed."}),
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():
                account = TreasuryAccount.objects.select_for_update().get(user=user)

                pin = payload.get("pin")
                biometrics = payload.get("use_biometrics")

                if biometrics:
                    verification = Biometrics.authenticate(user.phone_number)
                else:
                    verification = Pin.verify(user=user, pin=pin, hashed_pin=account.pin)

                if not verification:
                    return Response(
                        data=encrypt({"status": "fail", "error": "Incorrect PIN."}),
                        status=status.HTTP_401_UNAUTHORIZED,
                    )

                amount = Decimal(str(payload.get("amount")))
                charge = TransferCharge.breakdown(amount)
                total = Decimal(charge["total"])

                if account.balance < total:
                    return Response(
                        data=encrypt({"status": "fail", "error": "Insufficient balance."}),
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                tx = TxModel.objects.create(
                    user=user,
                    tx_reference=idempotency_key,
                    tx_type="External Transfer",
                    amount=charge["total"],
                    transfer_fee=charge["transfer_fee"],
                    description=payload.get("narration") or f"Transfer to {payload.get('beneficiary_account_number')}",
                    status="PENDING",
                )

            # Resolve counterparty — reuse cached ID or create and save a new one
            beneficiary_acct = payload.get("beneficiary_account_number")
            beneficiary_bank = payload.get("beneficiary_bank_code")
            beneficiary_name = payload.get("beneficiary_name") or ""

            saved = TreasuryBeneficiary.objects.filter(
                user=user,
                account_number=beneficiary_acct,
                bank_code=beneficiary_bank,
            ).first()

            if saved and saved.anchor_counterparty_id:
                counterparty_id = saved.anchor_counterparty_id
            else:
                cp_resp = Anchor.create_counterparty(
                    account_name=beneficiary_name,
                    account_number=beneficiary_acct,
                    bank_code=beneficiary_bank,
                )
                if not cp_resp or not Anchor.is_success(cp_resp):
                    tx.status = "FAILED"
                    tx.save(update_fields=["status"])
                    err = {}
                    if cp_resp:
                        try:
                            err = cp_resp.json()
                        except Exception:
                            err = {"detail": getattr(cp_resp, "text", "")}
                    return Response(
                        data=encrypt({"status": "fail", "error": "Failed to register beneficiary.", "data": err}),
                        status=getattr(cp_resp, "status_code", status.HTTP_400_BAD_REQUEST),
                    )
                counterparty_id = cp_resp.json().get("data", {}).get("id")
                TreasuryBeneficiary.objects.update_or_create(
                    user=user,
                    account_number=beneficiary_acct,
                    bank_code=beneficiary_bank,
                    defaults={
                        "account_name": beneficiary_name,
                        "anchor_counterparty_id": counterparty_id,
                    },
                )

            transfer_resp = Anchor.nip_transfer(
                source_account_id=account.anchor_account_id,
                counterparty_id=counterparty_id,
                amount_naira=float(amount),
                narration=payload.get("narration") or "Transfer",
                reference=idempotency_key,
            )

            if transfer_resp and Anchor.is_success(transfer_resp):
                tx.status = "SUCCESS"
                tx.save(update_fields=["status"])

                post_transfer_update.delay(
                    user_id=user.id,
                    tx_id=tx.id,
                    anchor_account_id=account.anchor_account_id,
                    account_number=account.account_number,
                    beneficiary_account_number=beneficiary_acct,
                    sender_full_name=account.acct_name,
                    amount_str=charge["principal"],
                    narration=payload.get("narration"),
                    idempotency_key=idempotency_key,
                    alert_type=getattr(user, "alert_type_choice", "Both"),
                    phone_number=getattr(user, "phone_number", None),
                    email=getattr(user, "email", None),
                    beneficiary_name=beneficiary_name,
                    transfer_type="EXTERNAL",
                )

                return Response(
                    data=encrypt({
                        "status": "success",
                        "message": "Transfer successful.",
                        "data": {
                            "credit_account": beneficiary_acct,
                            "debit_account": account.account_number,
                            "amount": charge["principal"],
                            "transfer_fee": charge["transfer_fee"],
                            "total": charge["total"],
                            "narration": payload.get("narration"),
                            "transactionReference": idempotency_key,
                        },
                    }),
                    status=status.HTTP_200_OK,
                )
            else:
                tx.status = "FAILED"
                tx.save(update_fields=["status"])
                err = {}
                if transfer_resp:
                    try:
                        err = transfer_resp.json()
                    except Exception:
                        err = {"detail": getattr(transfer_resp, "text", "")}
                return Response(
                    data=encrypt({"status": "fail", "error": "Transfer failed.", "data": err}),
                    status=getattr(transfer_resp, "status_code", status.HTTP_400_BAD_REQUEST),
                )

        except TreasuryAccount.DoesNotExist:
            return Response(
                data=encrypt({"status": "fail", "error": "Account not found."}),
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as e:
            logger.exception("Unexpected error during external transfer: %s", e)
            return Response(
                data=encrypt({"status": "fail", "error": "An error occurred. Please try again."}),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


@extend_schema(summary="Get remaining free internal transfer count for today", tags=["Treasury"])
class InternalTransferFreeCount(APIView):
    """
    How many free internal transfers the user has made today.
    Equivalent to IntraBankFreeTransferCount in banking.
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        today = timezone.now().date()
        used = TxModel.objects.filter(
            user=request.user,
            tx_type="Internal Transfer",
            date__date=today,
        ).count()

        free_limit = 5
        remaining = max(0, free_limit - used)

        return Response(
            data=encrypt({
                "status": "success",
                "free_transfers_used": used,
                "free_transfers_remaining": remaining,
                "free_limit": free_limit,
                "fee_after_limit": "10.00",
            }),
            status=status.HTTP_200_OK,
        )


@extend_schema(summary="Generate Paystack checkout URL for treasury card funding", tags=["Treasury"])
class PayWithCard(generics.CreateAPIView):
    """
    Generate a Paystack checkout URL to fund the treasury account with a card.
    Equivalent to PayWithCard in banking.
    """

    serializer_class = CardFundingSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        user_data = decrypt(request.data)

        serializer = self.serializer_class(data=user_data)
        if not serializer.is_valid(raise_exception=True):
            return Response(data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST)

        try:
            amount_in_kobo = int(user_data["amount"]) * 100
            checkout_resp = Paystack.generate_url(email=user.email, amount=amount_in_kobo)

            if checkout_resp and checkout_resp.status_code == 200:
                url_resp = checkout_resp.json()
                ref = url_resp["data"]["reference"]
                TreasuryCardFunding.objects.update_or_create(
                    txn_reference=ref,
                    defaults={"user": user},
                )
                return Response(
                    data=encrypt({
                        "status": "success",
                        "message": "Checkout URL generated.",
                        "checkout_url": url_resp["data"]["authorization_url"],
                        "access_code": url_resp["data"]["access_code"],
                        "reference": ref,
                    }),
                    status=status.HTTP_200_OK,
                )
            else:
                return Response(
                    data=encrypt(checkout_resp.json() if checkout_resp else {"error": "Service unavailable."}),
                    status=getattr(checkout_resp, "status_code", status.HTTP_502_BAD_GATEWAY),
                )
        except Exception as e:
            logger.exception("PayWithCard error for user %s: %s", user.id, e)
            return Response(
                data=encrypt({"status": "fail", "error": "Checkout URL generation failed."}),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


@extend_schema(summary="Credit treasury account after confirmed card payment", tags=["Treasury"])
class FundTreasuryAccount(generics.GenericAPIView):
    """
    Credit the user's treasury account after a confirmed Paystack card payment.
    Equivalent to FundWallet in banking.
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user_data = decrypt(request.data)
        user = request.user
        tx_ref = user_data.get("txn_reference")

        if not tx_ref:
            return Response(
                data=encrypt({"status": "fail", "message": "Transaction reference required."}),
                status=status.HTTP_400_BAD_REQUEST,
            )

        funding = TreasuryCardFunding.objects.filter(user=user, txn_reference=tx_ref).first()
        if not funding:
            return Response(
                data=encrypt({"status": "fail", "message": "Transaction not found or does not belong to user."}),
                status=status.HTTP_403_FORBIDDEN,
            )

        if funding.is_processed:
            return Response(
                data=encrypt({"status": "fail", "message": "Transaction already processed."}),
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            account = TreasuryAccount.objects.get(user=user)
        except TreasuryAccount.DoesNotExist:
            return Response(
                data=encrypt({"status": "fail", "message": "Account not found."}),
                status=status.HTTP_404_NOT_FOUND,
            )

        # Credit via Anchor internal transfer from platform account
        # (Actual credit happens via webhook; this just records the intent)
        funding.is_processed = True
        funding.save(update_fields=["is_processed"])

        tx_id = generate_txId()
        TxModel.objects.create(
            user=user,
            tx_reference=tx_id,
            tx_type="Card Funding",
            amount=funding.amount,
            description="Wallet funded via card.",
            status="SUCCESS",
        )

        UserNotification.objects.create(
            user=user,
            title="Card Funding",
            message=f"Your wallet has been funded with ₦{funding.amount}.",
        )

        return Response(
            data=encrypt({"status": "success", "message": "Funding processed."}),
            status=status.HTTP_200_OK,
        )
