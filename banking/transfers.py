import logging
import string
import random
import time
from decimal import Decimal


from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

import rest_framework.serializers as s
from drf_spectacular.utils import extend_schema, OpenApiParameter, inline_serializer
from drf_spectacular.types import OpenApiTypes

from permissions import (
    IsPartnerUserOrMember,
    IsBrandAd,
    IsGuestWithValidId,
)
from commons import Biometrics

# Third party imports.
from rest_framework import generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

# In-projects imports.
from .helpers import Pin
from .transfer_charge import TransferCharge
from roles.models import ActivityModel
from .controllers import Transfers, Paystack, Wallet
from .models import TransferModel, WalletModel, FundWithCard
from banking.tasks import (
    post_transfer_update,
    resolve_pending_transfer,
)
from accounts.models import (
    User,
    WelcomeBonusAward,
    WelcomeBonusCounter,
    TxModel,
    UserNotification,
)
from .serializers import (
    Get9PSBWalletSerializer,
    GetAccountSerializer,
    BankTransfersSerializer,
    GetTransferStatusSerializer,
    PaymentURLSerializers,
    FundWalletSerializers,
)
from security import encrypt, decrypt

logger = logging.getLogger(__name__)


def _build_narration(sender_name: str, user_narration) -> str:
    """
    Enforces the sender's name as a prefix on every outbound transfer
    narration, with whatever the user typed appended after it.
    """
    user_narration = (user_narration or "").strip()
    if user_narration:
        return f"{sender_name}/{user_narration}"
    return sender_name


@extend_schema(
    summary="Get all supported banks and their codes",
    tags=["Banking"],
    description="Return a list of all financial institutions and their 3-digit bank codes supported by the 9PSB transfer network.",
    responses={
        200: inline_serializer(
            name="GetAllBanksResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "data": s.ListField(child=s.DictField()),
            },
        ),
        500: inline_serializer(
            name="GetAllBanksErrorResponse",
            fields={"status": s.CharField(), "error": s.CharField()},
        ),
    },
)
class GetAllBanks(APIView):
    """
    GetAllBanks handles the GET request of retrieving all available financial
    institutions and their banks codes.
    """

    permission_classes = (IsAuthenticated, (IsPartnerUserOrMember | IsBrandAd))

    def get(self, request):
        logger.info("Received request to retrieve all financial institutions.")

        # Call Transfers service to get all banks
        all_banks_resp = Transfers.getAllBanks()
        try:
            resp_json = all_banks_resp.json()
        except Exception as e:
            logger.error(f"Failed to parse response JSON: {e}")
            resp_json = {}

        status_val = resp_json.get("status")
        data_val = resp_json.get("data")

        if status_val == "SUCCESS" and data_val is not None:
            logger.info("Successfully retrieved financial institutions data.")
            resp = {
                "status": "success",
                "message": "All financial institutions retrieved successfully.",
                "data": data_val,
            }
            return Response(data=encrypt(resp), status=status.HTTP_200_OK)
        else:
            logger.error(
                f"Failed to retrieve financial institutions. Status code: {getattr(all_banks_resp, 'status_code', 'N/A')}"
            )
            err_resp = {
                "status": "fail",
                "error": "Could not retrieve financial institution.",
                "data": data_val if data_val is not None else resp_json,
            }
            return Response(
                data=encrypt(err_resp),
                status=getattr(
                    all_banks_resp, "status_code", status.HTTP_500_INTERNAL_SERVER_ERROR
                ),
            )


@extend_schema(
    summary="Validate a 9PSB wallet account number",
    tags=["Banking"],
    description="Verify that an account number belongs to a Picadailys/9PSB wallet and return the account name. Falls back to the local database if the live enquiry fails.",
    request=Get9PSBWalletSerializer,
    responses={
        200: inline_serializer(
            name="Get9PSBWalletResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "data": inline_serializer(
                    name="Get9PSBWalletData",
                    fields={
                        "account_number": s.CharField(),
                        "acc_name": s.CharField(),
                    },
                ),
            },
        ),
    },
)
class Get9PSBWallet(generics.GenericAPIView):
    """
    Get9PSBWallet handles the GET request of validating supplied account number
    It returns the account details upon success.
    """

    serializer_class = Get9PSBWalletSerializer
    permission_classes = (IsAuthenticated, (IsPartnerUserOrMember | IsBrandAd))

    def post(self, request):
        logger.info("Received request to validate and retrieve 9PSB wallet details.")

        # Decrypt, Clean up and prepare payload
        decrypted_payload = decrypt(request.data)
        payload = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_payload.items()
        }
        serializer = Get9PSBWalletSerializer(data=payload)

        if serializer.is_valid():
            validated_data = serializer.validated_data
            logger.info(
                f"Payload validation successful for account number: {validated_data['account_number']}"
            )

            # Call external service to retrieve account details
            acc_resp = Wallet.getWalletDetails(
                account_number=validated_data["account_number"]
            )
            acc_data = None
            if acc_resp is not None:
                try:
                    acc_data = acc_resp.json()
                except Exception:
                    acc_data = None

            if acc_data and acc_data.get("status") == "SUCCESS":
                serializer = Get9PSBWalletSerializer(acc_data.get("data", {}))
                response = {
                    "status": "success",
                    "message": "Account details for supplied account number retrieved successfully.",
                    "data": acc_data.get("data", {}),
                }
            else:
                account_details = WalletModel.objects.filter(
                    account_number=payload["account_number"]
                ).first()
                if account_details:
                    logger.info("Account found in local database.")
                    serializer = Get9PSBWalletSerializer(account_details)
                    response = {
                        "status": "success",
                        "message": "Account details for supplied account number retrieved successfully.",
                        "data": {
                            "account_number": serializer.data["account_number"],
                            "acc_name": account_details.acct_name,
                        },
                    }
                else:
                    response = {
                        "status": "fail",
                        "message": "user does not have an account with Picadailys.",
                        "data": serializer.data,
                    }
        return Response(data=encrypt(response), status=status.HTTP_200_OK)


