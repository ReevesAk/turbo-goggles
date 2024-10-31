import logging
import requests
from django.template.loader import render_to_string
from django.db.models import Q
from commons import Message

# In project imports.
from .serializers import ListWalletUsersSerializer, AdminBankAccountCreationSerializers
from .views import PaginationStyle
from .models import ActivityModel

# Third party imports.
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.parsers import MultiPartParser, JSONParser

from accounts.models import User, UserNotification
from banking.models import AccountCreation, BVNData
from banking.serializers import GetAccountSerializer
from banking.controllers import Account, BVN
from permissions import IsSuperAdmin, IsNotDisabled, IsWalletAdminOrSuperAdmin


class GetallWalletUsers(generics.ListAPIView):
    """
    GetallWalletUsers is the GET request to retrieve the count
    of all wallet owners.
    """

    queryset = AccountCreation.objects.all().order_by("created_at")
    serializer_class = ListWalletUsersSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [
        IsAuthenticated,
        IsNotDisabled,
        IsWalletAdminOrSuperAdmin,
    ]
    pagination_class = PaginationStyle

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)

        if page is not None:
            serialized_users = self.get_serializer(page, many=True)
            return self.get_paginated_response(
                {
                    "status": "success",
                    "message": "All Wallet owners retrieved successfully.",
                    "num_of_wallet_owners": queryset.count(),
                    "wallet_owners": serialized_users.data,
                }
            )

        # In case pagination is not used
        serialized_users = self.get_serializer(queryset, many=True)
        count = queryset.count()
        data = serialized_users.data
        body = f"This is to inform you that {count} users have opened an account with Picadailys and these are their details: {data}."
        print("I dey work")

        email_content = render_to_string(
            "email_template.html",
            {
                "email": "OGafekemor@picadailys.com",
                "picadailys_phone": "08134649680",
                "message_body": body,
            },
        )

        Message.send_email(
            content=email_content,
            email="akwareeves@gmail.com",
            subject="Testing Subject.",
        )

        return Response(
            {
                "status": "success",
                "message": "All Wallet owners retrieved successfully.",
                "num_of_wallet_owners": queryset.count(),
                "wallet_owners": serialized_users.data,
            },
            status=status.HTTP_200_OK,
        )


