from decouple import config
import smtplib
import math
import random

# Third party imports.
from rest_framework import generics
from rest_framework.response import Response
from rest_framework import status, serializers

# In project imports.
from .serializers import RegisterSerializer, LoginSerializer, VerifyOTPSerailizer
from .models import User


global OTP

# Register handles the POST request of registering a user, 
# It takes in firstnmae, lastname, username, email and password
#  and resturns a validation email upon success.
class Register(generics.GenericAPIView):

    serializer_class = RegisterSerializer

    def post(self, request):
        user = request.data
        serializer = self.serializer_class(data=user)
        if serializer.is_valid(raise_exception=True):
            serializer.save()
            user_data = serializer.data
        else:
            serializers.ValidationError()
        # Connect to smtp mail server and login using email and app_password.
        s = smtplib.SMTP('smtp.gmail.com', 587)
        s.starttls()
        host_email = config('EMAIL_HOST_USER')
        app_password = config('EMAIL_HOST_PASSWORD')
        s.login(host_email, app_password)

        # Retrieve user email.
        user_obj = User.objects.get(email=user_data['email'])

        # generate otp
        digits="0123456789"

        for i in range(6):
            OTP+=digits[math.floor(random.random()*10)]


        subject = 'Verify your email'
        email_body = 'Hi '+user_obj.username + \
            'Please use the one time password to verify your email \n' + OTP
        message = 'Subject: {}\n\n{}'.format(subject, email_body)

        data = {'email_body': message,
                'from_email': host_email,
                'to_email': user_obj.email}
        
         # send mail
        s.sendmail(
                from_addr=data['host_email'], 
                to_addrs=data['user.email'], 
                msg=data['email_body'],
            )


        return Response(user_data, status=status.HTTP_201_CREATED)
    

# EmailVerify handles the GET request of verifying a register user with valid email.
class EmailVerifyOTP(generics.GenericAPIView):
    def post(self, request):
        data = request.data
        serializer = VerifyOTPSerailizer(data=data) 
        user_data = serializer.data

        if serializer.is_valid():
            otp = serializer.data['otp']

            user = User.objects.get(email=user_data['email'])

            if otp == OTP:
                user.is_verified = True
                user.save()
            return Response(user_data, status=status.HTTP_201_CREATED) 


# LoginAPIView handles the POST request of logging in
# a verified user with valid login credentials.
class Login(generics.GenericAPIView):
    serializer_class = LoginSerializer

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
