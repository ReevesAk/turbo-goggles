# Third party imports.
from rest_framework import serializers

from accounts.models import TxModel

# In project imports.
from .models import (
    UserKYC,
    WalletModel,
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
        fields = ["id", "acct_name", "gender", "dateOfBirth", "email", "bvn"]


class Tier2WalletUpgradeSerializer(serializers.Serializer):
    # Database-sourced fields (optional from request)
    accountNumber = serializers.CharField(required=False)
    bvn = serializers.CharField(required=False)
    accountName = serializers.CharField(required=False)
    phoneNumber = serializers.CharField(required=False)
    email = serializers.EmailField(required=False)
    nin = serializers.CharField(required=False, allow_null=True, allow_blank=True)

    tier = serializers.CharField(default="2")
    userPhoto = serializers.CharField()
    idType = serializers.CharField()
    idNumber = serializers.CharField()
    idIssueDate = serializers.DateField()
    idExpiryDate = serializers.DateField()
    idCardFront = serializers.CharField()
    idCardBack = serializers.CharField()

    houseNumber = serializers.CharField()
    streetName = serializers.CharField()
    city = serializers.CharField()
    state = serializers.CharField()
    localGovernment = serializers.CharField()

    pep = serializers.BooleanField()
    utilityBill = serializers.CharField()

    nearestLandmark = serializers.CharField()
    placeOfBirth = serializers.CharField()
    customerSignature = serializers.CharField()

    pin = serializers.CharField(required=False, write_only=True)
    use_biometrics = serializers.BooleanField(default=False, write_only=True)


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
    sender_name = serializers.SerializerMethodField()
    sender_account_number = serializers.SerializerMethodField()
    beneficiary_name = serializers.SerializerMethodField()
    beneficiary_account_number = serializers.SerializerMethodField()

    class Meta:
        model = TxModel
        fields = [
            "tx_reference",
            "tx_type",
            "amount",
            "vat",
            "transfer_fee",
            "description",
            "rwd",
            "date",
            "sender_name",
            "sender_account_number",
            "beneficiary_name",
            "beneficiary_account_number",
        ]

    def _get_transfer(self, obj):
        transfers = obj.transfers.all()
        return transfers[0] if transfers else None

    def get_sender_name(self, obj):
        t = self._get_transfer(obj)
        if t:
            return t.sender_name
        if obj.tx_type == "Wallet Credit" and obj.description:
            import re

            match = re.search(r"Credit from (.+?) \(", obj.description)
            if match:
                return match.group(1)
        return None

    def get_sender_account_number(self, obj):
        t = self._get_transfer(obj)
        return t.sender_account_number if t else None

    def get_beneficiary_name(self, obj):
        t = self._get_transfer(obj)
        return t.beneficiary_name if t else None

    def get_beneficiary_account_number(self, obj):
        t = self._get_transfer(obj)
        return t.beneficiary_account_number if t else None

    def to_representation(self, instance):
        data = super().to_representation(instance)
        has_transfer = bool(instance.transfers.all())
        is_wallet_credit = instance.tx_type == "Wallet Credit"
        if not has_transfer and not is_wallet_credit:
            data.pop("sender_name", None)
            data.pop("sender_account_number", None)
            data.pop("beneficiary_name", None)
            data.pop("beneficiary_account_number", None)
        elif is_wallet_credit and not has_transfer:
            data.pop("sender_account_number", None)
            data.pop("beneficiary_name", None)
            data.pop("beneficiary_account_number", None)
        if data.get("vat") is None:
            data.pop("vat", None)
        if data.get("transfer_fee") is None:
            data.pop("transfer_fee", None)
        return data


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


class Get9PSBWalletSerializer(serializers.ModelSerializer):
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
    tier = serializers.CharField(source="tier_level")

    class Meta:
        model = WalletModel
        fields = [
            "acct_name",
            "account_number",
            "transactionTrackingRef",
            "balance",
            "tier",
        ]


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
    class Meta:
        model = WalletModel
        fields = [
            "account_number",
            "status",
            "created_at",
        ]

    def get_status(self, obj):
        return "STATUS" if obj.status else "SUSPENDED"


class PaymentURLSerializers(serializers.ModelSerializer):
    class Meta:
        model = FundWithCard
        fields = ["id", "amount", "email"]


# class VerifyCardDepositSerializers(serializers.ModelSerializer):
#     class Meta:
#         model = FundWithCard
#         fields = ["id", "txn_reference"]
#         extra_kwargs = {
#             "txn_reference": {"validators": []}
#         }


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


class TransferNotificationWebhookSerializer(serializers.Serializer):
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


class UpgradeNotificationWebhookSerializer(serializers.Serializer):
    accountnumber = serializers.CharField()
    status = serializers.CharField()
    message = serializers.CharField()


class FundWalletSerializers(serializers.Serializer):
    class Meta:
        model = FundWithCard
        fields = ["id", "amount", "email", "tx_ref"]


class AddressVerificationSerializer(serializers.Serializer):
    houseNumber = serializers.CharField()
    streetName = serializers.CharField()
    city = serializers.CharField()
    state = serializers.CharField()
    localGovernment = serializers.CharField()


_BUSINESS_TYPES = [
    "PARTNERSHIP",
    "NGO",
    "COOPERATIVE",
    "CORPORATIONS",
    "OTHERS",
    "SOLE_PROPRIETORSHIP",
    "SOCIAL_ENTERPRISE",
    "LIMITED_LIABILITY_COMPANY",
    "FRANCHISE",
]


class SubmitCorporateSerializer(serializers.Serializer):
    taxIDNo = serializers.CharField()
    businessName = serializers.CharField()
    email = serializers.EmailField()
    phoneNo = serializers.CharField()
    address = serializers.CharField()
    industrialSector = serializers.CharField()
    businessType = serializers.ChoiceField(choices=_BUSINESS_TYPES)
    companyRegDate = serializers.CharField()
    contactPersonFirstName = serializers.CharField()
    contactPersonLastName = serializers.CharField()
    registrationNumber = serializers.CharField()
    webAddress = serializers.CharField(required=False, allow_blank=True)
    dateIncorporated = serializers.CharField(required=False, allow_blank=True)
    businessCommencementDate = serializers.CharField(required=False, allow_blank=True)
    postalAddress = serializers.CharField(required=False, allow_blank=True)


class AccountStatementSerializer(serializers.Serializer):
    start_date = serializers.DateField(required=True)
    end_date = serializers.DateField(required=True)
    format = serializers.ChoiceField(choices=["PDF", "CSV"], default="PDF")

    def validate(self, attrs):
        if attrs["end_date"] < attrs["start_date"]:
            raise serializers.ValidationError(
                "End date must be greater than start date."
            )
        return attrs
