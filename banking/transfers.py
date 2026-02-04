import logging
import string
import random
import time
from decimal import Decimal

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string

from drf_spectacular.utils import extend_schema

from permissions import (
    IsPartnerUserOrMember,
    IsBrandAd,
    IsAuthenticatedOrGuestWithValidId,
)
from commons import generate_txId, Messaging, Biometrics

# Third party imports.
from rest_framework import generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from rest_framework_simplejwt.authentication import JWTAuthentication

# In-projects imports.
from .helpers import Pin
from accounts.models import TxModel, UserNotification, User
from roles.models import ActivityModel
from .controllers import Transfers, Paystack, Wallet
from .models import TransferModel, WalletModel, FundWithCard
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


class GetAllBanks(APIView):
    """
    GetAllBanks handles the GET request of retrieving all available financial
    institutions and their banks codes.
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, (IsPartnerUserOrMember | IsBrandAd))

    def get(self, request):
        logger.info("Received request to retrieve all financial institutions.")

        # Call Transfers service to get all banks
        all_banks_resp = Transfers.getAllBanks()
        if all_banks_resp.json().get("status") == "SUCCESS":
            logger.info("Successfully retrieved financial institutions data.")

            resp = {
                "status": "success",
                "message": "All financial institutions retrieved successfully.",
                "data": all_banks_resp.json()["data"],
            }
            return Response(data=encrypt(resp), status=status.HTTP_200_OK)
        else:
            logger.error(
                f"Failed to retrieve financial institutions. Status code: {all_banks_resp.status_code}"
            )

            err_resp = {
                "status": "fail",
                "error": "Could not retrieve financial institution.",
                "data": all_banks_resp.json()["data"],
            }
            return Response(data=encrypt(err_resp), status=all_banks_resp.status_code)


class Get9PSBWallet(generics.GenericAPIView):
    """
    Get9PSBWallet handles the GET request of validating supplied account number
    It returns the account details upon success.
    """

    serializer_class = Get9PSBWalletSerializer
    authentication_classes = [JWTAuthentication]
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

            if acc_resp and acc_resp.get("status") == "SUCCESS":
                serializer = Get9PSBWalletSerializer(acc_resp.get("data", {}))
                response = {
                    "status": "success",
                    "message": "Account details for supplied account number retrieved successfully.",
                    "data": acc_resp.get("data", {}),
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


class ValidateAccountOfOtherBank(generics.GenericAPIView):
    """
    ValidateAccountOfOtherBank handles the GET request of validating supplied account number
    and 3-digit bank code. It returns the account details upon success.
    """

    serializer_class = GetAccountSerializer
    authentication_classes = [JWTAuthentication]
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


class IntraBankTransfer(generics.CreateAPIView):
    """
    IntraBankTransfer handles the POST request of transferring funds to other
    picadailys customers.
    Implements race condition prevention via select_for_update() and
    idempotency via Idempotency-Key header.
    """

    serializer_class = BankTransfersSerializer
    authentication_classes = [JWTAuthentication]
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
        idempotency_key = request.headers.get("Idempotency-Key") or request.data.get(
            "idempotency_key"
        )

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
                            "credit_account": transfer.beneficiary_account_number
                            if transfer
                            else payload.get("beneficiary_account_number"),
                            "debit_account": transfer.sender_account_number
                            if transfer
                            else payload.get("sender_account_number"),
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

            # Use select_for_update() to lock the wallet row during atomic transaction
            with transaction.atomic():
                account = WalletModel.objects.select_for_update().get(  # Lock the row to prevent race conditions
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

                # Check balance before proceeding
                amount = Decimal(str(payload.get("amount")))
                if account.balance < amount:
                    logger.error(
                        f"Insufficient balance. Available: {account.balance}, Required: {amount}"
                    )
                    return Response(
                        data=encrypt(
                            {"status": "fail", "error": "Insufficient balance"}
                        ),
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                logger.info("Verification successful, proceeding with transfer.")

                # Generate TRA-prefixed transaction ID for third party (max 18 chars)
                external_tx_id = self._generate_transaction_id(prefix="TRA")

                # Record transaction BEFORE external call with PENDING status
                tx = TxModel.objects.create(
                    user=authenticated_user,
                    tx_reference=idempotency_key,  # Use idempotency key for deduplication
                    external_tx_reference=external_tx_id,  # TRA-prefixed ID for third party
                    tx_type="Intra-Bank Transfer",
                    amount=payload.get("amount"),
                    description=payload.get("description"),
                    status="PENDING",  # Mark as pending until confirmed
                )

                transfer_resp = Transfers.initiate_transfer(
                    bank_code=payload.get("beneficiary_bank_code"),
                    account_number=payload.get("beneficiary_account_number"),
                    name=payload.get("beneficiary_name"),
                    sender_name=account.acct_name,
                    sender_account_number=payload.get("sender_account_number"),
                    amount=payload.get("amount"),
                    description=payload.get("description"),
                    transactionType="INTRA_BANK",
                    tx_ref=external_tx_id,  # Pass TRA-prefixed ID to external service
                )

                if transfer_resp.status_code == 200:
                    logger.info(
                        "Transfer successful, updating balance and transaction status."
                    )

                    # Update balance atomically
                    account.balance -= amount
                    account.save(update_fields=["balance"])
                    # Mark transaction as successful
                    tx.status = "SUCCESS"
                    tx.save(update_fields=["status"])

                    TransferModel.objects.create(
                        user=authenticated_user,
                        tx=tx,
                        beneficiary_account_number=payload.get(
                            "beneficiary_account_number"
                        ),
                        sender_name=authenticated_user.full_name,
                        amount=payload.get("amount"),
                        available_balance=account.balance,
                    )

                    # Notify user
                    message = f"Dear {authenticated_user.full_name},\nYour transfer of ₦{payload['amount']} has been confirmed. Your available balance is ₦{account.balance}."
                    UserNotification.objects.create(
                        user=authenticated_user,
                        title="Bank Transfer",
                        message=message,
                    )
                    ActivityModel.objects.create(
                        user=authenticated_user,
                        title="Bank Transfer",
                        description=f"{authenticated_user.first_name} {authenticated_user.last_name} made a transfer of ₦{payload['amount']}. Available balance is ₦{account.balance}.",
                    )

                    logger.info(
                        f"Transfer notification sent to user {authenticated_user.id}."
                    )

                    resp = {
                        "status": "success",
                        "message": "Transfer successful.",
                        "data": {
                            "credit_account": payload.get("beneficiary_account_number"),
                            "debit_account": payload.get("sender_account_number"),
                            "amount": payload.get("amount"),
                            "narration": payload.get("description"),
                            "beneficiaryBank": "Picadailys/9PSB",
                            "transactionReference": idempotency_key,
                        },
                    }
                    return Response(data=encrypt(resp), status=status.HTTP_200_OK)
                else:
                    logger.error(
                        "Transfer failed, received error from external service."
                    )

                    # Mark transaction as failed
                    tx.status = "FAILED"
                    tx.save(update_fields=["status"])

                    err_resp = {
                        "status": "fail",
                        "error": "Transfer failed.",
                        "data": transfer_resp.json(),
                    }
                    return Response(
                        data=encrypt(err_resp), status=transfer_resp.status_code
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


class InterBankTransfer(generics.CreateAPIView):
    """
    InterBankTransfer handles the POST request of transferring funds to other
    banks other than Picadialys/Providus users.
    Implements race condition prevention via select_for_update() and
    idempotency via Idempotency-Key header.
    """

    serializer_class = BankTransfersSerializer
    authentication_classes = [JWTAuthentication]
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
        idempotency_key = request.headers.get("Idempotency-Key") or request.data.get(
            "idempotency_key"
        )

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
                            "credit_account": transfer.beneficiary_account_number
                            if transfer
                            else payload.get("beneficiary_account_number"),
                            "debit_account": transfer.sender_account_number
                            if transfer
                            else payload.get("sender_account_number"),
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

            # Use select_for_update() to lock the wallet row during atomic transaction
            with transaction.atomic():
                account = WalletModel.objects.select_for_update().get(  # Lock the row to prevent race conditions
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

                # Check balance before proceeding
                amount = Decimal(str(payload.get("amount")))
                if account.balance < amount:
                    logger.error(
                        f"Insufficient balance. Available: {account.balance}, Required: {amount}"
                    )
                    return Response(
                        data=encrypt(
                            {"status": "fail", "error": "Insufficient balance"}
                        ),
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                logger.info("Verification successful, proceeding with transfer.")

                # Generate TRA-prefixed transaction ID for third party (max 18 chars)
                external_tx_id = self._generate_transaction_id(prefix="TRA")

                # Record transaction BEFORE external call with PENDING status
                tx = TxModel.objects.create(
                    user=authenticated_user,
                    tx_reference=idempotency_key,  # Use idempotency key for deduplication
                    external_tx_reference=external_tx_id,  # TRA-prefixed ID for third party
                    tx_type="Inter-Bank Transfer",
                    amount=payload.get("amount"),
                    description=payload.get("description"),
                    status="PENDING",  # Mark as pending until confirmed
                )

                transfer_resp = Transfers.initiate_transfer(
                    bank=payload.get("beneficiary_bank_code"),
                    account_number=payload.get("beneficiary_account_number"),
                    name=payload.get("beneficiary_name"),
                    sender_name=account.acct_name,
                    sender_account_number=payload.get("sender_account_number"),
                    amount=payload.get("amount"),
                    description=payload.get("description"),
                    transactionType="INTER_BANK",
                    tx_ref=external_tx_id,  # Pass TRA-prefixed ID to external service
                )

                if transfer_resp.status_code == 200:
                    logger.info(
                        "Transfer successful, updating balance and transaction status."
                    )

                    # Update balance atomically
                    account.balance -= amount
                    account.save(update_fields=["balance"])

                    # Mark transaction as successful
                    tx.status = "SUCCESS"
                    tx.save(update_fields=["status"])

                    TransferModel.objects.create(
                        user=authenticated_user,
                        tx=tx,
                        beneficiary_account_number=payload.get(
                            "beneficiary_account_number"
                        ),
                        source_account_name=authenticated_user.full_name,
                        amount=payload.get("amount"),
                        available_balance=account.balance,
                    )

                    # Notify user
                    message = f"Dear {authenticated_user.full_name},\nYour transfer of ₦{payload['amount']} has been confirmed. Your available balance is ₦{account.balance}."
                    UserNotification.objects.create(
                        user=authenticated_user,
                        title="Bank Transfer",
                        message=message,
                    )
                    ActivityModel.objects.create(
                        user=authenticated_user,
                        title="Bank Transfer",
                        description=f"{authenticated_user.first_name} {authenticated_user.last_name} made a transfer of ₦{payload['amount']}. Available balance is ₦{account.balance}.",
                    )

                    logger.info(
                        f"Transfer notification sent to user {authenticated_user.id}."
                    )

                    resp = {
                        "status": "success",
                        "message": "Transfer successful.",
                        "data": {
                            "credit_account": payload.get("beneficiary_account_number"),
                            "debit_account": payload.get("sender_account_number"),
                            "amount": payload.get("amount"),
                            "narration": payload.get("description"),
                            "beneficiaryBank": payload.get("beneficiary_bank_code"),
                            "transactionReference": idempotency_key,
                        },
                    }
                    return Response(data=encrypt(resp), status=status.HTTP_200_OK)
                else:
                    logger.error(
                        "Transfer failed, received error from external service."
                    )

                    # Mark transaction as failed
                    tx.status = "FAILED"
                    tx.save(update_fields=["status"])

                    err_resp = {
                        "status": "fail",
                        "error": "Transfer failed.",
                        "data": transfer_resp.json(),
                    }
                    return Response(
                        data=encrypt(err_resp), status=transfer_resp.status_code
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


class TransactionStatus(generics.GenericAPIView):
    """
    TransactionStatus handles the GET request of validating the supplied single
    transaction reference and returns the current status of an inter-bank transaction.
    """

    serializer_class = GetTransferStatusSerializer
    authentication_classes = [JWTAuthentication]
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


class PayWithCard(generics.CreateAPIView):
    """
    PayWithCard handles the POST request of funding your activities on Picadailys with Card.
    """

    serializer_class = PaymentURLSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticatedOrGuestWithValidId,)

    def post(self, request):
        user_data = decrypt(request.data)
        guest_email = user_data.get("email")
        guest_id = request.headers.get("X-Guest-ID")
        user = request.user if request.user.is_authenticated else None

        if user:
            logger.info(
                f"User {user.id} initiated a PayWithCard request with data: {user_data}"
            )
        elif guest_id:
            logger.info(
                f"Guest User: {guest_id} initiated a PayWithCard request with data: {user_data}"
            )
        serializer = PaymentURLSerializers(data=user_data)
        if serializer.is_valid(raise_exception=True):
            try:
                # Convert amount to kobo by multiplying by 100
                amount_in_naira = int(user_data["amount"]) * 100

                # Generate checkout URL using Paystack
                if user:
                    checkout_url_response = Paystack.generate_url(
                        email=user.email, amount=amount_in_naira
                    )
                    if checkout_url_response.status_code == 200:
                        # Log successful URL generation
                        url_resp = checkout_url_response.json()
                        logger.info(
                            f"Checkout URL generated successfully for user {user.id} with reference {url_resp['data']['reference']}"
                        )

                        # Save transaction in FundWithCard model
                        FundWithCard.objects.create(
                            user=user, txn_reference=url_resp["data"]["reference"]
                        )
                        response = {
                            "status": "success",
                            "message": "Checkout URL generated successfully.",
                            "checkout_url": url_resp["data"]["authorization_url"],
                            "access_code": url_resp["data"]["access_code"],
                            "reference": url_resp["data"]["reference"],
                        }
                        return Response(
                            data=encrypt(response), status=status.HTTP_200_OK
                        )
                    else:
                        # Log unsuccessful URL generation attempt
                        logger.error(
                            f"Failed to generate checkout URL for user {user.id}. Status code: {checkout_url_response.status_code}"
                        )
                        return Response(
                            data=encrypt(checkout_url_response.json()),
                            status=checkout_url_response.status_code,
                        )
                elif guest_id:
                    checkout_url_response = Paystack.generate_url(
                        email=guest_email, amount=amount_in_naira
                    )
                    if checkout_url_response.status_code == 200:
                        # Log successful URL generation
                        url_resp = checkout_url_response.json()
                        logger.info(
                            f"Checkout URL generated successfully for guest user {guest_id} with reference {url_resp['data']['reference']}"
                        )

                        # # Save transaction in FundWithCard model
                        # FundWithCard.objects.create(
                        #     user=user, txn_reference=url_resp["data"]["reference"]
                        # )
                        response = {
                            "status": "success",
                            "message": "Checkout URL generated successfully.",
                            "checkout_url": url_resp["data"]["authorization_url"],
                            "access_code": url_resp["data"]["access_code"],
                            "reference": url_resp["data"]["reference"],
                        }
                        return Response(
                            data=encrypt(response), status=status.HTTP_200_OK
                        )
                    else:
                        # Log unsuccessful URL generation attempt
                        logger.error(
                            f"Failed to generate checkout URL for guest user {guest_id}. Status code: {checkout_url_response.status_code}"
                        )
                        return Response(
                            data=encrypt(checkout_url_response.json()),
                            status=checkout_url_response.status_code,
                        )
            except Exception as e:
                # Log exceptions in checkout URL generation process
                if user:
                    logger.exception(
                        f"Exception occurred while generating checkout URL for user {user.id}: {e}"
                    )
                elif guest_id:
                    logger.exception(
                        f"Exception occurred while generating checkout URL for guest user {guest_id}: {e}"
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
            # Log validation errors
            if user:
                logger.warning(
                    f"Validation failed for PayWithCard request by user {user.id} with errors: {serializer.errors}"
                )
            elif guest_id:
                logger.warning(
                    f"Validation failed for PayWithCard request by guest user {guest_id} with errors: {serializer.errors}"
                )
            return Response(
                data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST
            )


class FundWallet(generics.GenericAPIView):
    """
    FundWallet handles the POST request of funding your Picadailys wallet with Card.
    """

    serializer_class = FundWalletSerializers

    @extend_schema(exclude=True)
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

        reference_exists = FundWithCard.objects.filter(
            user=user, txn_reference=tx_ref
        ).exists()
        if not reference_exists:
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

        user_details = WalletModel.objects.get(user=user)

        try:
            print(user_details.account_number)
            print(amount)
            transfer_resp = Wallet.Credit(
                acct_no=user_details.account_number,
                amount=amount,
                reason=f"You funded your wallet with {amount} using paystack.",
            )
            if transfer_resp.status_code == 200:
                tx_id = generate_txId()
                logger.info("Transfer successful. Transaction ID: %s", tx_id)

                tx = TxModel.objects.create(
                    user=user,
                    tx_reference="",
                    tx_type="Funding of wallet",
                    amount=amount,
                    description="You funded your wallet.",
                )
                TransferModel.objects.create(
                    user=user,
                    tx=tx,
                    beneficiary_account_number=user_details.account_number,
                    sender_name=user.first_name + " " + user.last_name,
                    amount=amount,
                )

                account = TransferModel.objects.filter(user=user).first()
                message = f"Dear {user.first_name} {user.last_name}, /n Your transfer of {amount} has been confirmed. Your available balance is ₦{account.available_balance}."

                UserNotification.objects.create(
                    user=user,
                    title="Wallet Funding",
                    message=f"Your transfer of ₦{amount} has been confirmed. Your available balance is ₦{account.available_balance}.",
                )
                logger.info("User notification created for user %s", user.id)

                ActivityModel.objects.create(
                    user=user,
                    title="Wallet Funding",
                    description=f"{user.first_name} {user.last_name} funded their account with ₦{amount}. Available balance is ₦{account.available_balance}.",
                )
                logger.info("Activity log created for user %s", user.id)

                text_content = render_to_string(
                    template_name="empty_email.html",
                    context={
                        "custom_text": message,
                        "support_email": "support@picadailys.com",
                        "picadailys_phone": [
                            "02012271894",
                            "02012271895",
                        ],
                    },
                )

                Messaging.send_email(
                    sender_email="notifications@picadailys.com",
                    body=message,
                    subject="Wallet Funding",
                    html_content=text_content,
                    email=user.email,
                )
                logger.info(
                    "Confirmation email sent to user %s at %s", user.id, user.email
                )

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
            return Response(
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "Internal server error during wallet funding",
                    }
                ),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
