from decouple import config

# Third party imports.
from rest_framework import generics
from django.contrib.auth import authenticate
from rest_framework.request import Request
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

# In project imports.
from .serializers import (RegisterSerializer, LoginSerializer, 
    VerifyOTPSerailizer, ResetPasswordSerializer)
from .models import User
from .utils import send_email
from .otp import otp_manager
from .tokens import create_jwt_pair_for_user


# Register handles the POST request of registering a user, 
# It takes in firstnmae, lastname, username, email and password
#  and resturns a validation email upon success.
class Register(generics.GenericAPIView):
    permission_classes = (AllowAny,)
    serializer_class = RegisterSerializer

    def post(self, request):
        user = request.data
        serializer = self.serializer_class(data=user)
        if serializer.is_valid(raise_exception=True):
            serializer.save()
            user_data = serializer.data

            otp = otp_manager.create_otp(user_id=str(request.data.get('id')))
            print(otp)
        
           # Retrieve host email and password.
            host_email = config('EMAIL_HOST_USER')
            app_password = config('EMAIL_HOST_PASSWORD')

            # Retrieve user email.
            user_obj = User.objects.get(email=user_data['email'])

            subject = 'Picadailys - Verify your email'
            email_body = 'Hi '+user_obj.firstname, + \
                'use this one time password(OTP) provided to verify your email \n' + otp
            message = 'Subject: {}\n\n{}'.format(subject, email_body)

    
            # send mail.
            send_email(
                subject=subject,
                body=message,
                sender=host_email,
                recipients=[user_obj.email],
                password=app_password
            )

            response = {"message": "User Created Successfully. An OTP has been sent to your mail for verification", "data": serializer.data}
            return Response(data=response, status=status.HTTP_201_CREATED)
        else:
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    

# EmailVerify handles the GET request of verifying a register user with valid email.
class EmailVerifyOTP(generics.GenericAPIView):
    permission_classes = (AllowAny,)
    serializer_class = VerifyOTPSerailizer

    def post(self, request):
        data = request.data
        serializer = self.serializer_class(data=data) 
        user_data = serializer.data

        if serializer.is_valid():
            received_otp = serializer.data['otp']

            user = User.objects.get(email=user_data['email'])

            # Validate otp.
            user_id = otp_manager.validate_user_otp(str(received_otp))
            if not user_id:
                return Response(data={"error": "Invalid or expired otp"}, status=status.HTTP_400_BAD_REQUEST)

            user = User.objects.get(id=user_id)
            user.is_verified = True
            user.save()
 
            return Response({"Success": "Account is verified"}, status=status.HTTP_201_CREATED)


# LoginAPIView handles the POST request of logging in
# a verified user with valid login credentials.
class Login(APIView):
    permission_classes = (AllowAny,)
    serializer_class = LoginSerializer

    def post(self, request: Request):
        email = request.data.get("email")
        password = request.data.get("password")

        user = authenticate(email=email, password=password)

        if user is not None:

            tokens = create_jwt_pair_for_user(user)

            response = {
                "message": "Login Successfull", 
                "id": user.id,
                "tokens": tokens
            }
            return Response(data=response, status=status.HTTP_200_OK)

        else:
            return Response(data={"message": "Invalid email or password"})

    def get(self, request: Request):
        content = {"user": str(request.user), "auth": str(request.auth)}

        return Response(data=content, status=status.HTTP_200_OK)
    

class ForgotPassword(generics.GenericAPIView):
    serializer_class = ResetPasswordSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, )
    def post(self, request):
        user = request.data
        serializer = self.serializer_class(data=user)
        if serializer.is_valid(raise_exception=True):
            serializer.save()
            user_data = serializer.data
        
            # Retrieve host email and password.
            host_email = config('EMAIL_HOST_USER')
            app_password = config('EMAIL_HOST_PASSWORD')

            otp = otp_manager.create_otp(user_id=str(request.data.get('id')))
            
            # Retrieve user email.
            user_obj = User.objects.get(email=user_data['email'])

            subject = 'Verify your email'
            email_body = 'Hi '+user_obj.username, + \
                'use the one time password(OTP) provided to reset your password \n' + otp
            message = 'Subject: {}\n\n{}'.format(subject, email_body)

    
            # send mail.
            send_email(
                subject=subject,
                body=message,
                sender=host_email,
                recipients=[user_obj.email],
                password=app_password
            )
            
            return Response(serializer.data, status=status.HTTP_200_OK)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        

class ResetPassword(generics.GenericAPIView):
    serializer_class = ResetPasswordSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, )

    def post(self, request):
        user = request.data
        serializer = self.serializer_class(data=user)
        if serializer.is_valid(raise_exception=True):
            serializer.save()
            user_data = serializer.data

            return Response(user_data, status=status.HTTP_201_CREATED)
        