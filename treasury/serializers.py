from rest_framework import serializers

from accounts.models import TxModel
from .models import TreasuryAccount, TreasuryTransfer, TreasuryCardFunding


class TreasuryStatusSerializer(serializers.Serializer):
    message = serializers.CharField(max_length=200)


class CreateTreasuryAccountSerializer(serializers.Serializer):
    acct_name = serializers.CharField(max_length=150, required=True)


class CreateAccountPinSerializer(serializers.ModelSerializer):
    pin2 = serializers.CharField(max_length=4, write_only=True, required=True)

    class Meta:
        model = TreasuryAccount
        fields = ["id", "pin", "pin2"]


class VerifyPinOTPSerializer(serializers.Serializer):
    otp = serializers.CharField()


class ResetAccountPinSerializer(serializers.ModelSerializer):
    otp = serializers.CharField(max_length=50, min_length=4)
    pin2 = serializers.CharField(max_length=4, write_only=True, required=True)

    class Meta:
        model = TreasuryAccount
        fields = ("otp", "pin", "pin2")


class TreasuryAccountDetailsSerializer(serializers.ModelSerializer):
    balance = serializers.DecimalField(max_digits=12, decimal_places=2)
    tier = serializers.IntegerField(source="tier_level")

    class Meta:
        model = TreasuryAccount
        fields = ["acct_name", "account_number", "bank_name", "balance", "tier"]


class TreasuryTransferSerializer(serializers.Serializer):
    pin = serializers.CharField(max_length=4, write_only=True, required=False)
    use_biometrics = serializers.BooleanField(required=False, default=False)
    beneficiary_name = serializers.CharField(max_length=150)
    beneficiary_account_number = serializers.CharField(max_length=30)
    beneficiary_bank_code = serializers.CharField(max_length=20, required=False, allow_blank=True)
    sender_account_number = serializers.CharField(max_length=30)
    narration = serializers.CharField(required=False, allow_blank=True, default="")
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)


class ValidateTreasuryAccountSerializer(serializers.Serializer):
    account_number = serializers.CharField(max_length=30)


class ValidateExternalAccountSerializer(serializers.Serializer):
    account_number = serializers.CharField(max_length=30)
    bank_code = serializers.CharField(max_length=20)

    def validate_bank_code(self, value):
        if not value.isdigit() or not (3 <= len(value) <= 6):
            raise serializers.ValidationError("Bank code must be 3-6 digits.")
        return value


class CardFundingSerializer(serializers.ModelSerializer):
    class Meta:
        model = TreasuryCardFunding
        fields = ["id", "amount", "email"]


class GetTransferStatusSerializer(serializers.Serializer):
    anchor_transfer_id = serializers.CharField()


class TreasuryAccountStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = TreasuryAccount
        fields = ["account_number", "status", "created_at"]


# Admin (roles) serializers
class ListTreasuryAccountsSerializer(serializers.ModelSerializer):
    email = serializers.CharField(source="user.email", read_only=True)
    profile_img = serializers.CharField(source="user.profile_img_url", read_only=True)
    userTypes = serializers.SerializerMethodField()

    class Meta:
        model = TreasuryAccount
        fields = [
            "profile_img",
            "email",
            "acct_name",
            "account_number",
            "bank_name",
            "balance",
            "cashback_balance",
            "tier_level",
            "tier2_upgrade_status",
            "status",
            "created_at",
            "userTypes",
        ]

    def get_userTypes(self, obj):
        return list(obj.user.account_types.values_list("user_type", flat=True))


class ChangeTreasuryAccountStatusSerializer(serializers.ModelSerializer):
    pin = serializers.CharField(max_length=5, required=False, allow_blank=True)

    class Meta:
        model = TreasuryAccount
        fields = ["account_number", "status", "pin", "created_at"]