@extend_schema(
    summary="Validate an account at another bank",
    tags=["Banking"],
    description="Resolve an account number and bank code against the 9PSB NIP network and return the account holder's name.",
    request=GetAccountSerializer,
    responses={
        200: inline_serializer(
            name="ValidateOtherBankAccountResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "data": s.DictField(),
            },
        ),
        400: inline_serializer(
            name="ValidateOtherBankAccountErrorResponse",
            fields={"status": s.CharField(), "error": s.CharField()},
        ),
    },
)
class ValidateAccountOfOtherBank(generics.GenericAPIView):
    """
    ValidateAccountOfOtherBank handles the GET request of validating supplied account number
    and 3-digit bank code. It returns the account details upon success.
    """

    serializer_class = GetAccountSerializer
    permission_classes = (IsAuthenticated, (IsPartnerUserOrMember | IsBrandAd))

    def post(self, request):
        logger.info("Received request to validate and retrieve account details.")

        # Clean payload data
        decrypted_payload = decrypt(request.data)
        payload = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_payload.items()
        }

        serializer = GetAccountSerializer(data=payload)
        if serializer.is_valid():
            validated_data = serializer.validated_data
            logger.info(
                f"Validation successful for account number: {validated_data['account_number']} and bank code: {validated_data['bankCode']}"
            )

            # Call external API to retrieve account details
            acc_resp = Transfers.getAccount(
                acct_num=validated_data["account_number"],
                bank_code=validated_data["bankCode"],
            )

            if acc_resp.status_code == 200:
                logger.info("Successfully retrieved account details.")

                resp = {
                    "status": "success",
                    "message": "Account retrieve operation successful.",
                    "data": acc_resp.json(),
                }
                return Response(data=encrypt(resp), status=status.HTTP_200_OK)
            else:
                logger.error(
                    f"Failed to retrieve account details. Status code: {acc_resp.status_code}"
                )

                err_resp = {
                    "status": "fail",
                    "error": "Account retrieve operation failed.",
                    "data": acc_resp.json(),
                }
                return Response(data=encrypt(err_resp), status=acc_resp.status_code)
        else:
            logger.warning("Validation failed with errors: %s", serializer.errors)
            return Response(
                data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST
            )


