# Third party imports.
from rest_framework import serializers

# In project imports.
from .models import (
    Applications,
)


from .models import JobModel


class JobSerializer(serializers.ModelSerializer):
    class Meta:
        model = JobModel
        fields = [
            "id",
            "title",
            "description",
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
