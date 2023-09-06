# Third party imports.
from rest_framework import serializers
from rest_framework.validators import ValidationError   

# In projects imports.
from .models import (
    BrandAdvert, BrandAdService, BrandAdlogo, BookAnAd,
    BrandAdSurvey
)
from accounts.models import User
from accounts.utils import validate_url


class AdvertStartSeriailizers(serializers.ModelSerializer):
    """Serializers for initializing brand adverts"""

    class Meta:
        model = BrandAdvert
        fields = ['id','brand_name', 'email', 'phone_number', 'address', 'city', 'trade']


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
    
       

class AdvertContdSerializers(serializers.ModelSerializer):
    """Serializers for initializing brand adverts"""

    class Meta:
        model = BrandAdvert
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
    
    
class BrandAvertSurveySerializers(serializers.ModelSerializer):
    """ Serailizers for our Brand adverts survey. """    
    
    class Meta:
        model = BrandAdSurvey
        fields = ['preference', 'age_bracket', 'hobbies', 'phone_use', 
                  'music_type', 'social_event'
        ]


class AdvertServicecSerializers(serializers.ModelSerializer):
    """Serializers for initializing brand adverts"""

    class Meta:
        model = BrandAdService
        fields = ['id', 'service_name', 'price_of_service', 'duration_of_service', 
            'service_desc'
        ]


    def validate(self, attrs):

        service_name_exists = BrandAdService.objects.filter(service_name=attrs["service_name"]).exists()

        if service_name_exists:
            raise ValidationError("Service already exists")

        service_name = attrs.get('service_name', '')
        
        if service_name is None:
            raise serializers.ValidationError(
                'service_name: service_name field can not be empty'
            )
        return super().validate(attrs) 


class BrandAvertLogoUploadsSerializers(serializers.ModelSerializer):
    """ Serailizers for our Brand adverts logo uploads. """

    class Meta:
        model = BrandAdlogo
        fields = ['user', 'logo_url', 'logo', 'timestamp']

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation.pop("logo")

        return representation    


class BookAvertSerializers(serializers.ModelSerializer):
    """ Serializer for booking an advert. """

    class Meta:
        model = BookAnAd
        fields = ['user', 'booking']