@extend_schema(
    summary="Transfer funds to another Picadailys user (intra-bank)",
    tags=["Banking"],
    description="Send funds to another Picadailys/9PSB wallet. Requires an Idempotency-Key header to prevent duplicate debits. Authorization via PIN or biometrics. First 5 transfers to the same beneficiary per day are free; subsequent ones attract a ₦10 fee.",
    request=BankTransfersSerializer,
    parameters=[
        OpenApiParameter(
            name="Idempotency-Key",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.HEADER,
            required=True,
            description="Unique key per transfer request to ensure idempotency.",
        )
    ],
    responses={
        200: inline_serializer(
            name="IntraBankTransferResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "data": inline_serializer(
                    name="IntraBankTransferData",
                    fields={
                        "credit_account": s.CharField(),
                        "debit_account": s.CharField(),
                        "amount": s.CharField(),
                        "narration": s.CharField(),
                        "beneficiaryBank": s.CharField(),
                        "transactionReference": s.CharField(),
                    },
                ),
            },
        ),
        202: inline_serializer(
            name="IntraBankTransferPendingResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "transactionReference": s.CharField(),
            },
        ),
        400: inline_serializer(
            name="IntraBankTransferErrorResponse",
            fields={"status": s.CharField(), "error": s.CharField()},
        ),
        401: inline_serializer(
            name="IntraBankTransferUnauthorizedResponse",
            fields={"status": s.CharField(), "error": s.CharField()},
        ),
    },
)
class IntraBankTransfer(generics.CreateAPIView):
    """
    IntraBankTransfer handles the POST request of transferring funds to other
    picadailys customers.
    Implements race condition prevention via select_for_update() and
    idempotency via Idempotency-Key header.
    """

    serializer_class = BankTransfersSerializer
    permission_classes = (IsAuthenticated, (IsPartnerUserOrMember | IsBrandAd))
    throttle_scope = "wallet_transfer"

    @staticmethod
    def _generate_transaction_id(prefix):
        timestamp = str(int(time.time()))[-10:]
        rand_suffix = "".join(
            random.choices(string.ascii_uppercase + string.digits, k=4)
        )
        return f"{prefix}{timestamp}{rand_suffix}"

    def post(self, request):
        authenticated_user = request.user
        logger.info(f"Received transfer request from user: {authenticated_user.id}")

        # Extract idempotency key from request headers or body
        idempotency_key = request.headers.get("Idempotency-Key")

        if not idempotency_key:
            logger.warning("Idempotency-Key header is missing.")
            return Response(
                data=encrypt(
                    {"status": "fail", "error": "Idempotency-Key header required"}
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        decrypted_payload = decrypt(request.data)
        payload = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_payload.items()
        }
        serializer = BankTransfersSerializer(data=payload)
        if not serializer.is_valid():
            logger.warning("Transfer request validation failed.")
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Check if this idempotency key was already processed
            existing_tx = TxModel.objects.filter(
                user=authenticated_user, tx_reference=idempotency_key
            ).first()

            if existing_tx:
                logger.info(
                    f"Duplicate request detected for idempotency key: {idempotency_key}"
                )

                # If still PENDING, return PENDING status
                if existing_tx.status == "PENDING":
                    return Response(
                        data=encrypt(
                            {"status": "pending", "message": "Transfer in progress"}
                        ),
                        status=status.HTTP_202_ACCEPTED,
                    )

                # If already successful, return same success response
                if existing_tx.status == "SUCCESS":
                    transfer = TransferModel.objects.filter(tx=existing_tx).first()
                    resp = {
                        "status": "success",
                        "message": "Transfer successful.",
                        "data": {
                            "credit_account": (
                                transfer.beneficiary_account_number
                                if transfer
                                else payload.get("beneficiary_account_number")
                            ),
                            "debit_account": (
                                transfer.sender_account_number
                                if transfer
                                else payload.get("sender_account_number")
                            ),
                            "amount": str(existing_tx.amount),
                            "narration": existing_tx.description,
                            "beneficiaryBank": "Picadailys/9PSB",
                            "transactionReference": idempotency_key,
                        },
                    }
                    return Response(data=encrypt(resp), status=status.HTTP_200_OK)

                # If failed, return same error
                return Response(
                    data=encrypt(
                        {"status": "fail", "error": "Previous transfer failed"}
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )

            with transaction.atomic():
                account = WalletModel.objects.select_for_update().get(
                    user=authenticated_user
                )

                pin = payload.get("pin")
                biometrics = payload.get("use_biometrics")

                if biometrics:
                    logger.info("Using biometrics for verification.")
                    verification = Biometrics.authenticate(
                        authenticated_user.phone_number
                    )
                else:
                    logger.info("Using PIN for verification.")
                    verification = Pin.verify(
                        user=authenticated_user, pin=pin, hashed_pin=account.pin
                    )

                if not verification:
                    logger.error("Verification failed: Incorrect PIN or biometrics.")
                    return Response(
                        data=encrypt({"status": "fail", "error": "Incorrect pin"}),
                        status=status.HTTP_401_UNAUTHORIZED,
                    )

                amount = Decimal(str(payload.get("amount")))

                beneficiary_account = payload.get("beneficiary_account_number")
                today = timezone.now().date()
                intra_count = TxModel.objects.filter(
                    user=authenticated_user,
                    tx_type="Intra-Bank Transfer",
                    transfers__beneficiary_account_number=beneficiary_account,
                    date__date=today,
                ).count()
                intra_merchant_fee = Decimal("10") if intra_count >= 5 else Decimal("0")
                total = amount + intra_merchant_fee

                if account.balance < total:
                    logger.error(
                        f"Insufficient balance. Available: {account.balance}, Required: {total}"
                    )
                    return Response(
                        data=encrypt(
                            {"status": "fail", "error": "Insufficient balance"}
                        ),
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                external_tx_id = self._generate_transaction_id(prefix="TRA")
                sender_name = account.acct_name
                account_number = account.account_number
                narration = _build_narration(sender_name, payload.get("description"))

                tx = TxModel.objects.create(
                    user=authenticated_user,
                    tx_reference=idempotency_key,
                    external_tx_reference=external_tx_id,
                    tx_type="Intra-Bank Transfer",
                    amount=str(total),
                    description=narration,
                    status="PENDING",
                )

            logger.info("Verification successful, proceeding with transfer.")
            transfer_resp = Transfers.initiate_transfer(
                bank_code=payload.get("beneficiary_bank_code"),
                account_number=payload.get("beneficiary_account_number"),
                name=payload.get("beneficiary_name"),
                sender_name=sender_name,
                sender_account_number=payload.get("sender_account_number"),
                amount=payload.get("amount"),
                description=narration,
                transactionType="INTRA_BANK",
                tx_ref=external_tx_id,
                merchant_fee=int(intra_merchant_fee) if intra_merchant_fee else None,
            )

            if transfer_resp is None:
                logger.error(
                    "Intra-bank transfer timed out, keeping PENDING for resolution."
                )
                resolve_pending_transfer.apply_async(
                    kwargs=dict(
                        tx_id=tx.id,
                        user_id=authenticated_user.id,
                        account_number=account_number,
                        external_tx_reference=external_tx_id,
                        beneficiary_account_number=payload.get(
                            "beneficiary_account_number"
                        ),
                        sender_full_name=sender_name,
                        amount_str=str(total),
                        narration=narration,
                        idempotency_key=idempotency_key,
                        alert_type=getattr(
                            authenticated_user, "alert_type_choice", "Both"
                        ),
                        phone_number=getattr(authenticated_user, "phone_number", None),
                        email=getattr(authenticated_user, "email", None),
                        beneficiary_name=payload.get("beneficiary_name"),
                    ),
                    countdown=30,
                )
                return Response(
                    data=encrypt(
                        {
                            "status": "pending",
                            "message": "Transfer is being processed. You will be notified once confirmed.",
                            "transactionReference": idempotency_key,
                        }
                    ),
                    status=status.HTTP_202_ACCEPTED,
                )

            if transfer_resp.status_code == 200:
                logger.info("Transfer successful, updating transaction status.")
                tx.status = "SUCCESS"
                tx.save(update_fields=["status"])

                post_transfer_update.delay(
                    user_id=authenticated_user.id,
                    tx_id=tx.id,
                    account_number=account_number,
                    beneficiary_account_number=payload.get(
                        "beneficiary_account_number"
                    ),
                    sender_full_name=sender_name,
                    amount_str=str(total),
                    narration=narration,
                    idempotency_key=idempotency_key,
                    alert_type=getattr(authenticated_user, "alert_type_choice", "Both"),
                    phone_number=getattr(authenticated_user, "phone_number", None),
                    email=getattr(authenticated_user, "email", None),
                    beneficiary_name=payload.get("beneficiary_name"),
                )

                resp_data = {
                    "credit_account": payload.get("beneficiary_account_number"),
                    "debit_account": payload.get("sender_account_number"),
                    "amount": str(amount),
                    "narration": narration,
                    "beneficiaryBank": "Picadailys/9PSB",
                    "transactionReference": idempotency_key,
                    "total_debited": str(total),
                }
                if intra_merchant_fee:
                    resp_data["merchant_fee"] = str(intra_merchant_fee)

                return Response(
                    data=encrypt(
                        {
                            "status": "success",
                            "message": "Transfer successful.",
                            "data": resp_data,
                        }
                    ),
                    status=status.HTTP_200_OK,
                )
            else:
                logger.error("Transfer failed, received error from external service.")
                tx.status = "FAILED"
                tx.save(update_fields=["status"])
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "error": "Transfer failed.",
                            "data": transfer_resp.json(),
                        }
                    ),
                    status=transfer_resp.status_code,
                )

        except WalletModel.DoesNotExist:
            logger.error(f"Account for user {authenticated_user.id} not found.")
            return Response(
                data=encrypt({"status": "fail", "error": "Account not found"}),
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as e:
            logger.exception(f"Unexpected error during transfer: {str(e)}")
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "error": "An error occurred. Please try again later.",
                    }
                ),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


