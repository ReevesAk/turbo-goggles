import requests
from django.conf import settings
from django.db.models import Sum

# Third party imports.
from rest_framework import serializers
from rest_framework.validators import ValidationError   

# In project imports.
from accounts.models import User
from .models import (
    PartnerServices, ServiceAndCharge, PartnerServiceImageUploads,
    Wallet, WalletTransaction,
)


class RegisterPartnerSerializer(serializers.ModelSerializer):
    """ Serailizers for our Partners' first time registration """

    password2 = serializers.CharField(
        style={"input_type": "password"}, max_length=68, min_length=6, write_only=True)

    account_type = serializers.CharField(default="Partner")

    class Meta:
        model = User
        fields = ['id', 'first_name', 'last_name', 'country', 'account_type',
        'state', 'city',  'phone_number', 'business_name', 'website',
        'business_category', 'email', 'password', 'password2']
        extra_kwargs = {
            'password': {'write_only': True}
        }

    def validate(self, attrs):

        email_exists = User.objects.filter(email=attrs["email"]).exists()

        if email_exists:
            raise ValidationError("Email has already been used")
        
        email = attrs.get('email', '')
        password = attrs.get('password', '')
        password2 = attrs.pop('password2', '')
        
        if password != password2:
            raise serializers.ValidationError(
                'password: Passwords do not match'
            )

        if email is None:
            raise serializers.ValidationError(
                'email: email field can not be empty'
            )
        return super().validate(attrs)
    
    def create(self, validated_data):
        password = validated_data.pop("password")

        user = User
        user = super().create(validated_data)

        user.set_password(password)
        
        user.save()

        return User.objects.create_user(**validated_data)     


class PartnerServiceSerializers(serializers.ModelSerializer):
    """ Serailizers for our Partners' services. """

    class Meta:
        model = PartnerServices
        fields = ['id', 'service_offered', "service_category"]


    def create(self, validated_data):
        partner = PartnerServices.objects.create_user(**validated_data)
        return partner
        


class ServiceAndChargeSerializers(serializers.ModelSerializer):
    """ Serailizers for our Partners' service types and prices. """
    
    class Meta:
        model = ServiceAndCharge
        fields = ['id', 'price', 'service']


    def create(self, validated_data):
        partner_service = ServiceAndCharge.objects.create_user(**validated_data)
        return partner_service
        


class PartnerServiceUploadsSerializers(serializers.ModelSerializer):
    """ Serailizers for our Partners' service uploads. """

    class Meta:
        model = PartnerServiceImageUploads
        fields = ['user', 'image_url', 'image', 'timestamp']

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation.pop("image")

        return representation    


class WalletSerializer(serializers.ModelSerializer):
    """
    Serializers to validate the user's wallet 
    """
    balance = serializers.SerializerMethodField()

    def get_balance(self, obj):
        bal = WalletTransaction.objects.filter(
            wallet=obj, status="success").aggregate(Sum('amount'))['amount__sum']
        return bal

    class Meta:
        model = Wallet
        fields = ['id', 'currency', 'balance']


def is_amount(value):
    if value <= 0:
        raise serializers.ValidationError({"detail": "Invalid Amount"})
    return value


class DepositSerializer(serializers.Serializer):

    amount = serializers.IntegerField(validators=[is_amount])
    email = serializers.EmailField()

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            return value
        raise serializers.ValidationError({"detail": "Email not found"})

    def save(self):
        user = self.context['request'].user
        wallet = Wallet.objects.get(user=user)
        data = self.validated_data
        url = 'https://api.paystack.co/transaction/initialize'
        headers = {
            {"authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}"}
        }  
        r = requests.post(url, headers=headers, data=data)
        response = r.json()
        WalletTransaction.objects.create(
            wallet=wallet,
            transaction_type="deposit",
            amount= data["amount"],
            paystack_payment_reference=response['data']['reference'],
            status="pending",
        )

        return response


class TransferSerializer(serializers.Serializer):
    amount = serializers.IntegerField(validators=[is_amount])
    email = serializers.EmailField()

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            return value
        raise serializers.ValidationError({"detail": "Email not found"})
    

    def save(self):
        user = self.context['request'].user
        wallet = Wallet.objects.get(user=user)
        data = self.validated_data
        url = 'https://api.paystack.co/transaction/initialize'
        headers = {
            {"authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}"}
        }  
        r = requests.post(url, headers=headers, data=data)
        response = r.json()
        WalletTransaction.objects.create(
            wallet=wallet,
            transaction_type="transfer",
            amount= data["amount"],
            paystack_payment_reference=response['data']['reference'],
            status="pending",
        )
