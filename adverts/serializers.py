from django.core.validators import URLValidator

# Third party imports.
from rest_framework import serializers
from rest_framework.validators import ValidationError   

# In projects imports.
from .models import BrandAdvertRegistration
from accounts.models import User
from accounts.utils import validate_url

class AdvertStartSeriailizers(serializers.ModelSerializer):
    """Serializers for initializing brand adverts"""

    class Meta:
        model = BrandAdvertRegistration
        fields = ['brand_name', 'email', 'phone_number', 'address', 'city', 'trade']


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
        user = BrandAdvertRegistration
        user = super().create(validated_data)

        user.save()

        return BrandAdvertRegistration.objects.create_user(**validated_data)     


class AdvertContdSerializers(serializers.ModelSerializer):
    """Serializers for initializing brand adverts"""

    class Meta:
        model = BrandAdvertRegistration
        fields = ['facebook', 'twitter', 'instagram', 'youtube', 'website']


    def validate(self, attrs):
        
        valid_urls = []

        facebook = attrs.get('facebook', '')
        twitter = attrs.get('twitter', '')
        instagram = attrs.get('instagram', '')
        youtube = attrs.get('youtube', '')
        website = attrs.get('website', '')

        urls = [facebook, twitter, instagram, youtube, website]
        
        for url in urls:
            is_valid = validate_url(url)
            if is_valid == True:
                valid_urls.append(url)

        return super().validate(attrs)
    
    def create(self, validated_data):
        user = BrandAdvertRegistration
        user = super().create(validated_data)

        user.save()

        return BrandAdvertRegistration.objects.create_user(**validated_data)     