@extend_schema(
    summary="Get remaining free intra-bank transfer count for today",
    tags=["Banking"],
    description="Return how many free intra-bank transfers the authenticated user has remaining today for a given beneficiary account. Each user gets 5 free transfers per beneficiary per day.",
    parameters=[
        OpenApiParameter(
            name="beneficiary_account_number",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            required=True,
            description="The beneficiary account number to check the free transfer count against.",
        )
    ],
    responses={
        200: inline_serializer(
            name="IntraBankFreeCountResponse",
            fields={
                "status": s.CharField(),
                "free_transfers_used": s.IntegerField(),
                "free_transfers_remaining": s.IntegerField(),
                "free_limit": s.IntegerField(),
                "fee_after_limit": s.CharField(),
            },
        ),
        400: inline_serializer(
            name="IntraBankFreeCountErrorResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class IntraBankFreeTransferCount(APIView):
    """
    Returns how many free intra-bank transfers remain today for a given beneficiary.
    Each user gets 5 free transfers to the same beneficiary per day.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        beneficiary_account = request.query_params.get("beneficiary_account_number")
        if not beneficiary_account:
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "beneficiary_account_number is required.",
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        today = timezone.now().date()
        used = TxModel.objects.filter(
            user=request.user,
            tx_type="Intra-Bank Transfer",
            transfers__beneficiary_account_number=beneficiary_account,
            date__date=today,
        ).count()

        free_limit = 5
        remaining = max(0, free_limit - used)

        return Response(
            data=encrypt(
                {
                    "status": "success",
                    "free_transfers_used": used,
                    "free_transfers_remaining": remaining,
                    "free_limit": free_limit,
                    "fee_after_limit": "10.00",
                }
            ),
            status=status.HTTP_200_OK,
        )


@extend_schema(
    summary="Transfer funds to another bank (inter-bank NIP)",
    tags=["Banking"],
    description="Send funds via NIP to a beneficiary at any Nigerian bank. Requires an Idempotency-Key header. Transfer fees, VAT, and stamp duty are auto-calculated and deducted from the sender's balance.",
    request=BankTransfersSerializer,
    parameters=[
        OpenApiParameter(
            name="Idempotency-Key",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.HEADER,
            required=True,
            description="Unique key per transfer request to ensure idempotency.",
        )
    ],
    responses={
        200: inline_serializer(
            name="InterBankTransferResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "data": inline_serializer(
                    name="InterBankTransferData",
                    fields={
                        "credit_account": s.CharField(),
                        "debit_account": s.CharField(),
                        "amount": s.CharField(),
                        "vat": s.CharField(),
                        "total": s.CharField(),
                        "narration": s.CharField(),
                        "beneficiaryBank": s.CharField(),
                        "transactionReference": s.CharField(),
                    },
                ),
            },
        ),
        202: inline_serializer(
            name="InterBankTransferPendingResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "transactionReference": s.CharField(),
            },
        ),
        400: inline_serializer(
            name="InterBankTransferErrorResponse",
            fields={"status": s.CharField(), "error": s.CharField()},
        ),
        401: inline_serializer(
            name="InterBankTransferUnauthorizedResponse",
            fields={"status": s.CharField(), "error": s.CharField()},
        ),
    },
)
class InterBankTransfer(generics.CreateAPIView):
    """
    InterBankTransfer handles the POST request of transferring funds to other
    banks other than Picadialys/Providus users.
    Implements race condition prevention via select_for_update() and
    idempotency via Idempotency-Key header.
    """

    serializer_class = BankTransfersSerializer
    permission_classes = (IsAuthenticated, (IsPartnerUserOrMember | IsBrandAd))
    throttle_scope = "wallet_transfer"

    @staticmethod
    def _generate_transaction_id(prefix):
        timestamp = str(int(time.time()))[-10:]
        rand_suffix = "".join(
            random.choices(string.ascii_uppercase + string.digits, k=4)
        )
        return f"{prefix}{timestamp}{rand_suffix}"

    def post(self, request):
        authenticated_user = request.user
        logger.info(f"Received transfer request from user: {authenticated_user.id}")

        # Extract idempotency key from request headers or body
        idempotency_key = request.headers.get("Idempotency-Key")

        if not idempotency_key:
            logger.warning("Idempotency-Key header is missing.")
            return Response(
                data=encrypt(
                    {"status": "fail", "error": "Idempotency-Key header required"}
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        decrypted_payload = decrypt(request.data)
        payload = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_payload.items()
        }
        serializer = BankTransfersSerializer(data=payload)
        if not serializer.is_valid():
            logger.warning("Transfer request validation failed.")
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Check if this idempotency key was already processed
            existing_tx = TxModel.objects.filter(
                user=authenticated_user, tx_reference=idempotency_key
            ).first()

            if existing_tx:
                logger.info(
                    f"Duplicate request detected for idempotency key: {idempotency_key}"
                )

                # If still PENDING, return PENDING status
                if existing_tx.status == "PENDING":
                    return Response(
                        data=encrypt(
                            {"status": "pending", "message": "Transfer in progress"}
                        ),
                        status=status.HTTP_202_ACCEPTED,
                    )

                # If already successful, return same success response
                if existing_tx.status == "SUCCESS":
                    transfer = TransferModel.objects.filter(tx=existing_tx).first()
                    resp = {
                        "status": "success",
                        "message": "Transfer successful.",
                        "data": {
                            "credit_account": (
                                transfer.beneficiary_account_number
                                if transfer
                                else payload.get("beneficiary_account_number")
                            ),
                            "debit_account": (
                                transfer.sender_account_number
                                if transfer
                                else payload.get("sender_account_number")
                            ),
                            "amount": str(existing_tx.amount),
                            "narration": existing_tx.description,
                            "beneficiaryBank": payload.get("beneficiary_bank_code"),
                            "transactionReference": idempotency_key,
                        },
                    }
                    return Response(data=encrypt(resp), status=status.HTTP_200_OK)

                # If failed, return same error
                return Response(
                    data=encrypt(
                        {"status": "fail", "error": "Previous transfer failed"}
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )

            with transaction.atomic():
                account = WalletModel.objects.select_for_update().get(
                    user=authenticated_user
                )

                pin = payload.get("pin")
                biometrics = payload.get("use_biometrics")

                if biometrics:
                    logger.info("Using biometrics for verification.")
                    verification = Biometrics.authenticate(
                        authenticated_user.phone_number
                    )
                else:
                    logger.info("Using PIN for verification.")
                    verification = Pin.verify(
                        user=authenticated_user, pin=pin, hashed_pin=account.pin
                    )

                if not verification:
                    logger.error("Verification failed: Incorrect PIN or biometrics.")
                    return Response(
                        data=encrypt({"status": "fail", "error": "Incorrect pin"}),
                        status=status.HTTP_401_UNAUTHORIZED,
                    )

                amount = Decimal(str(payload.get("amount")))
                charge = TransferCharge.breakdown(amount)
                total = Decimal(charge["total"])

                if account.balance < total:
                    logger.error(
                        f"Insufficient balance. Available: {account.balance}, Required: {total}"
                    )
                    return Response(
                        data=encrypt(
                            {"status": "fail", "error": "Insufficient balance"}
                        ),
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                external_tx_id = self._generate_transaction_id(prefix="TRA")
                sender_name = account.acct_name
                account_number = account.account_number
                narration = _build_narration(sender_name, payload.get("description"))

                tx = TxModel.objects.create(
                    user=authenticated_user,
                    tx_reference=idempotency_key,
                    external_tx_reference=external_tx_id,
                    tx_type="Inter-Bank Transfer",
                    amount=charge["total"],
                    vat=charge["vat"],
                    transfer_fee=charge["transfer_fee"],
                    description=narration,
                    status="PENDING",
                )

            logger.info("Verification successful, proceeding with transfer.")
            transfer_resp = Transfers.initiate_transfer(
                bank_code=payload.get("beneficiary_bank_code"),
                account_number=payload.get("beneficiary_account_number"),
                name=payload.get("beneficiary_name"),
                sender_name=sender_name,
                sender_account_number=payload.get("sender_account_number"),
                amount=payload.get("amount"),
                description=narration,
                transactionType="INTER_BANK",
                tx_ref=external_tx_id,
                merchant_fee=charge["merchant_fee"],
            )

            if transfer_resp is None:
                logger.error(
                    "Inter-bank transfer timed out, keeping PENDING for resolution."
                )
                resolve_pending_transfer.apply_async(
                    kwargs=dict(
                        tx_id=tx.id,
                        user_id=authenticated_user.id,
                        account_number=account_number,
                        external_tx_reference=external_tx_id,
                        beneficiary_account_number=payload.get(
                            "beneficiary_account_number"
                        ),
                        sender_full_name=sender_name,
                        amount_str=charge["principal"],
                        narration=narration,
                        idempotency_key=idempotency_key,
                        alert_type=getattr(
                            authenticated_user, "alert_type_choice", "Both"
                        ),
                        phone_number=getattr(authenticated_user, "phone_number", None),
                        email=getattr(authenticated_user, "email", None),
                        beneficiary_name=payload.get("beneficiary_name"),
                    ),
                    countdown=30,
                )
                return Response(
                    data=encrypt(
                        {
                            "status": "pending",
                            "message": "Transfer is being processed. You will be notified once confirmed.",
                            "transactionReference": idempotency_key,
                        }
                    ),
                    status=status.HTTP_202_ACCEPTED,
                )

            if transfer_resp.status_code == 200:
                logger.info("Transfer successful, updating transaction status.")
                tx.status = "SUCCESS"
                tx.save(update_fields=["status"])

                post_transfer_update.delay(
                    user_id=authenticated_user.id,
                    tx_id=tx.id,
                    account_number=account_number,
                    beneficiary_account_number=payload.get(
                        "beneficiary_account_number"
                    ),
                    sender_full_name=sender_name,
                    amount_str=charge["principal"],
                    narration=narration,
                    idempotency_key=idempotency_key,
                    alert_type=getattr(authenticated_user, "alert_type_choice", "Both"),
                    phone_number=getattr(authenticated_user, "phone_number", None),
                    email=getattr(authenticated_user, "email", None),
                    beneficiary_name=payload.get("beneficiary_name"),
                )

                return Response(
                    data=encrypt(
                        {
                            "status": "success",
                            "message": "Transfer successful.",
                            "data": {
                                "credit_account": payload.get(
                                    "beneficiary_account_number"
                                ),
                                "debit_account": payload.get("sender_account_number"),
                                "amount": charge["principal"],
                                "vat": charge["vat"],
                                "total": charge["total"],
                                "narration": narration,
                                "beneficiaryBank": payload.get("beneficiary_bank_code"),
                                "transactionReference": idempotency_key,
                            },
                        }
                    ),
                    status=status.HTTP_200_OK,
                )
            else:
                logger.error("Transfer failed, received error from external service.")
                tx.status = "FAILED"
                tx.save(update_fields=["status"])
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "error": "Transfer failed.",
                            "data": transfer_resp.json(),
                        }
                    ),
                    status=transfer_resp.status_code,
                )

        except WalletModel.DoesNotExist:
            logger.error(f"Account for user {authenticated_user.id} not found.")
            return Response(
                data=encrypt({"status": "fail", "error": "Account not found"}),
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as e:
            logger.exception(f"Unexpected error during transfer: {str(e)}")
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "error": "An error occurred. Please try again later.",
                    }
                ),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


@extend_schema(
    summary="Get inter-bank transfer status by reference",
    tags=["Banking"],
    description="Query 9PSB for the current status of an inter-bank transfer using the transaction reference returned at initiation.",
    parameters=[
        OpenApiParameter(
            name="tx_reference",
            type=OpenApiTypes.INT,
            location=OpenApiParameter.PATH,
            required=True,
            description="The transaction reference number returned when the transfer was initiated.",
        )
    ],
    responses={
        200: inline_serializer(
            name="TransactionStatusResponse",
            fields={"status": s.CharField(), "data": s.DictField()},
        ),
        500: inline_serializer(
            name="TransactionStatusErrorResponse",
            fields={"status": s.CharField(), "error": s.CharField()},
        ),
    },
)
class TransactionStatus(generics.GenericAPIView):
    """
    TransactionStatus handles the GET request of validating the supplied single
    transaction reference and returns the current status of an inter-bank transaction.
    """

    serializer_class = GetTransferStatusSerializer
    permission_classes = (IsAuthenticated, (IsPartnerUserOrMember | IsBrandAd))

    def get(self, request, *args, **kwargs):
        tx_reference = kwargs.get("tx_reference")
        user_id = request.user.id
        logger.info(
            f"User {user_id} requested transaction status for reference: {tx_reference}"
        )

        # Check if transaction reference is provided
        if not tx_reference:
            logger.warning(
                f"Transaction reference not found in request by user {user_id}"
            )
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "Transaction reference not found",
                    }
                ),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Attempt to retrieve transaction status
        try:
            status_resp = Transfers.complete_transfer(
                transactionId=tx_reference,
            )
            if status_resp.get("status") == "SUCCESS":
                logger.info(
                    f"Transaction status retrieved successfully for reference {tx_reference}"
                )
                resp = {
                    "status": "success",
                    "data": status_resp.json(),
                }
                return Response(data=encrypt(resp), status=status.HTTP_200_OK)
            else:
                # Log failed status retrieval
                logger.error(
                    f"Failed to retrieve transaction status for reference {tx_reference}. Status code: {status_resp.status_code}"
                )
                err_resp = {
                    "status": "fail",
                    "error": "Could not retrieve transaction status.",
                    "data": status_resp.json(),
                }
                return Response(data=encrypt(err_resp), status=status_resp.status_code)
        except Exception as e:
            # Log exceptions that occur during the status retrieval
            logger.exception(
                f"Exception occurred while retrieving transaction status for reference {tx_reference}: {e}"
            )
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "error": "Internal server error while retrieving status",
                    }
                ),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


@extend_schema(
    summary="Generate Paystack checkout URL to fund with card",
    tags=["Banking"],
    description="Create a Paystack payment session for a guest user and return the checkout URL and access code. The X-Guest-ID header is required for guest identification.",
    request=PaymentURLSerializers,
    parameters=[
        OpenApiParameter(
            name="X-Guest-ID",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.HEADER,
            required=True,
            description="Unique identifier for the guest user making the card payment.",
        )
    ],
    responses={
        200: inline_serializer(
            name="BankingPayWithCardResponse",
            fields={
                "status": s.CharField(),
                "message": s.CharField(),
                "checkout_url": s.CharField(),
                "access_code": s.CharField(),
                "reference": s.CharField(),
            },
        ),
        400: inline_serializer(
            name="PayWithCardErrorResponse",
            fields={"status": s.CharField(), "error": s.CharField()},
        ),
    },
)
class PayWithCard(generics.CreateAPIView):
    """
    PayWithCard handles the POST request of funding your activities on Picadailys with Card.
    """

    serializer_class = PaymentURLSerializers
    permission_classes = (IsAuthenticated | IsGuestWithValidId,)

    def post(self, request):
        user_data = decrypt(request.data)
        authenticated_user = request.user if request.user.is_authenticated else None
        guest_id = request.headers.get("X-Guest-ID")

        if authenticated_user:
            user_data.setdefault("email", authenticated_user.email)

        caller_desc = (
            f"User {authenticated_user.id}"
            if authenticated_user
            else f"Guest User: {guest_id}"
        )
        logger.info(
            f"{caller_desc} initiated a PayWithCard request with data: {user_data}"
        )
        serializer = PaymentURLSerializers(data=user_data)
        if serializer.is_valid(raise_exception=True):
            try:
                amount_in_naira = int(Decimal(str(user_data["amount"])) * 100)
                checkout_url_response = Paystack.generate_url(
                    email=user_data["email"], amount=amount_in_naira
                )
                if checkout_url_response.status_code == 200:
                    url_resp = checkout_url_response.json()
                    logger.info(
                        f"Checkout URL generated successfully for {caller_desc} with reference {url_resp['data']['reference']}"
                    )
                    FundWithCard.objects.update_or_create(
                        txn_reference=url_resp["data"]["reference"],
                        defaults={
                            "email": user_data["email"],
                            "user": authenticated_user,
                            "purpose": serializer.validated_data.get(
                                "purpose", "wallet_topup"
                            ),
                        },
                    )
                    response = {
                        "status": "success",
                        "message": "Checkout URL generated successfully.",
                        "checkout_url": url_resp["data"]["authorization_url"],
                        "access_code": url_resp["data"]["access_code"],
                        "reference": url_resp["data"]["reference"],
                    }
                    return Response(data=encrypt(response), status=status.HTTP_200_OK)
                else:
                    logger.error(
                        f"Failed to generate checkout URL for {caller_desc}. Status code: {checkout_url_response.status_code}"
                    )
                    return Response(
                        data=encrypt(checkout_url_response.json()),
                        status=checkout_url_response.status_code,
                    )
            except Exception as e:
                logger.exception(
                    f"Exception occurred while generating checkout URL for {caller_desc}: {e}"
                )
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "error": "Internal server error during checkout URL generation",
                        }
                    ),
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
        else:
            logger.warning(
                f"Validation failed for PayWithCard request by {caller_desc} with errors: {serializer.errors}"
            )
            return Response(
                data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST
            )


@extend_schema(
    summary="Credit wallet after confirmed Paystack card payment",
    tags=["Banking"],
    description="Credit a user's 9PSB wallet following a verified Paystack card transaction. Also awards the ₦500 welcome bonus if the funded amount is ≥ ₦2,000 and the bonus has not yet been awarded.",
    request=FundWalletSerializers,
    responses={
        200: inline_serializer(
            name="FundWalletResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        400: inline_serializer(
            name="FundWalletErrorResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
        403: inline_serializer(
            name="FundWalletForbiddenResponse",
            fields={"status": s.CharField(), "message": s.CharField()},
        ),
    },
)
class FundWallet(generics.GenericAPIView):
    """
    FundWallet handles the POST request of funding your Picadailys wallet with Card.
    """

    serializer_class = FundWalletSerializers

    def post(self, request):
        user_data = decrypt(request.data)
        logger.info("FundWallet request initiated with data: %s", user_data)

        serializer = FundWalletSerializers(data=user_data)
        if not serializer.is_valid(raise_exception=True):
            logger.warning("Validation failed with errors: %s", serializer.errors)
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        email = user_data.get("email")
        amount = user_data.get("amount")
        tx_ref = user_data.get("tx_ref")
        logger.info(
            "Processing FundWallet for user with email: %s and tx_ref: %s",
            email,
            tx_ref,
        )

        # Retrieve the user or return a 404 response if not found
        user = get_object_or_404(User, email=email)
        logger.info("User %s found for wallet funding.", user.id)

        # Reserve the row under lock before doing anything else: is_processed
        # was previously only set True *after* the external Wallet.Credit
        # call succeeded, leaving a wide window where two concurrent/retried
        # requests for the same reference could both read is_processed=False
        # and both credit the wallet. Locking + marking processed up front
        # closes that race; a failed credit reverts it below so a genuine
        # retry can still go through.
        with transaction.atomic():
            funding = (
                FundWithCard.objects.select_for_update()
                .filter(user=user, txn_reference=tx_ref)
                .first()
            )
            if not funding:
                logger.error(
                    "Transaction reference %s does not exist or belong to user %s",
                    tx_ref,
                    user.id,
                )
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "message": "Transaction reference does not exist or belong to User",
                        }
                    ),
                    status=status.HTTP_403_FORBIDDEN,
                )

            if funding.is_processed:
                logger.warning(
                    "Transaction reference %s has already been processed for user %s",
                    tx_ref,
                    user.id,
                )
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "message": "Transaction has already been processed.",
                        }
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if funding.status != "success":
                logger.warning(
                    "Transaction reference %s has not been confirmed by Paystack yet (status=%s)",
                    tx_ref,
                    funding.status,
                )
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "message": "Card payment has not been confirmed yet.",
                        }
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Trust what Paystack actually confirmed for this reference, not
            # whatever the client claims - the client-supplied `amount` above
            # is otherwise unverified and forgeable. Pass the verified gross
            # straight through - 9PSB deducts its own flat transfer fee
            # automatically on every Wallet.Credit call, so pre-deducting
            # anything here double-charges the user (confirmed against real
            # transactions: a requested 95.38 landed as 73.88, exactly 21.50
            # short - the same flat gap seen crediting a raw 100 as 78.50).
            amount = Decimal(str(funding.amount))

            funding.is_processed = True
            funding.save(update_fields=["is_processed"])

        try:
            user_details = WalletModel.objects.get(user=user, walletType="INDIVIDUAL")
            transfer_resp = Wallet.Credit(
                acct_no=user_details.account_number,
                amount=float(amount),
                reason=f"You funded your wallet with {amount} using paystack.",
            )
            if transfer_resp.status_code == 200:
                logger.info("Transfer successful for user %s.", user.id)

                # Award welcome bonus if user opened wallet and funded >= 2000 NGN
                try:
                    funded_amount = Decimal(str(amount))
                except Exception:
                    funded_amount = Decimal("0.00")

                if funded_amount >= Decimal("2000.00"):
                    try:
                        with transaction.atomic():
                            counter, _ = WelcomeBonusCounter.objects.get_or_create(id=1)
                            # lock counter row to prevent race conditions
                            counter = (
                                WelcomeBonusCounter.objects.select_for_update().get(
                                    id=counter.id
                                )
                            )

                            already_awarded = WelcomeBonusAward.objects.filter(
                                user=user
                            ).exists()
                            if (not already_awarded) and counter.awarded_count < 1000:
                                WelcomeBonusAward.objects.create(
                                    user=user, amount=Decimal("500.00")
                                )
                                counter.awarded_count = counter.awarded_count + 1
                                counter.save()

                                # mark on user model for convenience
                                try:
                                    user.welcome_bonus = 500
                                    user.has_bonus = True
                                    user.save()
                                except Exception:
                                    logger.exception(
                                        "Failed to set flags on user after awarding welcome bonus"
                                    )

                                UserNotification.objects.create(
                                    user=user,
                                    title="Welcome Bonus",
                                    message="You have been credited with a ₦500 welcome bonus. Use it for purchases.",
                                )
                                ActivityModel.objects.create(
                                    user=user,
                                    title="Welcome Bonus",
                                    description=f"{user.first_name} {user.last_name} was awarded a ₦500 welcome bonus.",
                                )
                    except Exception:
                        logger.exception(
                            "Error while attempting to award welcome bonus"
                        )

                # No TxModel/TransferModel written here on purpose: this is
                # the gross, pre-9PSB-fee amount, not what actually lands.
                # InflowsWebhookNotificationView creates the authoritative
                # TxModel (real net amount, SUCCESS status) once 9PSB
                # confirms the settlement, and sends the one user-facing
                # notification for this event.
                ActivityModel.objects.create(
                    user=user,
                    title="Wallet Funding",
                    description=f"{user.first_name} {user.last_name} funded their account with ₦{amount}. Available balance is ₦{user_details.balance}.",
                )
                logger.info("Activity log created for user %s", user.id)

                resp = {
                    "status": "success",
                    "message": "Transfer successful.",
                }
                return Response(data=encrypt(resp), status=status.HTTP_200_OK)
            else:
                logger.error(
                    "Transfer failed with status code: %s, response: %s",
                    transfer_resp.status_code,
                    transfer_resp.json(),
                )
                FundWithCard.objects.filter(pk=funding.pk).update(is_processed=False)
                return Response(
                    data=encrypt(
                        {
                            "status": "fail",
                            "message": "Transaction failed, refund will be issued shortly.",
                            "data": transfer_resp.json(),
                        }
                    ),
                    status=transfer_resp.status_code,
                )

        except Exception as e:
            logger.exception(
                "An error occurred during wallet funding for user %s: %s",
                user.id,
                str(e),
            )
            FundWithCard.objects.filter(pk=funding.pk).update(is_processed=False)
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "Internal server error during wallet funding",
                    }
                ),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
