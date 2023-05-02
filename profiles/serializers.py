from rest_framework import serializers

# In_project imports.
from . models import BusinessProfile, UserProfile, MemberProfile


class BusinessProfileSerializers(serializers.ModelSerializer):
    """ Serailizers for our Business profile personal data """

    class Meta:
        model = BusinessProfile
        fields = ['id',   'full_name', 'phone_number', 'address', 'city', 'state', 'country', 'category', 'number_of_branches'
                  'id_verification', 'business_docs', 'createdAt', 'updatedAt']

    def validate(self, attrs):
        # return super().validate(attrs)
    
        return BusinessProfile.objects.create(**attrs)
    

class UserProfileSerializers(serializers.ModelSerializer):
    """ Serailizers for our Business profile personal data """

    class Meta:
        model = UserProfile
        fields = ['id', 'email', 'full_name', 'phone_number', 'address', 'city', 'state', 'country', 'createdAt', 'updatedAt']

    def validate(self, attrs):
        # return super().validate(attrs)
    
        return UserProfile.objects.create(**attrs)    


class MemberProfileSerializers(serializers.ModelSerializer):
    """ Serailizers for our Business profile personal data """

    class Meta:
        model = MemberProfile
        fields = ['id', 'email', 'full_name', 'phone_number', 'address', 'city', 'state', 'country', 'createdAt', 'updatedAt']

    def validate(self, attrs):
        # return super().validate(attrs)
    
        return MemberProfile.objects.create(**attrs)  