class CreateBankAccountForUser(generics.GenericAPIView):
    """
    CreateBankAccountForUser handles the POST request of
    creating an account for a user.
    """

    serializer_class = AdminBankAccountCreationSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = [
        IsAuthenticated,
        IsNotDisabled,
        IsWalletAdminOrSuperAdmin
    ]
    parser_classes = (
        MultiPartParser,
        JSONParser,
    )

    def post(self, request, *args, **kwargs):
        admin_user = request.user
        payload = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in request.data.items()
        }

        email = kwargs.get("email")
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            logging.error("User not found")
            return Response(data={"detail": "User does not exist"}, status=status.HTTP_401_UNAUTHORIZED)

        # Retrieve files only if user exists
        passport = request.FILES.get("passport")
        identity = request.FILES.get("identity")
        utility = request.FILES.get("utility")
        signature = request.FILES.get("signature")

        # Validate payload with serializer
        serializer = AdminBankAccountCreationSerializers(data=payload)
        if not serializer.is_valid():
            logging.error(f"Validation Errors: {serializer.errors}")
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        bvn_response = BVN.verify(bvn=request.data.get("bvn"))
        bvn_status_code = bvn_response.status_code

        try:
            if bvn_status_code == 200:
                bvn_data = bvn_response.json()

                # Check if the user's date of birth matches the ones on BVN.
                if request.data.get("date_of_birth") != bvn_data["DOB"]:
                    return Response(
                        data={
                            "status": "fail",
                            "message": "Date of birth or phone number provided does not match the one on bvn",
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                try:
                    bvn = BVNData.objects.get(user=user)
                except BVNData.DoesNotExist:
                    bvn = BVNData.objects.create(user=user)

                # Update the user's BVN instance with the new data.
                bvn.first_name = bvn_data["FirstName"]
                bvn.last_name = bvn_data["LastName"]
                bvn.date_of_birth = bvn_data["DOB"]
                bvn.phone_number = bvn_data["Phone"]
                bvn.number = bvn_data["bvn"]
                bvn.save()

                user.is_bvn_verified = True
                user.save()
            else:
                return Response(data=bvn_response.json(), status=bvn_status_code)

        except Exception as err:
            return Response(
                {
                    "status": "fail",
                    "message": err,
                },
                status=status.HTTP_409_CONFLICT,
            )
        try:
            acc_response = Account.Open(
                addr=request.data.get("address"),
                tc=request.data.get("tc"),
                acc_type="65",
                religion=request.data.get("religion"),
                ms=request.data.get("ms"),
                gn=request.data.get("gn"),
                branch="203",
                bvn=request.data.get("bvn"),
                state=request.data.get("state"),
                lga=request.data.get("lga"),
                country=request.data.get("country"),
                altEmail=request.data.get("alt_email"),
                altPhone=request.data.get("alt_phone"),
                currentAddress=request.data.get("address"),
                nin=request.data.get("NIN"),
                passport=passport,
                identity=identity,
                utility=utility,
                signature=signature,
            )
            response_data = acc_response.json()
            response_code = response_data.get("ResponseCode")

            # Handle different response codes explicitly
            if response_code == "7799":
                logging.error(
                    f"Error {response_code}: {response_data['ResponseDetInfo']}"
                )
                error_message = "The operation has timed out. Please try again later."
                return Response(
                    data={
                        "status": "fail",
                        "error": error_message,
                        "details": response_data["ResponseDetInfo"],
                    },
                    status=status.HTTP_408_REQUEST_TIMEOUT,
                )

            elif acc_response.status_code == 200:
                user_acc = AccountCreation.objects.create(
                    user=user,
                    account_number=acc_response.json()["AccountNUBAN"],
                    customer_numnber=acc_response.json()["CustomerNumber"],
                    acct_name=acc_response.json()["AccountName"],
                    sex=request.data.get("gn"),
                    title=request.data.get("tc"),
                    marital_status=request.data.get("ms"),
                    lga=request.data.get("lga"),
                    state=request.data.get("state"),
                    religion=request.data.get("religion"),
                    nin=request.data.get("NIN"),
                    address=request.data.get("address"),
                )
                UserNotification.objects.create(
                    user=user,
                    title="Virtual Account Creation 🎉",
                    message="Congratulations! 🎊🎉 Your virtual account has been created successfully. 🥳",
                )

                ActivityModel.objects.create(
                    user=admin_user,
                    title="Virtual Account Creation 🎉",
                    description=f"You have successfully created an account for {user.first_name} {user.last_name} 🎊🎉.",
                )

                # Set the value of has_wallet to true.
                user.has_wallet = True
                user.save()

                # Set the value of user's active n account creation.
                user_acc.active_role_on_creation = user.active_role
                user_acc.save()

                resp = {
                    "status": "success",
                    "message": "Open Account Operation was successful!",
                    "accountNumber": acc_response.json()["AccountNUBAN"],
                    "accountName": acc_response.json()["AccountName"],
                    "CustomerNumber": acc_response.json()["CustomerNumber"],
                }
                logging.info(f"Account creation successful for {user.first_name} {user.last_name}")
                return Response(data=resp, status=status.HTTP_201_CREATED)
            else:
                return Response(
                    data=acc_response.json(), status=acc_response.status_code
                )
        except requests.exceptions.RequestException as e:
            logging.error(f"Account creation API request error: {str(e)}")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class WalletSearch(generics.ListAPIView):
    """
    WalletSearch handles the GET request of searching
    for results that matches the query.
    """
    serializer_class = GetAccountSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [
        IsAuthenticated,
        IsNotDisabled,
        IsWalletAdminOrSuperAdmin,
    ]

    def get(self, request):
        keyword = request.query_params.get("account_name", "")

        accounts = AccountCreation.objects.filter(
            Q(acct_name__icontains=keyword)
        )

    # Serialize the results
        serializer = self.get_serializer(accounts, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
