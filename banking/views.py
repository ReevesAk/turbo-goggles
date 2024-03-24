import requests
import logging
import json
from threading import Thread
from concurrent.futures import ThreadPoolExecutor
from decouple import config
from accounts.otp import otp_manager
from permissions import IsPartnerUserOrMember
from mail import send_email
from cloudinary import uploader as cloud
from commons import Message

from django.contrib.auth.hashers import make_password
from django.shortcuts import get_object_or_404

# Third party imports.
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.parsers import MultiPartParser, JSONParser
from rest_framework_simplejwt.authentication import JWTAuthentication

from drf_spectacular.utils import extend_schema

# In-projects imports.
from .serializers import (
    BankingStatusSerializer,
    BVNSerializer,
    CustomerUpgradeSerializers,
    CreateUSDAccountSerializers,
    CreateWalletPinSerializer,
    VerifyPinOTPSerializer,
    ResetPinSerializer,
    UpdateCustomerSerializers,
    VirtaulAccountDetailsSerializer,
)
from accounts.models import User, UserNotification
from .models import Wallet, Address, Identity, Phone, BVNData, CustomerData
from .controllers import BVN, Customer


base_url = config("MAPLERAD_BASE_URL")
secret_key = config("MAPLERAD_SECRET_KEY")
headers = {
    "accept": "application/json",
    "content-Type": "application/json",
    "Authorization": "Bearer " + secret_key,
}

picadailys_email = config("EMAIL_HOST_USER")
app_password = config("EMAIL_HOST_PASSWORD")


