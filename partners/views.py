from decouple import config

# Third party imports.
from rest_framework import generics
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from rest_framework import viewsets


# In project imports.
from .serializers import (
    RegisterPartnerSerializer, PartnerServiceSerializers,
    ServiceAndChargeSerializers, PartnerServiceUploadsSerializers
)
from .models import (
    PartnerServices, ServiceAndCharge, PartnerServiceUploads
)
from accounts.models import User
from accounts.utils import send_email
from accounts.otp import otp_manager


# Create your views here.
# RegisterPartner handles the POST request of registering a user, 
# It takes in firstnmae, lastname, username, email and password
#  and resturns a validation email upon success.
class RegisterPartner(generics.GenericAPIView):
    permission_classes = (AllowAny,)
    serializer_class = RegisterPartnerSerializer

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


class PartnerServiceViewsets(viewsets.ModelViewSet):
    queryset = PartnerServices.objects.all()
    serializer_class = PartnerServiceSerializers


class ServiceAndChargeViewsets(viewsets.ModelViewSet):
    queryset = ServiceAndCharge.objects.all()
    serializer_class = ServiceAndChargeSerializers
    