# Third party imports.
from rest_framework import serializers

from .models import WaitlistModel

class WaitlistSerialiser(serializers.ModelSerializer):
    class Meta:
        model = WaitlistModel
        fields = [
            "f_name",
            "l_name",
            "email",
            "phone",
            "referral_code"
        ]

    def create(self, validated_data):
        first_name = validated_data.get("f_name")

        validated_data["referral_code"] = WaitlistModel.generate_referral_code(
            first_name=first_name
        )

        return super().create(validated_data)
