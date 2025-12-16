# Third party imports.
from rest_framework import serializers

# In project imports.
from .models import (
    Applications,
)


from .models import JobModel


class JobSerializer(serializers.ModelSerializer):
    pin = serializers.CharField(
        max_length=5, min_length=5, required=False, allow_blank=True
    )
    key_responsibilities = serializers.ListField(
        child=serializers.CharField(),
        required=False
    )
    requirements = serializers.ListField(
        child=serializers.CharField(),
        required=False
    )

    class Meta:
        model = JobModel
        fields = [
            "id",
            "pin",
            "title",
            "company",
            "job_summary",
            "key_responsibilities",
            "requirements",
            "location",
            "salary",
            "is_active",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class ApplicationsSerializers(serializers.ModelSerializer):

    class Meta:
        model = Applications
        fields = [
            "first_name",
            "last_name",
            "gender",
            "phone_number",
            "state",
            "lga",
            "address",
            "email",
            "cv",
        ]


class GetApplicationsSerializers(serializers.ModelSerializer):
    class Meta:
        model = Applications
        fields = [
            "id",
            "first_name",
            "last_name",
            "gender",
            "phone_number",
            "state",
            "lga",
            "address",
            "email",
            "cv",
        ]
