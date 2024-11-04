from django.http import Http404

from permissions import IsPartnerUserOrMember, IsBrandAd
from commons import generate_txId, Message

# Third party imports.
from rest_framework import generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from rest_framework_simplejwt.authentication import JWTAuthentication

# In-projects imports.
from .helpers import Pin
from accounts.models import TxModel, UserNotification
from roles.models import ActivityModel
from .controllers import Transfers, Paystack
from .models import TransferModel, AccountCreation, FundWithCard
from .serializers import (
    GetProvidusAccountSerializer,
    GetAccountSerializer,
    InterBankTransfersSerializer,
    IntraBankTransfersSerializer,
    PaymentURLSerializers,
)


class GetAllBanks(APIView):
    """
    GetAllBanks handles the GET request of retrieving all available financial
    institutions and their banks codes.
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, (IsPartnerUserOrMember | IsBrandAd))

    def get(self, request):
        all_banks_resp = Transfers.getAllBanks()
        if all_banks_resp.status_code == 200:
            resp = {
                "status": "success",
                "message": "All financial institutions retrieved successfully.",
                "data": all_banks_resp.json(),
            }
            return Response(data=resp, status=status.HTTP_200_OK)
        else:
            err_resp = {
                "status": "fail",
                "error": "Could not retrieve financial institution.",
                "data": all_banks_resp.json(),
            }
            return Response(data=err_resp, status=all_banks_resp.status_code)


class GetProvidusAccount(generics.GenericAPIView):
    """
    GetProvidusAccount handles the GET request of validating supplied account numbber
    It returns the account details upon success.
    """

    serializer_class = GetProvidusAccountSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, (IsPartnerUserOrMember | IsBrandAd))

    def post(self, request):
        payload = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in request.data.items()
        }

        serializer = GetProvidusAccountSerializer(data=payload)
        if serializer.is_valid():
            validated_data = serializer.validated_data

            acc_resp = Transfers.getProvidusAccount(
                acct_num=validated_data["account_number"],
            )
            if acc_resp.status_code == 200:
                resp = {
                    "status": "success",
                    "message": "Account retrieve operation successful.",
                    "data": acc_resp.json(),
                }
                return Response(data=resp, status=status.HTTP_200_OK)
            else:
                err_resp = {
                    "status": "fail",
                    "error": "Account retrieve operation failed.",
                    "data": acc_resp.json(),
                }
                return Response(data=err_resp, status=acc_resp.status_code)
        else:
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class GetAccount(generics.GenericAPIView):
    """
    GetAccount handles the GET request of validating supplied account numbber
    and 3-digit bank code. It returns the account details upon success.
    """

    serializer_class = GetAccountSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, (IsPartnerUserOrMember | IsBrandAd))

    def post(self, request):
        payload = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in request.data.items()
        }

        serializer = GetAccountSerializer(data=payload)
        if serializer.is_valid():
            validated_data = serializer.validated_data
            acc_resp = Transfers.getAccount(
                acct_num=validated_data["account_number"],
                bank_code=validated_data["bankCode"],
            )

            if acc_resp.status_code == 200:
                resp = {
                    "status": "success",
                    "message": "Account retrieve operation successful.",
                    "data": acc_resp.json(),
                }
                return Response(data=resp, status=status.HTTP_200_OK)
            else:
                err_resp = {
                    "status": "fail",
                    "error": "Account retrieve operation failed.",
                    "data": acc_resp.json(),
                }
                return Response(data=err_resp, status=acc_resp.status_code)
        else:
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class IntraBankTransfer(generics.CreateAPIView):
    """
    IntraBankTransfer handles the POST request of transferring funds to other
    picadailys customers.
    """

    serializer_class = IntraBankTransfersSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, (IsPartnerUserOrMember | IsBrandAd))

    def post(self, request):
        authenticated_user = request.user

        payload = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in request.data.items()
        }
        serializer = IntraBankTransfersSerializer(data=payload)
        if not serializer.is_valid:
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        account = AccountCreation.objects.get(user=authenticated_user)
        pin = request.data.get("pin")
        verification = Pin.verify(
            user=authenticated_user, pin=pin, hashed_pin=account.pin
        )
        if verification:
            transfer_resp = Transfers.Intra_bank_transfer(
                creditAccount=payload["credit_account"],
                debitAccount=payload["debit_account"],
                transactionAmount=payload["transaction_amount"],
                narration=payload["narration"],
                transactionReference=payload["transaction_reference"],
            )
            tx_id = generate_txId()
            if transfer_resp.status_code == 200:
                tx = TxModel.objects.create(
                    user=authenticated_user,
                    tx_reference=payload["transaction_reference"],
                    tx_type="Transfer to Providus Account",
                    tx_id=tx_id,
                    amount=payload["transaction_amount"],
                    description=payload["narration"],
                )

                TransferModel.objects.create(
                    user=authenticated_user,
                    tx=tx,
                    beneficiary_account_number=payload["credit_account"],
                    source_account_name=authenticated_user.full_name,
                    transaction_amount=payload["transaction_amount"],
                )
                amount = payload["transaction_amount"]
                account = TransferModel.objects.filter(user=authenticated_user).first()
                message = f"Dear {authenticated_user.full_name}, /n Your transfer of ₦{amount} has been confirmed. Your available balance is ₦{account.available_balance}."

                UserNotification.objects.create(
                    user=authenticated_user,
                    title="Bank Transfer.",
                    message=f"Your transfer of ₦{amount} has been confirmed. Your available balance is ₦{account.available_balance}.",
                )

                ActivityModel.objects.create(
                    user=authenticated_user,
                    title="Bank Transfer.",
                    description=f"{authenticated_user.first_name} {authenticated_user.last_name} made a transfer of ₦{amount}. Available balance is ₦{account.available_balance}.",
                )
                # send email notification to the User.
                Message.send_email(
                    subject="Debit Transaction.",
                    content=message,
                    email=authenticated_user.email,
                )
                resp = {
                    "status": "success",
                    "message": "Transfer succussful.",
                    "data": {
                        "credit_account": payload["credit_account"],
                        "debit_account": payload["debit_account"],
                        "amount": payload["transaction_amount"],
                        "narration": payload["narration"],
                        "beneficiaryBank": "Providus Bank",
                        "transactionReference": payload["transaction_reference"],
                    },
                }
                return Response(data=resp, status=status.HTTP_200_OK)
            else:
                err_resp = {
                    "status": "fail",
                    "error": "Transfer failed.",
                    "data": transfer_resp.json(),
                }
                return Response(data=err_resp, status=transfer_resp.status_code)
        else:
            return Response(
                data={"status": "fail", "error": "Incorrect pin"},
                status=status.HTTP_401_UNAUTHORIZED,
            )


class InterBankTransfer(generics.CreateAPIView):
    """
    InterBankTransfer handles the POST request of transferring funds to other
    banks other than Picadialys/Providus users.
    """

    serializer_class = InterBankTransfersSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, (IsPartnerUserOrMember | IsBrandAd))

    def post(self, request):
        authenticated_user = request.user

        payload = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in request.data.items()
        }
        serializer = InterBankTransfersSerializer(data=payload)
        if not serializer.is_valid:
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        account = AccountCreation.objects.get(user=authenticated_user)
        pin = request.data.get("pin")
        verification = Pin.verify(
            user=authenticated_user, pin=pin, hashed_pin=account.pin
        )
        if verification:
            transfer_resp = Transfers.Inter_bank_transfer(
                beneficiaryAccountName=payload["beneficiary_account_name"],
                transactionAmount=payload["transaction_amount"],
                narration=payload["narration"],
                beneficiaryBank=payload["beneficiary_bank"],
                transactionReference=payload["transaction_reference"],
                beneficiaryAccountNumber=payload["beneficiary_account_number"],
            )
            tx_id = generate_txId()
            if transfer_resp.status_code == 200:
                tx = TxModel.objects.create(
                    user=authenticated_user,
                    tx_reference=payload["transaction_reference"],
                    tx_type="Transfer to Bank Account",
                    tx_id=tx_id,
                    amount=payload["transaction_amount"],
                    description=payload["narration"],
                )

                TransferModel.objects.create(
                    user=authenticated_user,
                    tx=tx,
                    beneficiary_account_name=payload["beneficiary_account_name"],
                    beneficiary_account_number=payload["beneficiary_account_number"],
                    source_account_name=authenticated_user.full_name,
                    beneficiary_bank=payload["beneficiary_bank"],
                    transaction_amount=payload["transaction_amount"],
                )
                amount = payload["transaction_amount"]
                message = f"Dear {authenticated_user.full_name}, /n Your transfer of ₦{amount} has been confirmed. Your available balance is ₦{account.available_balance}."

                UserNotification.objects.create(
                    user=authenticated_user,
                    title="Bank Transfer.",
                    message=f"Your transfer of ₦{amount} has been confirmed. Your available balance is ₦{account.available_balance}.",
                )

                ActivityModel.objects.create(
                    user=authenticated_user,
                    title="Bank Transfer.",
                    description=f"{authenticated_user.first_name} {authenticated_user.last_name} made a transfer of ₦{amount}. Available balance is ₦{account.available_balance}.",
                )
                # send email notification to the User.
                Message.send_email(
                    subject="Debit Transaction.",
                    content=message,
                    email=authenticated_user.email,
                )

                resp = {
                    "status": "success",
                    "message": "Transfer succussful.",
                    "data": {
                        "recipient_name": payload["beneficiary_account_name"],
                        "beneficiary_account_number": payload[
                            "beneficiary_account_number"
                        ],
                        "amount": payload["transaction_amount"],
                        "narration": payload["narration"],
                        "beneficiaryBank": payload["beneficiary_bank"],
                        "transactionReference": payload["transaction_reference"],
                    },
                }
                return Response(data=resp, status=status.HTTP_200_OK)
            else:
                err_resp = {
                    "status": "fail",
                    "error": "Transfer failed.",
                    "data": transfer_resp.json(),
                }
                return Response(data=err_resp, status=transfer_resp.status_code)
        else:
            return Response(
                data={"status": "fail", "error": "Incorrect pin"},
                status=status.HTTP_401_UNAUTHORIZED,
            )


class IntraBankTransactionStatus(generics.GenericAPIView):
    """
    IntraBankTransactionStatus handles the GET request of validating the supplied single
    transaction reference and returns the current status of the transaction
    between two Providus Accounts.
    """

    serializer_class = InterBankTransfersSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, (IsPartnerUserOrMember | IsBrandAd))

    def get(self, request, *args, **kwargs):
        tx_reference = kwargs.get("tx_reference")
        if not tx_reference:
            raise Http404("Transaction reference not found")

        status_resp = Transfers.IntraBankStatus(
            transactionReference=tx_reference,
        )
        if status_resp.status_code == 200:
            resp = {
                "status": "success",
                "data": status_resp.json(),
            }
            return Response(data=resp, status=status.HTTP_200_OK)
        else:
            err_resp = {
                "status": "fail",
                "error": "Could not retrieve transaction status.",
                "data": status_resp.json(),
            }
            return Response(data=err_resp, status=status_resp.status_code)


class InterBankTransactionStatus(generics.GenericAPIView):
    """
    InterBankTransactionStatus handles the GET request of validating the supplied single transaction
    reference and returns the current status of the transaction.
    """

    serializer_class = InterBankTransfersSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, (IsPartnerUserOrMember | IsBrandAd))

    def get(self, request, *args, **kwargs):
        tx_reference = kwargs.get("tx_reference")
        if not tx_reference:
            raise Http404("Transaction reference not found")

        status_resp = Transfers.InterBankStatus(
            transactionReference=tx_reference,
        )
        if status_resp.status_code == 200:
            resp = {
                "status": "success",
                "data": status_resp.json(),
            }
            return Response(data=resp, status=status.HTTP_200_OK)
        else:
            err_resp = {
                "status": "fail",
                "error": "Could not retrieve transaction status.",
                "data": status_resp.json(),
            }
            return Response(data=err_resp, status=status_resp.status_code)


class FundWalletWithCard(generics.CreateAPIView):
    """
    FundWalletWithCard handles the POST request of funding your Picadailys wallet with Card.
    """

    serializer_class = InterBankTransfersSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, (IsPartnerUserOrMember | IsBrandAd))

    def post(self, request):
        user_data = request.data
        user = request.user

        serializer = PaymentURLSerializers(data=user_data)
        if serializer.is_valid(raise_exception=True):
            chaekout_url_response = Paystack.generate_url(
                email=user.email, amount=user_data["amount"]
            )

            if chaekout_url_response.status_code == 200:
                url_resp = chaekout_url_response.json()
                FundWithCard.objects.create(
                    user=user, txn_reference=url_resp["data"]["reference"]
                )
                response = {
                    "status": "success",
                    "message": "Chekcout url generated successfully.",
                    "checkout_url": url_resp["data"]["authorization_url"],
                    "access_code": url_resp["data"]["access_code"],
                    "reference": url_resp["data"]["reference"],
                }
                return Response(data=response, status=status.HTTP_200_OK)
            else:
                return Response(
                    data=chaekout_url_response.json(),
                    status=chaekout_url_response.status_code,
                )

        else:
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)
