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
            "full_name",
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
            full_name=validated_data.get("full_name"),
        )
        # Set and save the password securely
        user.set_password(validated_data["password"])
        user.save()
        return user


class UserProfileSerializer(serializers.ModelSerializer):
    """Serailizers for our Partners' profile."""

    class Meta:
        model = User
        fields = [
            "id",
            "first_name",
            "last_name",
            "profile_img_url",
            "email",
            "active_role",
            "phone_number",
            "created_at",
            "welcome_bonus",
        ]


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
            "customer_email",
            "customer_phone_number",
            "title",
            "priority",
            "resolution_hours",
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
            "resolution_hours",
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
    agent_name = serializers.CharField(max_length=68, write_only=True)
    agent_email = serializers.CharField(max_length=68, write_only=True)
    agent_role = serializers.ChoiceField(
        choices=["Agent", "Moderator", "Manager"],
        write_only=True
    )
    pin = serializers.CharField(max_length=10, min_length=5, write_only=True)
    reason = serializers.CharField(max_length=200, write_only=True, required=False)
    status = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = Ticket
        fields = [
            "pin",
            "category",
            "status",
            "agent_name",
            "agent_role",
            "resolution_hours",
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


class TicketRRTrailSerializer(serializers.Serializer):
    action = serializers.CharField()
    from_user = serializers.CharField(allow_null=True)
    to_user = serializers.CharField(allow_null=True)
    role = serializers.CharField(allow_null=True)
    priority = serializers.CharField(allow_null=True)
    reason = serializers.CharField(allow_null=True)
    timestamp = serializers.DateTimeField()


class TicketEscalateSerializer(serializers.Serializer):
    to_user_id = serializers.CharField(max_length=255)
    to_role = serializers.CharField(max_length=150)
    reason = serializers.CharField(max_length=255)
    pin = serializers.CharField(max_length=10, min_length=5, write_only=True)

    def validate_to_user_id(self, value):
        if not User.objects.filter(id=value).exists():
            raise serializers.ValidationError("Target user does not exist.")
        return value


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
    rating_comment = serializers.CharField(
        max_length=68, min_length=6, write_only=True,
        required=False
    )

    class Meta:
        model = AgentRating
        fields = [
            "id",
            "rating",
            "rating_comment"
        ]


class AgentDeletionSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(required=True)
    pin = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = User
        fields = ["email", "pin"]


class DisableAgentSerializer(serializers.ModelSerializer):
    pin = serializers.CharField(max_length=5, min_length=6, write_only=True)

    class Meta:
        model = User
        fields = ["email", "pin"]


class EnableAgentSerializer(serializers.ModelSerializer):
    pin = serializers.CharField(max_length=5, min_length=6, write_only=True)

    class Meta:
        model = User
        fields = ["email", "pin"]


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

    def create(self, validated_data):
        user_types = validated_data.pop("role", [])
        validated_data.pop("pin", None)

        user = User(
            email=validated_data.get("email"),
            full_name=validated_data.get("full_name"),
        )

        # 🔐 CRITICAL: Disable password until signup completion
        user.set_unusable_password()
        user.is_verified = False
        user.save()

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
        validated_data.pop("password2", None)

        password = validated_data.pop("password", None)  # Remove password2 if present
        if password:
            instance.set_password(password)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()
        return instance


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


class ListAgentModeratorAndManagerSerializer(serializers.ModelSerializer):
    user_type = serializers.SerializerMethodField()
    full_name = serializers.SerializerMethodField()
    average_rating = serializers.FloatField(read_only=True)
    rating_count = serializers.IntegerField(read_only=True)
    total_tickets_assigned = serializers.IntegerField(read_only=True)
    total_tickets_resolved = serializers.IntegerField(read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "full_name",
            "phone_number",
            "email",
            "user_type",
            "last_login",
            "average_rating",
            "rating_count",
            "is_agent_disabled",
            "total_tickets_assigned",
            "total_tickets_resolved"
        ]

    def get_user_type(self, obj):
        # Fetch user_type values from AccountType model related to the user
        return list(obj.account_types.values_list("user_type", flat=True))

    def get_full_name(self, obj):
        if obj.first_name or obj.last_name:
            return f"{obj.first_name or ''} {obj.last_name or ''}".strip()
        return None


class CompleteTicketSerializer(serializers.ModelSerializer):

    class Meta:
        model = Ticket
        fields = [
            "id",
            "resolution_attachment",
        ]


class ForgotPinSerializer(serializers.ModelSerializer):
    email = serializers.CharField(max_length=50, write_only=True)

    class Meta:
        model = User
        fields = ["email"]

    def validate(self, attrs):
        email = attrs.get("email")
        return attrs


class VerifyOTPSerializer(serializers.Serializer):
    otp = serializers.CharField()

    def validate(self, attrs):
        otp = attrs.get("otp")
        logger.info("OTP verification attempt for OTP: %s", otp)
        return attrs


class ResetPinSerializer(serializers.ModelSerializer):
    pin = serializers.CharField(max_length=68, min_length=5, write_only=True)
    pin2 = serializers.CharField(max_length=68, min_length=5, write_only=True)
    agent_id = serializers.CharField(max_length=68, write_only=True)

    class Meta:
        model = User
        fields = ["agent_id", "pin", "pin2"]


class SupportStaffForgotPasswordSerializer(serializers.ModelSerializer):
    email = serializers.CharField(max_length=68, min_length=6, write_only=True)

    class Meta:
        model = User
        fields = ["email"]

    def validate(self, attrs):
        email = attrs.get("email")
        logger.info("Forgot password request for email for support staff: %s", email)
        return attrs


class SupportStaffPasswordResendOTPSerializer(serializers.Serializer):
    """Serailizers for resending OTP to support members."""

    email = serializers.CharField()

    class Meta:
        model = User
        fields = ["id", "email"]

    def validate(self, attrs):
        email = attrs.get("email")
        logger.info("OTP resend request for phone number: %s", email)
        return attrs


class SupportStaffResetPasswordSerializer(serializers.ModelSerializer):
    password = serializers.CharField(max_length=68, min_length=10, write_only=True)
    password2 = serializers.CharField(max_length=68, min_length=10, write_only=True)
    agent_id = serializers.CharField(max_length=68, write_only=True)

    class Meta:
        model = User
        fields = ("agent_id", "password", "password2")

    def validate(self, attrs):
        agent_id = attrs.get("agent_id")
        user = User.objects.get(id=agent_id)
        logger.info("Password reset request for email: %s", user.email)
        return attrs
