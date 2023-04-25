import os

from django.shortcuts import render
from django.contrib.sites.shortcuts import get_current_site
from django.urls import reverse
from django.shortcuts import get_object_or_404

# Third party imports.
from rest_framework import generics
from rest_framework.response import Response
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
import jwt
from django.conf import settings

# In project imports.
from .serializers import RegisterSerializer, LoginSerializer
from .models import User 
from commons import generateOTP
from .renderers import UserRenderer

# Register handles the POST request of registering a user, 
# It takes in firstnmae, lastname, username, email and password
#  and resturns a validation email upon success.
class Register(generics.GenericAPIView):

    serializer_class = RegisterSerializer
    renderer_classes = (UserRenderer,)

    def post(self, request):
        user = request.data
        serializer = self.serializer_class(data=user)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        user_data = serializer.data

        # Retrieve user email.
        user = User.objects.get(email=user_data['email'])

        # token = RefreshToken.for_user(user).access_token

        # current_site = get_current_site(request).domain
        # relative_link = reverse('verify_email')
        # absolute_url = 'http://'+current_site+relative_link  +"?token="+str(token)
        # email_body = 'Hi '+user.username + \
        #     'Please use the link below to verify your email \n' + absolute_url
        # data = {'email_body': email_body, 
        #         'to_email': user.email,
        #         'email_subject': 'Verify your email'}
        
        # Util.send_email(data)

        generateOTP(user)

        return Response(user_data, status=status.HTTP_201_CREATED)
    

# EmailVerify handles the GET request of verifying a register user with valid email.
class EmailVerify(generics.GenericAPIView):
    def get(self, request):
        token = request.GET.get('token')
        try:
            payload = jwt.decode(token, settings.SECRET_KEY)
            user = User.objects.get(id=payload['user_id'])
            if not user.is_verified:
                user.verified =True
                user.save()
            return Response({'email': 'Successfully activated'}, status=status.HTTP_200_OK)
        except jwt.ExpiredSignatureError as identifier:
            return Response({'error': 'Activation Token Expired'}, status=status.HTTP_400_BAD_REQUEST)
        except jwt.exceptions.DecodeError as identifier:
            return Response({'error': 'Invalid token'}, status=status.HTTP_400_BAD_REQUEST)
        

# LoginAPIView handles the POST request of logging in
# a verified user with valid login credentials.
class Login(generics.GenericAPIView):
    serializer_class = LoginSerializer

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
