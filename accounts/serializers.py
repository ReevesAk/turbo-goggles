from django.contrib import auth

# Third party imports.
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.validators import ValidationError   

# In project imports.
from .models import User


class RegisterSerializer(serializers.ModelSerializer):
    """ Serailizers for our User first time registration """

    class Meta:
        model = User
        fields = ['id', 'first_name', 'last_name', 'account_type','country', 'state', 'city',  'phone_number', 'email', 'password', 'password']
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

    def create(self, validated_data):
        password = validated_data.pop("password")

        user = User
        user = super().create(validated_data)

        user.set_password(password)
        
        user.save()

        return User.objects.create_user(**validated_data)     
    

# LoginSerializer is a  serializer class for login credentials. 
class LoginSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(max_length=255, min_length=3)
    password = serializers.CharField(
        max_length=68, min_length=6, write_only=True)


    def get_tokens(self, obj):
        user = User.objects.get(email=obj['email'])

        return {
            'refresh': user.tokens()['refresh'],
            'access': user.tokens()['access']
        }

    class Meta:
        model = User
        fields = ['email', 'password']

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
        }

        return super().validate(attrs)
    

class VerifyOTPSerailizer(serializers.Serializer):
    otp = serializers.CharField()  


class ForgotPasswordSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(max_length=255, min_length=3)

    class Meta:
        model = User
        fields = ['email']

    def validate(self, attrs):
        email = attrs.get('email', '')
            
        if email is None:
            return serializers.ValidationError(
                'email: email field can not be empty'
            )
        return attrs
    
     
class ResetPasswordSerializer(serializers.ModelSerializer):
    old_password = serializers.CharField(max_length=68, min_length=6, write_only=True)
    password = serializers.CharField(max_length=68, min_length=6, write_only=True)
    password2 = serializers.CharField(max_length=68, min_length=6, write_only=True)


    class Meta:
        model = User
        fields = ['old_password', 'password', 'password2']


    def validate(self, attrs):

        password = attrs.get('password', '')
        password2 = attrs.get('password2', '')
        
        if password != password2:
            return serializers.ValidationError(
                'password: Passwords do not match'
            )
        return attrs
     