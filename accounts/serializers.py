from django.contrib import auth

# Third party imports.
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from drf_spectacular.utils import extend_schema

# In project imports.
from .models import User

class RegisterSerializer(serializers.ModelSerializer):
    """ Serailizers for our User first time registration """

    password = serializers.CharField(
        max_length=68, min_length=6, write_only=True)
    
    password2 = serializers.CharField(
        max_length=68, min_length=6, write_only=True)

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'phone_number', 'email','password', 'password2']


    def validate(self, attrs):
        email = attrs.get('email', '')
        password = attrs.get('password', '')
        password2 = attrs.get('password2', '')
        
        if password != password2:
            return serializers.ValidationError(
                'password: Passwords do not match'
            )

        if email is None:
            return serializers.ValidationError(
                'email: email field can not be empty'
            )
        return attrs

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)     
    
    
# LoginSerializer is a  serializer class for login credentials. 
class LoginSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(max_length=255, min_length=3)
    password = serializers.CharField(
        max_length=68, min_length=6, write_only=True)

    tokens = serializers.SerializerMethodField()

    def get_tokens(self, obj):
        user = User.objects.get(email=obj['email'])

        return {
            'refresh': user.tokens()['refresh'],
            'access': user.tokens()['access']
        }

    class Meta:
        model = User
        fields = ['email', 'password', 'tokens']

    def validate(self, attrs):
        phone_number = attrs.get('phone_number', '')
        password = attrs.get('password', '')
        # filtered_user_by_email = User.objects.filter(email=email)
        user = auth.authenticate(phone_number=phone_number, password=password)

        if not user:
            raise AuthenticationFailed('Invalid credentials, try again')
        if not user.is_active:
            raise AuthenticationFailed('Account disabled, contact admin')
        if not user.is_verified:
            raise AuthenticationFailed('Email is not verified')

        return {
            'email': user.email,
            'phone_number': user.phone_number,
            'tokens': user.tokens
        }

        return super().validate(attrs)
    