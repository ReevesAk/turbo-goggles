from django.conf import settings
from decouple import config
import requests


# Third party imports.
from rest_framework import generics
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from rest_framework import viewsets
from rest_framework.parsers import MultiPartParser
from rest_framework.generics import CreateAPIView
from rest_framework.views import APIView


# In project imports.
from .serializers import (
    RegisterPartnerSerializer, PartnerServiceSerializers,
    ServiceAndChargeSerializers, PartnerServiceUploadsSerializers,
    WalletSerializer, DepositSerializer, TransferSerializer,
)
from .models import (
    PartnerServices, ServiceAndCharge, PartnerServiceImageUploads,
    WalletTransaction, Wallet
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
            email_body = 'Hi '+user_obj.first_name, \
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
    

class UploadImage(CreateAPIView):
    serializer_class = PartnerServiceUploadsSerializers
    parser_classes = (MultiPartParser,)
    queryset = PartnerServiceImageUploads.objects.all()


class WalletInfo(APIView):

    def get(self, request):
        wallet = Wallet.objects.get(user=request.user)
        data = WalletSerializer(wallet).data
        return Response(data)


class DepositFunds(APIView):

    def post(self, request):
        serializer = DepositSerializer(
            data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        resp = serializer.save()
        return Response(resp)


class VerifyDeposit(APIView):

    def get(self, request, reference):
        transaction = WalletTransaction.objects.get(
        paystack_payment_reference=reference, wallet__user=request.user)
        reference = transaction.paystack_payment_reference
        url = 'https://api.paystack.co/transaction/verify/{}'.format(reference)
        headers = {
            {"authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}"}
        }    
        r = requests.get(url, headers=headers)
        resp = r.json()
        if resp['data']['status'] == 'success':
            status = resp['data']['status']
            amount = resp['data']['amount']
            WalletTransaction.objects.filter(paystack_payment_reference=reference).update(status=status,
                                                                                        amount=amount)
            return Response(resp)
        return Response(resp)


# TransferFunds handles the transaction between
# two picadailys wallets.
class TransferFunds(APIView):
    
    def post(self, request):
        serializer = TransferSerializer(
            data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        resp = serializer.save()
        return Response(resp)
