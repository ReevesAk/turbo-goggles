import logging

# Third party imports.
from rest_framework import serializers

# In project imports.
from accounts.models import User
from .models import (
    Ticket, AgentRating
)
from accounts.models import USER_CATEGORY_CHOICES, AccountType
from .models import TicketAssignmentHistory

logger = logging.getLogger("support")


class RegisterAgentManagerSerializer(serializers.ModelSerializer):
    """Serializer for agent manager first-time registration"""
    password2 = serializers.CharField(max_length=68, min_length=6, write_only=True)
    device_id = serializers.CharField(max_length=68, min_length=6, write_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "device_id",
            "phone_number",
            "email",
            "password",
            "password2",
        ]
        extra_kwargs = {"password": {"write_only": True}}

    def validate(self, attrs):
        email = attrs.get("email", "")
        password = attrs.get("password", "")
        password2 = attrs.get("password2", "")
        # Validate that email is provided and not already in use
        if not email:
            raise serializers.ValidationError(
                {"email": "Email field cannot be empty."}
            )
        if User.objects.filter(email=email).exists():
            raise serializers.ValidationError(
                {"email": "Email has already been used."}
            )
        # Validate that passwords match
        if password != password2:
            raise serializers.ValidationError(
                {"password": "Passwords do not match."}
            )
        return attrs

    def create(self, validated_data):
        # Remove password2 from validated_data as it's not a field in the User model
        validated_data.pop("password2")
        # Create the user with the provided email and phone number
        user = User.objects.create(
            email=validated_data["email"],
            phone_number=validated_data["phone_number"],
        )
        # Set and save the password securely
        user.set_password(validated_data["password"])
        user.save()
        return user


class SupportVerifyOTPSerializer(serializers.Serializer):
    otp = serializers.CharField()

    def validate(self, attrs):
        otp = attrs.get("otp")
        logger.info("OTP verification attempt for OTP: %s", otp)
        return attrs


class CreateTicketSerializers(serializers.ModelSerializer):
    email = serializers.CharField(max_length=68, min_length=6, write_only=True)
    attachments = serializers.FileField(
        required=False,
        allow_null=True
    )
    pin = serializers.CharField(max_length=10, min_length=5, write_only=True)

    class Meta:
        model = Ticket
        fields = [
            "id",
            "pin",
            "number",
            "customer_name",
            "title",
            "priority",
            "category",
            "channel",
            "email",
            "attachments",
            "description",
        ]
        read_only_fields = ["status", "created_at"]


class TicketSerializers(serializers.ModelSerializer):

    class Meta:
        model = Ticket
        fields = [
            "id",
            "number",
            "category",
            "channel",
            "description",
            "priority",
            "status",
            "assigned_at",
        ]


class UserWithTicketsSerializer(serializers.ModelSerializer):
    user_tickets = TicketSerializers(many=True, read_only=True)

    class Meta:
        model = User
        fields = ['id', 'first_name', 'last_name', 'email', 'user_tickets']


class AssignTicketSerializers(serializers.ModelSerializer):
    agent_name = serializers.CharField(max_length=68, min_length=6, write_only=True)
    agent_email = serializers.CharField(max_length=68, min_length=6, write_only=True)
    agent_role = serializers.ChoiceField(
        choices=["Agent", "Moderator"],
        write_only=True
    )
    pin = serializers.CharField(max_length=10, min_length=5, write_only=True)
    reason = serializers.CharField(max_length=200, write_only=True, required=False)

    class Meta:
        model = Ticket
        fields = [
            "pin",
            "category",
            "status",
            "agent_name",
            "agent_role",
            "agent_email",
            "reason",
            "priority"
        ]


class UpdateTicketStatusSerializer(serializers.ModelSerializer):
    pin = serializers.CharField(max_length=10, min_length=4, write_only=True)

    class Meta:
        model = Ticket
        fields = [
            "status",
            "pin",
        ]


