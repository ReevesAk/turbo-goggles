from django.core.validators import URLValidator
from django.core.exceptions import ValidationError as DjangoValidationError

# Third party imports.
from rest_framework import serializers

# In projects imports.
from accounts.models import User
from .models import CreateAd, AdBudget


class RegisterBrandAdvertSeriailizers(serializers.ModelSerializer):
    """Serializers for registering brand adverts"""

    password2 = serializers.CharField(max_length=68, min_length=6, write_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "device_id",
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
            "password2",
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
            phone_number_exists = User.objects.filter(
                phone_number=phone_number
            ).exists()
            if phone_number_exists:
                raise serializers.ValidationError("phone_number has already been used")
        else:
            raise serializers.ValidationError(
                "phone_number: phone_number field can not be empty"
            )

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
            name=validated_data["name"],
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
            website=validated_data["website"],
            facebook=validated_data["facebook"],
            twitter=validated_data["twitter"],
            instagram=validated_data["instagram"],
            telegram=validated_data["telegram"],
        )

        user.set_password(validated_data["password"])
        user.save()

        return user


class BrandAdProfileSerializers(serializers.ModelSerializer):
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
            "created_at",
            "updated_at",
        ]


class UpdateBrandAdProfileSerializers(serializers.ModelSerializer):
    """Serializers for updating brand adverts profile."""

    class Meta:
        model = User
        fields = [
            "id",
            "address",
            "brand_type",
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
            "created_at",
            "updated_at",
        ]


class BrandSurveySerializers(serializers.ModelSerializer):
    """Serializers for creating brand adverts survey."""

    state = serializers.CharField(max_length=150, write_only=True)
    city = serializers.CharField(max_length=150, write_only=True)

    class Meta:
        model = CreateAd
        fields = [
            "id",
            "brand_type",
            "product_type",
            "online_presence",
            "online_preferences",
            "metric_to_increase",
            "demography",
            "website",
            "state",
            "city",
            "type",
            "category",
            "address",
            "description",
            "duration",
        ]

        def validate(self, attrs):
            website = attrs.get("website")

            if website and not website.startswith(("http://", "https://")):
                raise serializers.ValidationError(
                    "Invalid website format. Please include 'http://' or 'https://'."
                )

            return attrs


class AdBudgetSerializer(serializers.ModelSerializer):
    """Serializers for Advert budget."""

    pin = serializers.CharField(max_length=4, min_length=6, write_only=True)

    class Meta:
        model = AdBudget
        fields = ["id", "ad_type", "ad", "star", "price_range", "pin"]
