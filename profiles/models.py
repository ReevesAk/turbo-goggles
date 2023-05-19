from django.db import models


from accounts.models import User

def upload_to(instance, filename):
    return 'profile/{filename}'.format(filename=filename)

BUSINESS_CATEGORY_CHOICES = (
    ("Hotel and Accomodation", "Hotel and Accomodation"),
    ("Fast food and restaurant", "Fast food and restaurant"),
    ("Land Transport", "Land Transport"),
    ("Cooking Gas Service", "Cooking Gas Service"),
    ("Air Transport", "Air Transport"),
    ("Dubai Visa", "Dubai Visa"),
    ("Cinema and Gym", "Cinema and Gym")
)

# Create your models here.
class BusinessProfile(models.Model):
    user                = models.ForeignKey(User, on_delete=models.CASCADE)
    business_name       = models.CharField(max_length=200, unique=True)
    email               = models.EmailField()
    full_name           = models.CharField(max_length=255, blank=False)
    country             = models.CharField(max_length=155, blank=False)
    state               = models.CharField(max_length=155, blank=False)
    city                = models.CharField(max_length=155, blank=False)
    address             = models.CharField(max_length=155, blank=False)
    phone_number        = models.CharField(max_length=100, blank=False)
    category            = models.CharField(choices=BUSINESS_CATEGORY_CHOICES, max_length=40)
    number_of_branches  = models.CharField(max_length=100, blank=False)
    id_verification     = models.FileField(upload_to=upload_to)
    business_docs       = models.FileField(upload_to=upload_to)
    createdAt           = models.DateTimeField(auto_now_add=True)
    updatedAt           = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-createdAt']
        verbose_name = 'Business Profile'
        verbose_name_plural = 'Business Profiles'

    def __str__(self):
        return self.business_name
        

class UserProfile(models.Model):
    user                = models.ForeignKey(User, on_delete=models.CASCADE)
    email               = models.EmailField()
    full_name           = models.CharField(max_length=255, blank=False)
    country             = models.CharField(max_length=155, blank=False)
    state               = models.CharField(max_length=155, blank=False)
    city                = models.CharField(max_length=155, blank=False)
    address             = models.CharField(max_length=155, blank=False)
    phone_number        = models.IntegerField()
    createdAt           = models.DateTimeField(auto_now_add=True)
    updatedAt           = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-createdAt']
        verbose_name = 'User Profile'
        verbose_name_plural = 'User Profiles'

    def __str__(self):
        return self.full_name