class TicketAssignmentHistorySerializer(serializers.ModelSerializer):
    assigned_by = serializers.SerializerMethodField()
    previous_agent = serializers.SerializerMethodField()
    new_agent = serializers.SerializerMethodField()

    class Meta:
        model = TicketAssignmentHistory
        fields = (
            "assigned_by",
            "previous_agent",
            "new_agent",
            "priority",
            "reason",
            "created_at",
        )

    def get_assigned_by(self, obj):
        return obj.assigned_by.full_name if obj.assigned_by else None

    def get_previous_agent(self, obj):
        return obj.previous_agent.full_name if obj.previous_agent else None

    def get_new_agent(self, obj):
        return obj.new_agent.full_name if obj.new_agent else None


class AgentRatingSerializers(serializers.ModelSerializer):
    rating_comment = serializers.CharField(max_length=68, min_length=6, write_only=True, required=False)

    class Meta:
        model = AgentRating
        fields = [
            "id",
            "rating",
            "rating_comment"
        ]


class PusherSerializers(serializers.ModelSerializer):
    message = serializers.CharField(max_length=68, min_length=6, write_only=True)

    class Meta:
        model = AgentRating
        fields = [
            "id",
            "message",
        ]


class AddAgentSerializer(serializers.ModelSerializer):
    """Serializer for other agents initial registration step."""

    role = serializers.ListField(
        child=serializers.ChoiceField(choices=USER_CATEGORY_CHOICES), write_only=True
    )
    pin = serializers.CharField(max_length=5, min_length=5, write_only=True)

    class Meta:
        model = User
        fields = ["id", "role", "full_name", "email", "pin"]
        extra_kwargs = {"email": {"required": True}}

    def validate(self, attrs):
        return super().validate(attrs)

    def create(self, validated_data):
        user_types = validated_data.pop("role", [])
        validated_data.pop("pin", None)
        user = super().create(validated_data)

        # Assign multiple AccountType entries based on roles
        AccountType.objects.bulk_create(
            [AccountType(user=user, user_type=user_type) for user_type in user_types]
        )

        return user


class AddAgentContdSerializer(serializers.ModelSerializer):
    """Serializer for other support agents first-time registration."""

    password2 = serializers.CharField(max_length=68, min_length=6, write_only=True)

    class Meta:
        model = User
        fields = ["phone_number", "password", "password2"]
        extra_kwargs = {"password": {"write_only": True}}

    def validate(self, attrs):
        password = attrs.get("password")
        password2 = attrs.get("password2")

        if password != password2:
            raise serializers.ValidationError(
                {"password": "Passwords do not match."}
            )

        return attrs

    def create(self, validated_data):
        validated_data.pop("password2")  # Remove password2 from validated data
        user = User(**validated_data)
        user.set_password(validated_data["password"])  # Hash the password
        user.save()
        return user

    def update(self, instance, validated_data):
        validated_data.pop("password2", None)  # Remove password2 if present
        if "password" in validated_data:
            instance.set_password(validated_data["password"])
        return super().update(instance, validated_data)


class SupportAgentLoginSerializers(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["email", "password"]


class CreateAgentPinSerializer(serializers.ModelSerializer):
    """Serailizers for agents first time pin creation."""

    pin = serializers.CharField(min_length=5, write_only=True)

    class Meta:
        model = User
        fields = ["pin"]
        extra_kwargs = {"pin": {"write_only": True}}

    def validate_pin(self, value):
        if not value.isdigit() or len(value) != 5:
            raise serializers.ValidationError("Pin must be a 5-digit number.")
        return value


class ListAgentAndModeratorSerializer(serializers.ModelSerializer):
    user_type = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "full_name", "phone_number", "email", "user_type", "last_login"]

    def get_user_type(self, obj):
        # Fetch user_type values from AccountType model related to the user
        return list(obj.account_types.values_list("user_type", flat=True))

    # def get_status(self, obj):
    #     return "Disabled" if obj.is_admin_disabled else "Active"
