from django.contrib.auth import authenticate

# Third party imports.
from rest_framework import serializers

# In project imports.
from .models import User


class RegisterSerializer(serializers.ModelSerializer):
    """Serailizers for our User first time registration"""

    class Meta:
        model = User
        fields = [
            "id",
            "first_name",
            "last_name",
            "account_type",
            "country",
            "state",
            "city",
            "phone_number",
            "email",
            "password",
        ]
        extra_kwargs = {"password": {"write_only": True}}

    def validate(self, attrs):
        email = attrs.get("email", "")

        if email:
            email_exists = User.objects.filter(email=email).exists()
            if email_exists:
                raise serializers.ValidationError("Email has already been used")
        else:
            raise serializers.ValidationError("email: email field can not be empty")

        return super().validate(attrs)


# LoginSerializer is a  serializer class for login credentials.
class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(
        label="Password",
        style={"input_type": "password"},
        trim_whitespace=False,
    )

    # class Meta:
    #     model = User
    #     fields = ["email", "password"]

    def validate(self, attrs):
        email = attrs.get("email")
        password = attrs.get("password")

        if email and password:
            user = authenticate(
                request=self.context.get("request"), email=email, password=password
            )

            if not user:
                msg = "Unable to log in with provided credentials."
                raise serializers.ValidationError(msg, code="authorization")
        else:
            msg = "Must include 'email' and 'password' fields."
            raise serializers.ValidationError(msg, code="authorization")

        attrs["user"] = user
        return attrs


class VerifyOTPSerailizer(serializers.Serializer):
    otp = serializers.CharField()


class ForgotPasswordSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(max_length=255, min_length=3)

    class Meta:
        model = User
        fields = ["email"]

    def validate(self, attrs):
        email = attrs.get("email", "")

        if email is None:
            return serializers.ValidationError("email: email field can not be empty")
        return attrs


class ResetPasswordSerializer(serializers.ModelSerializer):
    password = serializers.CharField(max_length=68, min_length=6, write_only=True)
    password2 = serializers.CharField(max_length=68, min_length=6, write_only=True)

    class Meta:
        model = User
        fields = ["old_password", "password", "password2"]

    def validate(self, attrs):
        password = attrs.get("password", "")
        password2 = attrs.get("password2", "")

        if password != password2:
            return serializers.ValidationError("password: Passwords do not match")
        return attrs