class VerifYBVN(generics.GenericAPIView):
    serializer_class = BVNSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsPartnerUserOrMember)

    def post(self, request):
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
                data={"status": "success", "message": "User has already verified BVN", "Bvn data": data},
                status=status.HTTP_202_ACCEPTED,
            )
        try:
            bvn = BVNData.objects.get(user=authenticated_user)
        except BVNData.DoesNotExist:
            bvn = BVNData.objects.create(user=authenticated_user)

        serializer = self.serializer_class(data=user_data)
        if serializer.is_valid(raise_exception=True):

            number = BVNData.objects.filter(number=user_data.get("bvn")).exists()
            if number:
                return Response(
                data={"status": "fail", "message": f"User with this bvn: {user_data.get("bvn")} already exist"},
                status=status.HTTP_400_BAD_REQUEST,
            )
            # Verify the user's BVN.
            bvn_response = BVN.verify(bvn=user_data.get("bvn"))
            bvn_status_code = bvn_response.status_code

            if bvn_status_code == 200:
                bvn_data = bvn_response.json()

                # Check if the user's date of birth matches the ones on BVN.
                if all(
                    data != bvn_data["data"][field]
                    for data, field in [
                        (user_data.get("date_of_birth"), "dob"),
                        (user_data.get("phone_number"), "phone_number"),
                    ]
                ):
                    print(user_data.get("date_of_birth"))
                    print(bvn_data["data"]["dob"])
                    return Response(
                        data={
                            "status": "fail",
                            "message": "Date of birth or phone number provided does not match the one on bvn"
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                # Update the user's BVN instance with the new data.
                bvn.first_name = bvn_data["data"]["first_name"]
                bvn.last_name = bvn_data["data"]["last_name"]
                bvn.date_of_birth = bvn_data["data"]["dob"]
                bvn.phone_number = bvn_data["data"]["phone_number"]
                bvn.number = user_data.get("bvn")
                bvn.save()

                authenticated_user.is_bvn_verified = True
                authenticated_user.save()

                serializer = BVNSerializer(data=user_data)

                UserNotification.objects.create(
                    user=request.user,
                    title="BVN Verification.",
                    message="Your BVN Verifiction is successful.",
                )
                # send_email(
                #     subject="BVN Verification.",
                #     body="This is to inform you that your BVN verifiction was successful.",
                #     sender=picadailys_email,
                #     recipients=authenticated_user.email,
                #     password=app_password,
                # )
                response = {
                    "status": "success",
                    "message": "Bvn verification was successful",
                    "bvn data": {
                        "first_name": bvn_data["data"]["first_name"],
                        "last_name": bvn_data["data"]["last_name"],
                        "date_of_birth": bvn_data["data"]["dob"],
                        "phone_number": bvn_data["data"]["phone_number"],
                        "number": user_data.get("bvn"),
                    },
                }
                return Response(data=response, status=status.HTTP_201_CREATED)
            else:
                return Response(data=bvn_response.json(), status=bvn_status_code)
        else:
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class CreateNGNAccount(generics.GenericAPIView):

    """
    CreateNGNAccount handles the POST request of creating a customer wallet in Naira.
    """

    serializer_class = BankingStatusSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsPartnerUserOrMember)

    @extend_schema(
        description="Create account view",
        responses={200: {"description": "Create a Nigerian account"}},
    )
    def post(self, request):
        authenticated_user = request.user

        user_data = User.objects.get(user=authenticated_user)

        try:
            customer = CustomerData.objects.get(email=request.data.get("email"))
        except CustomerData.DoesNotExist:
            customer = CustomerData.objects.create(user=authenticated_user)

        # Create a customer entry on Maplerad.
        customer_data_resp = Customer.create(
            f_name=user_data.first_name,
            l_name=user_data.last_name,
            email=user_data.email,
            country="NG",
        )

        if customer_data_resp.status_code == 200:
            resp = customer_data_resp.json()

            # Update the customer instance with the new data.
            customer.first_name = resp["data"]["first_name"]
            customer.last_name = resp["data"]["last_name"]
            customer.email = resp["data"]["email"]
            customer.country = resp["data"]["country"]
            customer.customer_id = resp["data"]["id"]
            customer.save()

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
            "preferred_bank": "C34",
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

                user_data.has_wallet = True
                user_data.welcome_bonus = 1500.00
                user_data.save()

                UserNotification.objects.create(
                    user=authenticated_user,
                    title="Wallet Creation.",
                    message="Your NGN wallet creation is successful.",
                )
                send_email(
                    subject="Wallet Creation.",
                    body="This is to inform you that your Wallet creation was successful.",
                    sender=picadailys_email,
                    recipients=authenticated_user.email,
                    password=app_password,
                )
                response_data = {
                    "status": "success",
                    "message": "Congratulations your customer wallet has been created\
                        successfully and you have been creidited with a bonus of 1500 that \
                        could be used on the VAS section of our platform.",
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

    serializer_class = BankingStatusSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsPartnerUserOrMember)

    @extend_schema(
        description="Get Customer view",
        responses={200: {"description": "Get Customer details"}},
    )
    def get(self, request):
        user = self.request.user  # Get the authenticated user.

        try:
            customer = CustomerData.objects.get(user=user)
        except CustomerData.DoesNotExist:
            raise NotFound("User does not have an associated customer account!")

        id = customer.customer_id
        if user:
            resource = f"customers/{id}"

            try:
                response = requests.get(
                    url=base_url + resource,
                    header=headers,
                )
                if response.status_code == 200:
                    response_data = {"status": "success", "data": response.json()}
                    return Response(data=response_data, status=status.HTTP_200_OK)

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

    serializer_class = BankingStatusSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsPartnerUserOrMember)

    @extend_schema(
        description="Get customer wallet view",
        responses={200: {"description": "Get customer wallet details"}},
    )
    def get(self, request):
        user = self.request.user  # Get the authenticated user.

        try:
            customer = CustomerData.objects.get(user=user)
        except CustomerData.DoesNotExist:
            raise NotFound("User does not have an associated customer account!")

        id = customer.customer_id
        if user:
            resource = f"customers/{id}/accounts"

            try:
                response = requests.get(
                    url=base_url + resource,
                    header=headers,
                )
                if response.status_code == 200:
                    response_data = {"status": "success", "data": response.json()}
                    return Response(data=response_data, status=status.HTTP_200_OK)

            except requests.exceptions.RequestException as e:
                logging.error(f"Fetching customer wallets API request error: {str(e)}")
                return Response(
                    {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )


class GetVirtualAccountDetails(generics.RetrieveAPIView):

    """
    GetVirtualAccountDetails handles the GET request of retrieving all
    the details of a virtual account. Call this endpoint to update the virtual
    account number.
    """

    serializer_class = VirtaulAccountDetailsSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsPartnerUserOrMember)

    @extend_schema(
        description="Get customer virtual account.",
        responses={200: {"description": "Get customer virtual account details."}},
    )
    def get(self, request):
        user = self.request.user  # Get the authenticated user.

        customer = CustomerData.objects.get(user=user)
        customer_id = customer.customer_id
        wallet = get_object_or_404(Wallet, user=user)
        if user:
            resource = f"customers/{customer_id}/virtual-account"

            try:
                response = requests.get(
                    url=base_url + resource,
                    header=headers,
                )
                if response.status_code == 200:
                    resp = response.json()["data"]
                    for res in resp:
                        # Update a user's account to persist the account number on the database.
                        wallet.account_number = res["account_number"]
                        wallet.save()
                    response_data = {"status": "success", "data": response.json()}
                    return Response(data=response_data, status=status.HTTP_200_OK)

            except requests.exceptions.RequestException as e:
                logging.error(
                    f"Fetching customer virtual account details API request error: {str(e)}"
                )
                return Response(
                    {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )


class CustomerTransctionHistory(generics.RetrieveAPIView):

    """
    CustomerTransctionHistory handles the GET request of retrieving all
    transactions a customer has made.
    """

    serializer_class = BankingStatusSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsPartnerUserOrMember)

    @extend_schema(
        description="Transaction history view",
        responses={200: {"description": "Customer transaction histroy."}},
    )
    def get(self, request):
        user = self.request.user  # Get the authenticated user.

        if user:
            try:
                customer = CustomerData.objects.get(user=user)
            except CustomerData.DoesNotExist:
                raise NotFound("User does not have an associated customer account!")

            id = customer.customer_id
            resource = f"customers/{id}/transactions"

            try:
                response = requests.get(
                    url=base_url + resource,
                    header=headers,
                )
                if response.status_code == 200:
                    response_data = {"status": "success", "data": response.json()}
                    return Response(data=response_data, status=status.HTTP_200_OK)

            except requests.exceptions.RequestException as e:
                logging.error(
                    f"Fetching customer transaction history API request error: {str(e)}"
                )
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
    permission_classes = (IsAuthenticated, IsPartnerUserOrMember)
    parser_classes = (MultiPartParser, JSONParser)

    def update(self, request):
        user = self.request.user  # Get the authenticated user.
        payload = request.data

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
                    "country": "NG",
                },
                "phone": {
                    "phone_country_code": "+234",
                    "phone_number": request.data["phone_number"],
                },
                "first_name": request.data["first_name"],
                "last_name": request.data["last_name"],
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
                    UserNotification.objects.create(
                        user=request.user,
                        title="Update Customer.",
                        message="Your customer update request is successful.",
                    )
                    send_email(
                        subject="Update",
                        body="This is to inform you that your account update request was successful.",
                        sender=picadailys_email,
                        recipients=user.email,
                        password=app_password,
                    )
                    resp = {
                        "status": "success",
                        "message": "Update customer request successful.",
                        "data": response.json(),
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
    permission_classes = (IsAuthenticated, IsPartnerUserOrMember)
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

                    UserNotification.objects.create(
                        user=authenticated_user,
                        title="Account Upgrade.",
                        message="This is to inform you that your account upgrade is successful.",
                    )
                    send_email(
                        subject="Account Upgrade.",
                        body="This is to inform you that your account upgrade was successful.",
                        sender=picadailys_email,
                        recipients=authenticated_user.email,
                        password=app_password,
                    )
                    response = {
                        "status": "success",
                        "message": "User upgraded successfully!",
                        "data": tier2_response.json(),
                    }
                    return Response(data=response, status=status.HTTP_200_OK)

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
    permission_classes = (IsAuthenticated, IsPartnerUserOrMember)

    def post(self, request):
        authenticated_user = request.user
        user_data = request.data

        wallet = Wallet.objects.get(user=authenticated_user).exists()
        if wallet.currency == "USD":
            existing_wallet = {
                "customer_id": wallet.customer_id,
                "first_name": wallet.first_name,
                "last_name": wallet.last_name,
                "currency": wallet.currency,
            }
            response_data = {
                "status": "fail",
                "message": "User already has a dollar wallet!",
                "data": existing_wallet,
            }
            return Response(data=response_data, status=status.HTTP_400_BAD_REQUEST)

        # Check if the user has an NGN wallet
        has_ngn_wallet = Wallet.objects.filter(
            user=authenticated_user, currency="NGN"
        ).exists()

        if not has_ngn_wallet:
            response_data = {
                "status": "fail",
                "message": "User must have an NGN wallet before creating a USD wallet!",
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

                    UserNotification.objects.create(
                        user=authenticated_user,
                        title="Wallet Creation.",
                        message="Your dollar account was created successfully.",
                    )
                    send_email(
                        subject="Wallet Creation.",
                        body="This is to inform you that your dollar account was successfully.",
                        sender=picadailys_email,
                        recipients=authenticated_user.email,
                        password=app_password,
                    )

                    response_data = {
                        "status": "success",
                        "message": "Creation of dollar wallet successful",
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
    """
    SetWalletPin handles the POST request of creating a pin for a
    customer wallet.
    """

    serializer_class = CreateWalletPinSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsPartnerUserOrMember)

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

            UserNotification.objects.create(
                user=authenticated_user,
                title="Wallet Pin.",
                message="Wallet pin created successfully.",
            )
            send_email(
                subject="Wallet Pin.",
                body="This is to inform you that your Wallet pin was created successful.",
                sender=picadailys_email,
                recipients=authenticated_user.email,
                password=app_password,
            )
            response = {
                "status": "success",
                "message": "Wallet pin created succesfully!",
            }
            return Response(data=response, status=status.HTTP_201_CREATED)


class ForgotWalletPin(generics.GenericAPIView):
    """
    ForgotWalletPin handles the POST request of sending a requeest to
    reset a pin for a customer's wallet.
    """

    serializer_class = BankingStatusSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsPartnerUserOrMember)

    @extend_schema(
        description="Forgot pin view",
        responses={200: {"description": "Forgot wallet pin"}},
    )
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

    serializer_class = BankingStatusSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsPartnerUserOrMember)

    @extend_schema(
        description="Resend Otp",
        responses={200: {"description": "Resend otp"}},
    )
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
    """
    PinVerifyOTP handles the POST request of verifying an
    OTP after wallet pin change request.
    """

    serializer_class = VerifyPinOTPSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsPartnerUserOrMember)

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
                data = {"status": "success", "message": "Account is verified"}
                return Response(data=data, status=status.HTTP_200_OK)


class ResetPin(generics.CreateAPIView):
    serializer_class = ResetPinSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsPartnerUserOrMember)

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

            UserNotification.objects.create(
                user=authenticated_user,
                title="Reset Wallet Pin.",
                message="Wallet pin reset was successful.",
            )
            send_email(
                subject="Reset Wallet Pin.",
                body="This is to inform you that your Wallet pin reset was successful.",
                sender=picadailys_email,
                recipients=authenticated_user.email,
                password=app_password,
            )

            response = {"status": "success", "message": "Pin reset successfully"}
            return Response(data=response, status=status.HTTP_200_OK)
        else:
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class GetAllBanks(generics.RetrieveAPIView):
    """
    GetAllBanks handles the GETT request of listing
    all institutions by type, code and country.
    """

    serializer_class = BankingStatusSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsPartnerUserOrMember)

    @extend_schema(
        description="Get all banks view",
        responses={200: {"description": "All financial institutions and bank codes"}},
    )
    def get(self, request, *args, **kwargs):
        user = self.request.user  # Get the authenticated user.

        if user:
            resource = "institutions"
            try:
                response = requests.get(url=base_url + resource, headers=headers)
                if response.status_code == 200:
                    response_data = {
                        "status": "success",
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
