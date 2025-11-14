# Third party imports.
from rest_framework import serializers

from accounts.models import TxModel

# In project imports.
from .models import (
    UserKYC,
    WalletModel,
    WalletUpgrade,
    BankingNotificationModel,
    TransferModel,
    FundWithCard,
)


class BankingStatusSerializer(serializers.Serializer):
    message = serializers.CharField(max_length=200)


class QuotationSerializer(serializers.Serializer):
    message = serializers.CharField(max_length=200)


class BVNSerializer(serializers.ModelSerializer):
    """Serailizers for our verify user bvn."""

    class Meta:
        model = UserKYC
        fields = [
            "id",
            "bvn",
            "bvn_phone",
        ]


class NINSerializer(serializers.ModelSerializer):
    """Serailizers for our verify user nin."""

    class Meta:
        model = UserKYC
        fields = [
            "id",
            "nin",
            "nin_dob",
        ]


class WalletCreationSerializers(serializers.ModelSerializer):
    """Serailizers for creating a bank account for users."""

    bvn = serializers.CharField(max_length=12, write_only=True, required=True)

    class Meta:
        model = WalletModel
        fields = ["id", "account_name", "gender", "dateOfBirth", "email", "bvn"]


class Tier2WalletUpgradeSerializers(serializers.ModelSerializer):
    """Serailizers for upgrading wallet to tier2."""

    class Meta:
        model = WalletUpgrade
        fields = [
            "id",
            "lga",
            "state",
            "nin",
            "tier",
            "userPhoto",
            "idType",
            "idNumber",
            "idIssueDate",
            "idCardFront",
            "houseNumber",
            "streetName",
            "city",
            "pep",
            "customerSignature",
        ]


class Tier3WalletUpgradeSerializers(serializers.ModelSerializer):
    """Serailizers for upgrading wallet to a tier3."""

    class Meta:
        model = WalletUpgrade
        fields = ["id", "proofOfAddressVerification"]


class CreateWalletPinSerializer(serializers.ModelSerializer):
    """Serailizers for first time wallet pin setting."""

    pin2 = serializers.CharField(max_length=4, write_only=True, required=True)

    class Meta:
        model = WalletModel
        fields = ["id", "pin", "pin2"]


class VerifyPinOTPSerializer(serializers.Serializer):
    otp = serializers.CharField()


class ResetPinSerializer(serializers.ModelSerializer):
    otp = serializers.CharField(max_length=50, min_length=4)
    pin2 = serializers.CharField(max_length=4, write_only=True, required=True)

    class Meta:
        model = WalletModel
        fields = ("otp", "pin", "pin2")


class TxModelSerializer(serializers.ModelSerializer):
    class Meta:
        model = TxModel
        fields = [
            "tx_reference",
            "tx_type",
            "tx_id",
            "amount",
            "description",
            "rwd",
            "date",
        ]


class BankNtfnSerializer(serializers.ModelSerializer):
    class Meta:
        model = BankingNotificationModel
        fields = [
            "accountNumber",
            "reference",
            "narration",
            "dateTime",
            "amount",
            "transactionType",
            "accountBalance",
        ]


class Get9PSBWalletSerializer(serializers.Serializer):
    class Meta:
        model = WalletModel
        fields = [
            "account_number",
        ]


class WalletEnquirySerializer(serializers.Serializer):
    acct_name = serializers.CharField(source="name")
    account_number = serializers.CharField(source="nuban")
    customer_number = serializers.CharField(source="number")
    balance = serializers.DecimalField(
        source="availableBalance", max_digits=12, decimal_places=2
    )
    tier = serializers.CharField()


class WalletDetailsSerializer(serializers.ModelSerializer):
    balance = serializers.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        model = WalletModel
        fields = ["acct_name", "account_number", "customer_numnber", "balance", "tier"]


class GetProvidusAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = WalletModel
        fields = [
            "account_number",
        ]

    def validate_accountNumber(self, value):
        """Validate the account number format."""
        if (
            not value.isdigit() or len(value) != 10
        ):  # Assuming a 10-digit account number
            raise serializers.ValidationError(
                "Account number must be a 10-digit number."
            )
        return value


class GetAccountSerializer(serializers.ModelSerializer):
    bankCode = serializers.CharField(min_length=3, write_only=True, required=True)

    class Meta:
        model = WalletModel
        fields = ["account_number", "bankCode"]

    def validate_accountNumber(self, value):
        """Validate the account number format."""
        if (
            not value.isdigit() or len(value) != 10
        ):  # Assuming a 10-digit account number
            raise serializers.ValidationError(
                "Account number must be a 10-digit number."
            )
        return value

    def validate_bankCode(self, value):
        """Validate the bank code format."""
        if not value.isdigit() or not (
            3 <= len(value) <= 6
        ):  # Bank code must be between 3 and 6 digits
            raise serializers.ValidationError(
                "Bank code must be a number between 3 and 6 digits."
            )
        return value


class BankTransfersSerializer(serializers.ModelSerializer):
    pin = serializers.CharField(max_length=4, write_only=True, required=True)
    use_biometrics = serializers.BooleanField(required=False)

    class Meta:
        model = TransferModel
        fields = [
            "id",
            "pin",
            "use_biometrics",
            "beneficiary_name",
            "beneficiary_account_number",
            "beneficiary_bank_code",
            "sender_account_number",
            "description",
            "amount",
        ]


class GetTransferStatusSerializer(serializers.Serializer):
    class Meta:
        fields = [
            "transaction_reference",
        ]


class WalletStatusSerializer(serializers.ModelSerializer):
    status = serializers.SerializerMethodField()

    class Meta:
        model = WalletModel
        fields = [
            "account_number",
            "acct_name",
            "balance",
            "status",
            "created_at",
        ]

    def get_status(self, obj):
        return "Open" if obj.status else "Blocked"


class PaymentURLSerializers(serializers.ModelSerializer):
    class Meta:
        model = FundWithCard
        fields = ["id", "amount", "email"]


class VerifyCardDepositSerializers(serializers.ModelSerializer):
    class Meta:
        model = FundWithCard
        fields = ["id", "txn_reference"]


class RefundSerializers(serializers.ModelSerializer):
    guest_id = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = FundWithCard
        fields = ["guest_id", "txn_reference"]


class CustomerSerializer(serializers.Serializer):
    email = serializers.EmailField()


class DataSerializer(serializers.Serializer):
    id = serializers.CharField()
    reference = serializers.CharField()
    customer = CustomerSerializer()
    status = serializers.CharField()
    amount = serializers.IntegerField()


class WebhookSerializer(serializers.Serializer):
    event = serializers.CharField()
    data = DataSerializer()


class NotificationWebhookSerializer(serializers.Serializer):
    merchant = serializers.CharField()
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    sourceaccount = serializers.CharField()
    sourcebank = serializers.CharField()
    sendername = serializers.CharField()
    narration = serializers.CharField()
    nipsessionid = serializers.CharField()
    transactionref = serializers.CharField()
    accountnumber = serializers.CharField()
    orderref = serializers.CharField()
    code = serializers.CharField()
    message = serializers.CharField()


class FundWalletSerializers(serializers.Serializer):
    class Meta:
        model = FundWithCard
        fields = ["id", "amount", "email", "tx_ref"]
