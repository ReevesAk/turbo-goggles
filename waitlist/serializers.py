from rapidfuzz import fuzz

# Third party imports.
from rest_framework import serializers

from .models import WaitlistModel


class VerifyWaitlistOTPSerializer(serializers.Serializer):
    email = serializers.EmailField(help_text="Email address used to join the waitlist.")
    otp = serializers.CharField(
        max_length=6, help_text="6-digit OTP sent to your phone number."
    )


class WaitlistSerialiser(serializers.ModelSerializer):

    def validate(self, data):
        import re

        f = (data.get("f_name") or "").strip().lower()
        ln = (data.get("l_name") or "").strip().lower()
        email = (data.get("email") or "").strip().lower()
        phone = (data.get("phone") or "").strip().lower()

        # Regex for real email validation
        email_regex = r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"
        if not re.match(email_regex, email):
            raise serializers.ValidationError("Please enter a valid email address.")

        # 1. Block emails starting with 'eric'
        if email.startswith("eric"):
            raise serializers.ValidationError(
                "Registrations from this email prefix are not allowed."
            )

        # 2. Block exact or swapped name duplicates
        exists = (
            WaitlistModel.objects.filter(f_name__iexact=f, l_name__iexact=ln).exists()
            or WaitlistModel.objects.filter(f_name__iexact=ln, l_name__iexact=f).exists()
        )
        if exists:
            raise serializers.ValidationError(
                "A user with this name combination already exists."
            )

        # 3. Fuzzy name matching (for typos or small changes)
        for user in WaitlistModel.objects.all():
            uf = (user.f_name or "").strip().lower()
            ul = (user.l_name or "").strip().lower()
            # Check both orders
            score1 = fuzz.ratio(f"{f} {ln}", f"{uf} {ul}")
            score2 = fuzz.ratio(f"{f} {ln}", f"{ul} {uf}")
            if max(score1, score2) > 90:
                raise serializers.ValidationError(
                    "A similar user already exists (fuzzy match)."
                )

        # 4. Block duplicate phone numbers (if not blank)
        if phone and WaitlistModel.objects.filter(phone=phone).exists():
            raise serializers.ValidationError(
                "A user with this phone number already exists."
            )

        return data

    class Meta:
        model = WaitlistModel
        fields = [
            "f_name",
            "l_name",
            "email",
            "phone",
            "referral_code",
            "is_student",
            "institution",
            "joined_at",
        ]
        read_only_fields = ["joined_at"]

    def create(self, validated_data):
        first_name = validated_data.get("f_name")
        validated_data["referral_code"] = WaitlistModel.generate_referral_code(
            first_name=first_name
        )
        return super().create(validated_data)
