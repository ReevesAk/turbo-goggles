# Third party imports.
from rest_framework import serializers

# In project imports.
from accounts.models import User
from banking.models import AccountCreation

from .models import (
    Ticket
)


class CreateTicketSerializers(serializers.ModelSerializer):
    email = serializers.CharField(max_length=68, min_length=6, write_only=True)

    class Meta:
        model = Ticket
        fields = [
            "id",
            "title",
            "email",
            "description",
        ]
