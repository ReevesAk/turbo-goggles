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

    class Meta:
        model = User
        fields = ['id', 'first_name', 'last_name', 'country', 'account_type',
        'state', 'city',  'phone_number', 'business_name', 'website',
        'business_category', 'email', 'password']
        extra_kwargs = {
            'password': {'write_only': True}
        }

    def validate(self, attrs):

        email_exists = User.objects.filter(email=attrs["email"]).exists()

        if email_exists:
            raise ValidationError("Email has already been used")
        
        email = attrs.get('email', '')
        

        if email is None:
            raise serializers.ValidationError(
                'email: email field can not be empty'
            )
        return super().validate(attrs)



class PartnerProfileSerializer(serializers.ModelSerializer):
    """ Serailizers for our Partners' profile. """

    class Meta:
        model = User
        fields = ['id', 'first_name', 'last_name', 'email', 'country', 'account_type',
            'state', 'city',  'phone_number', 'business_name', 'website',
            'business_category', 'created_at','updated_at',
        ]


class PartnerServiceSerializers(serializers.ModelSerializer):
    """ Serailizers for our Partners' services. """

    class Meta:
        model = PartnerServices
        fields = ["id", "service_offered", "service_category"]


    def create(self, validated_data):
        partner = PartnerServices.objects.create_user(**validated_data)
        return partner
        


class ServiceAndChargeSerializers(serializers.ModelSerializer):
    """ Serailizers for our Partners' service types and prices. """
    
    class Meta:
        model = ServiceAndCharge
        fields = ['price', 'service']


    def create(self, validated_data):
        partner_service = ServiceAndCharge.objects.create_user(**validated_data)
        return partner_service
        


class PartnerServiceUploadsSerializers(serializers.ModelSerializer):
    """ Serailizers for our Partners' service uploads. """

    class Meta:
        model = PartnerServiceImageUploads
        fields = ['image_url', 'image', 'timestamp']

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation.pop("image")

        return representation    


