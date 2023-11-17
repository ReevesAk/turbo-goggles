from django.core.validators import URLValidator
from django.core.exceptions import ValidationError as DjangoValidationError

# Third party imports.
from rest_framework import serializers
from rest_framework.validators import ValidationError

# In projects imports.
from accounts.models import User


class RegisterBrandAdvertSeriailizers(serializers.ModelSerializer):
    """Serializers for registering brand adverts"""

    password2 = serializers.CharField(max_length=68, min_length=6, write_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "account_type",
            "whoareyou",
            "name",
            "address",
            "email",
            "brand_type",
            "phone_number",
            "country",
            "brand_name",
            "description",
            "services",
            "state",
            "city",
            "website",
            "facebook",
            "twitter",
            "instagram",
            "telegram",
            "password",
            "password2"
        ]
        extra_kwargs = {"password": {"write_only": True}}

    def validate(self, attrs):
        email = attrs.get("email", "")
        phone_number = attrs.get("phone_number", "")

        if email:
            email_exists = User.objects.filter(email=email).exists()
            if email_exists:
                raise serializers.ValidationError("Email has already been used")
        else:
            raise serializers.ValidationError("email: email field can not be empty")
        
        if phone_number:
            phone_number_exists = User.objects.filter(phone_number=phone_number).exists()
            if phone_number_exists:
                raise serializers.ValidationError("phone_number has already been used")
        else:
            raise serializers.ValidationError("phone_number: phone_number field can not be empty")
        
        urls = ["facebook", "twitter", "instagram", "telegram", "website"]
        url_validator = URLValidator()

        for field_name in urls:
            url = attrs.get(field_name, "")

            if url:
                try:
                    url_validator(url)
                except DjangoValidationError:
                    raise serializers.ValidationError(
                        f"{field_name}: Invalid URL format"
                    )

        return super().validate(attrs)
    
    def create(self, validated_data):
        user = User.objects.create(
            email=validated_data["email"],
            whoareyou=validated_data["whoareyou"],
            address=validated_data["address"],
            brand_type=validated_data["brand_type"],
            brand_name=validated_data["brand_name"],
            description=validated_data["description"],
            services=validated_data["services"],
            account_type=validated_data["account_type"],
            country=validated_data["country"],
            state=validated_data["state"],
            city=validated_data["city"],
            phone_number=validated_data["phone_number"],
            business_name=validated_data["business_name"],
            website=validated_data["website"],
            facebook=validated_data["facebook"],
            twitter=validated_data["twitter"],
            instagram=validated_data["instagram"],
            telegram=validated_data["telegram"],
        )

        user.set_password(validated_data["password"])
        user.save()

        return user


class BrandAdProfileSerializers(serializers.Serializer):
    """Serailizers for our BrandAds profile."""

    class Meta:
        model = User
        fields = [
            "id",
            "account_type",
            "whoareyou",
            "name",
            "address",
            "email",
            "brand_type",
            "phone_number",
            "country",
            "brand_name",
            "description",
            "services",
            "state",
            "city",
            "website",
            "facebook",
            "twitter",
            "instagram",
            "telegram",
        ]
