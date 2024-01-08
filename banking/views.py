import requests
import logging
import json
from threading import Thread
from concurrent.futures import ThreadPoolExecutor
from decouple import config
from accounts.otp import otp_manager
from permissions import IsPartnerOrMember
from cloudinary import uploader as cloud
from commons import Message

from django.contrib.auth.hashers import make_password

# Third party imports.
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from rest_framework.parsers import MultiPartParser, JSONParser
from rest_framework_simplejwt.authentication import JWTAuthentication

# In-projects imports.
from .serializers import (
    BVNSerializer,
    CustomerUpgradeSerializers,
    CreateUSDAccountSerializers,
    CreateWalletPinSerializer,
    VerifyOTPSerializer,
    ResetPinSerializer,
    UpdateCustomerSerializers,
)
from .models import Wallet, Address, Identity, Phone, BVNData, CustomerData
from .controllers import BVN, Customer


base_url = config("MAPLERAD_BASE_URL")
secret_key = config("MAPLERAD_SECRET_KEY")
headers = {
    "accept": "application/json",
    "content-Type": "application/json",
    "Authorization": "Bearer " + secret_key,
}


class VerifYBVN(generics.CreateAPIView):
    serializer_class = BVNSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsPartnerOrMember)

    def create(self, request):
        user_data = request.data
        authenticated_user = request.user

        if authenticated_user.is_bvn_verified:
            bvn_deets = BVNData.objects.filter(user=authenticated_user).first()
            data = {
                "First Name": bvn_deets.first_name,
                "Last Name": bvn_deets.last_name,
                "Phone_no": bvn_deets.phone_number,
                "Date of Birth": bvn_deets.date_of_birth,
                "Bvn": user_data.get("bvn"),
            }
            return Response(
                data={"message": "User has already verified BVN", "Bvn data": data},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            bvn = BVNData.objects.get(user=authenticated_user)
        except BVNData.DoesNotExist:
            bvn = BVNData.objects.create(user=authenticated_user)

        serializer = self.serializer_class(data=user_data)
        if serializer.is_valid(raise_exception=True):
            # Verify the user's BVN.
            bvn_response = BVN.verify(bvn=user_data.get("bvn"))
            bvn_status_code = bvn_response.status_code

            if bvn_status_code == 200:
                bvn_data = bvn_response.json()

                # Check if the user's date of birth and phone number match the ones on BVN.
                if (
                    user_data.get("date_of_birth") != bvn_data["date_of_birth"]
                    or user_data.get("phone_number") != bvn_data["phone_num"]
                ):
                    return Response(
                        data={
                            "message": "Date of birth or phone number provided does not match the one on bvn"
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                # Update the user's BVN instance with the new data.
                bvn.first_name = bvn_data["first_name"]
                bvn.last_name = bvn_data["last_name"]
                bvn.date_of_birth = bvn_data["date_of_birth"]
                bvn.phone_number = bvn_data["phone_num"]
                bvn.number = user_data.get("bvn")
                bvn.save()

                authenticated_user.is_bvn_verified = True
                authenticated_user.save()

                serializer = BVNSerializer(data=user_data)

                response = {
                    "status": "Success",
                    "message": "Bvn verification was successful",
                    "Bvn data": serializer.data,
                }
                return Response(data=response, status=status.HTTP_201_CREATED)
            else:
                return Response(data=bvn_response.json(), status=bvn_status_code)


class CreateNGNAccount(generics.GenericAPIView):

    """
    CreateNGNAccount handles the POST request of creating a customer wallet in Naira.
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsPartnerOrMember)

    def post(self, request):
        authenticated_user = request.user

        user_exist = Wallet.objects.get(user=authenticated_user).exists()
        if user_exist:
            existing_wallet = {
                "customer_id": user_exist.customer_id,
                "bank_name": user_exist.bank_name,
                "currency": user_exist.currency,
            }
            response_data = {
                "message": "User already has a wallet!",
                "data": existing_wallet,
            }
            return Response(data=response_data, status=status.HTTP_400_BAD_REQUEST)

        resource = "collections/virtual-account"
        payload = {
            "customer_id": user_exist.customer_id,
            "currency": "NGN",
            "preferred_bank": "101",
            "country": "NG",
        }
        try:
            response = requests.post(
                url=base_url + resource,
                json=payload,
                headers=headers,
            )
            try:
                # Check if the response contains valid JSON
                response.json()
            except json.JSONDecodeError:
                # If JSON parsing fails, handle the error as needed
                return Response(
                    {"error": "Invalid JSON response from the external API"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
            if response.status_code == 200:
                account_details = Wallet.objects.create(
                    user=authenticated_user,
                    customer_id=user_exist.customer_id,
                    currency="NGN",
                    bank_name=response.json()["data"]["preferred_bank"],
                )
                account_details.save()

                response_data = {
                    "message": "Customer wallet created successfully",
                    "data": response.json(),
                }

                return Response(data=response_data, status=status.HTTP_201_CREATED)
            else:
                return Response(response.json(), status=response.status_code)

        except requests.exceptions.RequestException as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class GetCustomer(generics.RetrieveAPIView):

    """
    GetCustomer handles the GET request of retrieving a 
    customer's wallet information.
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsPartnerOrMember)

    def get(self, request):
        user = self.request.user  # Get the authenticated user.

        customer = CustomerData.objects.get(user=user)
        id = customer.customer_id
        if user:
            resource = f"customers/{id}"

            try:
                response = requests.get(
                    url=base_url + resource,
                    header=headers,
                )
                if response.status_code == 200:
                    return Response(data=response.json(), status=status.HTTP_200_OK)

            except requests.exceptions.RequestException as e:
                logging.error(f"Fetching customer API request error: {str(e)}")
                return Response(
                    {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )


class GetCustomersWallets(generics.RetrieveAPIView):

    """
    GetCustomersAccounts handles the GET request of retrieving all 
    the accounts created by a customer.
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsPartnerOrMember)

    def get(self, request):
        user = self.request.user  # Get the authenticated user.

        customer = CustomerData.objects.get(user=user)
        id = customer.customer_id
        if user:
            resource = f"customers/{id}/accounts"

            try:
                response = requests.get(
                    url=base_url + resource,
                    header=headers,
                )
                if response.status_code == 200:
                    return Response(data=response.json(), status=status.HTTP_200_OK)

            except requests.exceptions.RequestException as e:
                logging.error(f"Fetching customer wallets API request error: {str(e)}")
                return Response(
                    {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )


class CustomerTransctionHistory(generics.RetrieveAPIView):

    """
    CustomerTransctionHistory handles the GET request of retrieving all 
    transactions a customer has made.
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsPartnerOrMember)

    def get(self, request):
        user = self.request.user  # Get the authenticated user.

        if user:
            customer = CustomerData.objects.get(user=user)
            id = customer.customer_id
            resource = f"customers/{id}/transactions"

            try:
                response = requests.get(
                    url=base_url + resource,
                    header=headers,
                )
                if response.status_code == 200:
                    return Response(data=response.json(), status=status.HTTP_200_OK)

            except requests.exceptions.RequestException as e:
                logging.error(f"Fetching customer transaction history API request error: {str(e)}")
                return Response(
                    {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )


class UpdateCustomer(generics.RetrieveAPIView):

    """
    UpdateCustomer handles the PATCH request of updating 
    customer information.
    """
    serializer_class = UpdateCustomerSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsPartnerOrMember)
    parser_classes = (MultiPartParser, JSONParser)

    def update(self, request):
        user = self.request.user  # Get the authenticated user.

        if user:
            customer = CustomerData.objects.get(user=user)
            id = customer.customer_id
        
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid(raise_exception=True):
            # Start a separate thread for image upload
            thread_upload = Thread(
                target=self.upload_image,
                args=(payload.get("image"),),
            )
            thread_upload.start()

            resource = "customers/update"
            payload = {
                "customer_id": id,
                "identity": {
                    "type": request.data["type"],
                    "image": self.uploaded_image_url,
                    "number": request.data["number"],
                    "country": "NG"
                },
                "phone": {
                    "phone_country_code": "+234",
                    "phone_number": request.data["phone_number"]
                },
                "first_name": request.data["first_name"],
                "last_name": request.data["last_name"]
            }

            customer.first_name = request.data["first_name"]
            customer.last_name = request.data["last_name"]
            customer.save()

            identity = Identity.objects.get(user=customer)
            identity.type = request.data["type"]
            identity.image = self.uploaded_image_url
            identity.number = request.data["number"]
            identity.save()

            phone = Phone.objects.get(user=customer)
            phone.phone_number = request.data["phone"]
            phone.save()

            try:
                response = requests.post(
                    url=base_url + resource,
                    json=payload,
                    header=headers,
                )
                if response.status_code == 200:
                    resp = {
                        "message": "Update customer request done.",
                        "data": response.json()
                    }
                    return Response(data=resp, status=status.HTTP_200_OK)
                else:
                    return Response(data=response.json(), status=response.status_code)

            except requests.exceptions.RequestException as e:
                logging.error(f"Update customer to Tier 1 API request error: {str(e)}")
                return Response(
                    {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

    def upload_image(self, image_data):
        doc_image = cloud.upload(file=image_data)
        self.uploaded_image_url = doc_image["url"]


class UpgradeAccount(generics.CreateAPIView):

    """
    UpgradeAccount handles the POST request of upgrading a customer
    to Tier1 and Tier 2 respectfully.
    """

    serializer_class = CustomerUpgradeSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsPartnerOrMember)
    parser_classes = (MultiPartParser, JSONParser)

    def post(self, request):
        authenticated_user = request.user
        payload = request.data

        if authenticated_user.is_upgraded is True:
            return Response(data="User is already upgraded")

        customer = CustomerData.objects.get(user=authenticated_user)
        bvn = BVNData.objects.get(user=authenticated_user)

        serializer = self.serializer_class(data=payload)
        if serializer.is_valid(raise_exception=True):
            # Start a separate thread for image upload
            thread_upload = Thread(
                target=self.upload_image,
                args=(payload.get("image"),),
            )
            thread_upload.start()

            tier1_response = Customer.upgradeTier1(
                id=customer.customer_id,
                dob=bvn.date_of_birth,
                phone=bvn.phone_number,
                street=payload.get("street"),
                street2=payload.get("street2"),
                city=payload.get("city"),
                state=payload.get("state"),
                postal_code=payload.get("postal_code"),
                bvn=bvn.number,
            )
            if tier1_response.status_code == 200:
                phone = Phone.objects.create(
                    user=customer,
                    country_code="+234",
                    phone_number=payload.get("phone"),
                )
                phone.save()
                address = Address.objects.create(
                    user=customer,
                    street=payload.get("street"),
                    street2=payload.get("street2"),
                    city=payload.get("city"),
                    state=payload.get("state"),
                    country="NG",
                    postal_code=payload.get("postal_code"),
                )
                address.save()

                tier2_response = Customer.upgradeTier2(
                    customer_id=customer.customer_id,
                    id_type=payload.get("type"),
                    id_img=self.uploaded_image_url,
                    id_no=payload.get("number"),
                )
                tier2_status_code = tier2_response.status_code

                if tier2_status_code == 200:
                    identity = Identity.objects.create(
                        user=customer,
                        type=payload.get("type"),
                        image=self.uploaded_image_url,
                        number=payload.get("number"),
                        country="NG",
                    )
                    identity.save()
                    return Response(data="User upgraded successfully!")

                else:
                    return Response(
                        data=tier2_response.json(), status=tier2_status_code
                    )

    def upload_image(self, image_data):
        doc_image = cloud.upload(file=image_data)
        self.uploaded_image_url = doc_image["url"]


class CreateUSDAccount(generics.CreateAPIView):
    """
    CreateUSDAccount handles the POST request of creating a customer wallet in USD.
    """

    serializer_class = CreateUSDAccountSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsPartnerOrMember)

    def post(self, request):
        authenticated_user = request.user
        user_data = request.data

        wallet = Wallet.objects.get(user=authenticated_user.occupation).exists()
        if wallet.currency == "USD":
            existing_wallet = {
                "customer_id": wallet.customer_id,
                "first_name": wallet.first_name,
                "last_name": wallet.last_name,
                "currency": wallet.currency,
            }
            response_data = {
                "message": "User already has a dollar wallet!",
                "data": existing_wallet,
            }
            return Response(data=response_data, status=status.HTTP_400_BAD_REQUEST)

        resource = "collections/virtual-account"

        serializer = self.serializer_class(data=user_data)
        if serializer.is_valid(raise_exception=True):
            with ThreadPoolExecutor() as executor:
                # Submit image upload tasks to the thread pool.
                utility_upload = executor.submit(
                    self.upload_image, user_data.get("utility_bill")
                )
                bank_statement = executor.submit(
                    self.upload_image, user_data.get("bank_statement")
                )

                # Wait for both uploads to complete
                utility_upload_url = utility_upload.result()
                bank_statement_url = bank_statement.result()

            payload = {
                "customer_id": wallet.customer_id,
                "currency": "USD",
                "preferred_bank": "631",
                "meta": {
                    "occupation": user_data.get("occupation"),
                    "bank_statement": bank_statement_url,
                    "identity_type": "PASSPORT",
                    "identity_issued_date": user_data.get("identity_issued_date"),
                    "identity_expiration": user_data.get("identity_expiration"),
                    "utility_bill": utility_upload_url,
                },
            }
            try:
                response = requests.post(
                    url=base_url + resource,
                    json=payload,
                    header=headers,
                )
                if response.status_code == 200:
                    # Update wallet fields to save dollar wallet data.
                    wallet.occupation = user_data.get("occupation")
                    wallet.utility_bill = utility_upload_url
                    wallet.bank_statement = bank_statement_url
                    wallet.identity_number = user_data.get("identity_number")
                    wallet.identity_issued_date = user_data.get("identity_issued_date")
                    wallet.identity_expiration = user_data.get("identity_expiration")
                    wallet.save()

                    response_data = {
                        "message": "Creation of dollar wallet API request",
                        "data": response.json(),
                    }
                    return Response(data=response_data, status=status.HTTP_200_OK)
                else:
                    return Response(response.json(), status=response.status_code)
            except requests.exceptions.RequestException as e:
                logging.error(f"Creation of dollar wallet API request error: {str(e)}")
                return Response(
                    {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

    def upload_image(self, image_data):
        # Implement image upload logic here
        # For example, using a utility function
        uploaded_image = cloud.upload(file=image_data)
        return uploaded_image["url"]


class SetWalletPin(generics.CreateAPIView):
    serializer_class = CreateWalletPinSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsPartnerOrMember)

    def create(self, request, *args, **kwargs):
        user_data = request.data
        authenticated_user = request.user

        try:
            user = Wallet.objects.get(user=authenticated_user)
        except Wallet.DoesNotExist:
            return Response(
                data={"error": "Wallet not found for the authenticated user."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = self.serializer_class(data=user_data)
        if serializer.is_valid(raise_exception=True):
            pin = user_data.get("pin")
            pin2 = user_data.get("pin2")

            if pin != pin2:
                return Response(
                    data={"error": "Pins do not match!"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Hash the pin using make_password
            hashed_pin = make_password(pin)

            # set the hashed_pin and save it in the 'pin' flag on the db.
            user.pin = hashed_pin
            user.save()

            response = {
                "status": "Success!",
                "message": "Wallet pin created succesfully!",
            }
            return Response(data=response, status=status.HTTP_201_CREATED)


class ForgotWalletPin(generics.GenericAPIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsPartnerOrMember)

    def post(self, request):
        user = request.user
        phone_no = user.phone_number
        # Create and send OTP.
        otp = otp_manager.create_otp(user_id=str(user.id))
        msg = "Enter this OTP {} to verify your account and reset your pin".format(otp)

        response = Message.send_otp(msg=str(msg), to=phone_no)
        if response.status_code == 200:
            try:
                response = {
                    "status": "success",
                    "message": "Check your phone for an OTP",
                }
                return Response(data=response, status=status.HTTP_201_CREATED)
            except Exception as err:
                return Response(
                    {
                        "status": "fail",
                        "message": err,
                    },
                    status=status.HTTP_409_CONFLICT,
                )
        else:
            return Response(data=response, status=response.status_code)


class PinResendOTP(generics.GenericAPIView):
    """
    PinResendOTP handles the POST request of resending an
    OTP to a user.
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsPartnerOrMember)

    def post(self, request):
        user = request.user
        phone_number = user.phone_number

        # Generate otp.
        otp = otp_manager.create_otp(user_id=str(user.id))
        msg = "To reset your pin, please enter this One Time Password {}.".format(otp)

        response = Message.send_otp(msg=str(msg), to=phone_number)
        if response.status_code == 200:
            response = {
                "status": "success",
                "message": "Otp resent Successfully. Check your phone for validation",
            }
            return Response(data=response, status=status.HTTP_200_OK)
        else:
            return Response(data=response, status=response.status_code)


class PinVerifyOTP(generics.GenericAPIView):
    serializer_class = VerifyOTPSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsPartnerOrMember)

    def post(self, request):
        user = request.data
        user_data = request.user
        serializer = self.serializer_class(data=user)
        if serializer.is_valid(raise_exception=True):
            received_otp = serializer.data["otp"]

            # Validate otp.
            user_id = otp_manager.validate_user_otp(received_otp)

            if not user_id:
                return Response(
                    data={"error": "Invalid or expired OTP"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Send welcome message to user.
            msg = "User is verified... You can reset now your pin!"
            recipient = user_data.phone_number

            response = Message.send_msg(msg=str(msg), to=recipient)
            if response.status_code == 200:
                return Response(
                    {"Success": "Account is verified"}, status=status.HTTP_200_OK
                )


class ResetPin(generics.CreateAPIView):
    serializer_class = ResetPinSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsPartnerOrMember)

    def create(self, request):
        authenticated_user = request.user
        user_data = request.data
        serializer = self.get_serializer(data=request.data)

        try:
            user = Wallet.objects.get(user=authenticated_user)
        except Wallet.DoesNotExist:
            return Response(
                data={"error": "Wallet not found for the authenticated user."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if serializer.is_valid(raise_exception=True):
            otp = user_data["otp"]
            user_id = otp_manager.validate_user_otp(otp=otp)

            if not user_id:
                return Response(
                    data={"error": "Invalid or expired OTP"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            pin = user_data.get("pin")
            pin2 = user_data.get("pin2")

            if pin != pin2:
                return Response(
                    data={"error": "Pins do not match!"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            user.pin = pin
            user.save()

            response = {"status": "Success!", "message": "Pin reset successfully"}
            return Response(data=response, status=status.HTTP_200_OK)
        else:
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class GetAllBanks(generics.RetrieveAPIView):
    """
    GetAllBanks handles the GETT request of listing 
    all institutions by type, code and country.
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsPartnerOrMember)

    def get(self, request, *args, **kwargs):
        user = self.request.user  # Get the authenticated user.

        if user:
            resource = "institutions"
            try:
                response = requests.get(
                    url=base_url + resource, headers=headers
                )
                if response.status_code == 200:
                    response_data = {
                        "data": response.json(),
                    }

                    return Response(data=response_data, status=status.HTTP_200_OK)
                else:
                    return Response(response.json(), status=response.status_code)
            
            except requests.exceptions.RequestException as e:
                logging.error(f"Listing all institutions API request error: {str(e)}")
                return Response(
                    {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )