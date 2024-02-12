import requests
from django.db import IntegrityError

# Third party imports.
from rest_framework import generics
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import MultiPartParser, JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from cloudinary import uploader as cloud

# In project imports.
from .serializers import (
    BecomePartnerSerializer,
    PartnerServiceSerializer,
    PartnerProfileSerializer,
    UpdateProfileSerializer,
    VerifyCacSerializers,
    PartnerServicePhotosSerializer,
    PartnerServiceGymPhotosSerializer,
)
from accounts.models import User, AccountType
from .models import (
    PartnerServices,
    PartnerServicePhotos,
    AvailablePartnerGymTrainers,
)
from permissions import IsPartner, IsPartnerAdmin, IsUserOrMember


# Create your views here.
class CreatePartner(generics.GenericAPIView):
    """CreatePartner handles the POST request of creating a partner
    account.
    """

    serializer_class = BecomePartnerSerializer

    def post(self, request):
        user_data = request.data
        authenticated_user = request.user
        
        serializer = self.serializer_class(data=user_data)
        if serializer.is_valid(raise_exception=True):

            serializer.save()
            user_type = AccountType.objects.create(
                user_type="Partners",
            )
            authenticated_user.account_type.add(user_type)

            response = {
                "status": "success",
                "message": "Partner account created successfully.",
                "data": serializer.data,
            }
            return Response(data=response, status=status.HTTP_201_CREATED)
        else:
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ListAllPartners(generics.ListAPIView):
    serializer_class = PartnerProfileSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated & (IsPartner | IsPartnerAdmin)]

    def get_queryset(self):
        partners = User.objects.filter(account_type="Partner")
        return partners

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.serializer_class(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class CreatePartnerService(generics.CreateAPIView):
    """
    API endpoint to create a PartnerService.

    To create a new service, send a POST request with the following parameters:

    - `service_photos`: List of images representing the service.
    - `trainer_photo`: Image of the trainer (required if service is "Gym").
    - `business`: Type of Business.
    - `service`: Type of service.
    - `service_star`: Rating of the service.
    - `price`: Price of the service.
    - `description`: Description of the service.
    - `trainer_name`: Name of the trainer (optional).
    - `trainer_price`: Price of the trainer (optional).

    Example usage:

    ```
    curl -X POST -H "Authorization: Bearer <your_token>" -F "service_photos=@image1.jpg" -F "service_photos=@image2.jpg" -F "trainer_photo=@trainer_image.jpg" -F "business=XYZ" -F "service=Gym" -F "service_star=5" -F "price=100" -F "description=Great service" -F "trainer_name=John Doe" -F "trainer_price=50"
    """

    serializer_class = PartnerServiceSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsPartner)
    parser_classes = (
        MultiPartParser,
        JSONParser,
    )

    def create(self, request):
        serializer = PartnerServiceSerializer(data=request.data)
        if serializer.is_valid(raise_exception=True):
            service_uploads = request.data.getlist("service_photos")
            trainer_uploads = request.data.getlist("trainer_photo")
            image_urls = []
            gym_trainer_img_urls = []

            try:
                serializer.validated_data["user"] = request.user
                partner_service = serializer.save()

                for upload in service_uploads:
                    upload_result = cloud.upload(file=upload)
                    image_url = upload_result["url"]
                    image_urls.append(image_url)

                    PartnerServicePhotos.objects.create(
                        partner=partner_service.user,
                        photo=image_url,
                    )

                if request.data["service"] == "Gym":
                    for photo in trainer_uploads:
                        upload_res = cloud.upload(file=photo)
                        gym_trainer_img_url = upload_res["url"]
                        gym_trainer_img_urls.append(gym_trainer_img_url)

                        AvailablePartnerGymTrainers.objects.create(
                            partner=partner_service.user,
                            trainer_name=request.data["trainer_name"],
                            trainer_price=request.data["trainer_price"],
                            trainer_photo=gym_trainer_img_url,
                        )

                response = {
                    "status": "success",
                    "message": "Service recorded!",
                    "image urls": image_urls,
                    "gym trainers": gym_trainer_img_urls,
                    "data": serializer.data,
                }
                return Response(data=response, status=status.HTTP_201_CREATED)

            except Exception as err:
                return Response(
                    {"error": "An error occurred: {}".format(err)},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PartnerServiceList(generics.ListAPIView):
    """PartnerServiceList lists all the services belonging to
    an authenticated Partner.
    """

    serializer_class = PartnerServiceSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated & (IsPartner | IsUserOrMember | IsPartnerAdmin)]

    def get_queryset(self):
        user = self.request.user
        queryset = PartnerServices.objects.filter(user=user)
        return queryset

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.serializer_class(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class AllPartnersServiceList(generics.ListAPIView):
    """AllPartnersServiceList lists all the services of
    all authenticated Partners.
    """

    serializer_class = PartnerServiceSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated & (IsPartner | IsPartnerAdmin)]

    def list(self, request, *args, **kwargs):
        partners = User.objects.filter(account_type="Partner")
        data = []

        for partner in partners:
            partner_data = {
                "name": partner.business_name,
                "services": PartnerServiceSerializer(
                    PartnerServices.objects.filter(user=partner), many=True
                ).data,
            }
            data.append(partner_data)

            response = {
                "status": "success",
                "status": "All Partners services fetched successfully!",
                "data": data,
            }

        return Response(data=response, status=status.HTTP_200_OK)


class GetPartnerDetails(generics.RetrieveAPIView):
    """GetPartner returns the profile details of a partner user."""

    serializer_class = PartnerProfileSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsPartner)

    def retrieve(self, request, *args, **kwargs):
        user = self.request.user  # Get the authenticated user
        serializer = self.get_serializer(user)
        return Response(serializer.data, status=status.HTTP_200_OK)


class UpdatePartnerProfile(generics.UpdateAPIView):
    """Update User Profile"""

    serializer_class = UpdateProfileSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated & (IsPartner | IsPartnerAdmin)]

    def get_object(self):
        return self.request.user

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(data=serializer.data, status=status.HTTP_200_OK)


class PartnerServicePhotosList(generics.ListAPIView):
    """List view to retrieve all partner service photos."""

    serializer_class = PartnerServicePhotosSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated & (IsPartner | IsPartnerAdmin)]

    def get_queryset(self):
        # Filter partner service photos by the authenticated user
        return PartnerServicePhotos.objects.filter(partner=self.request.user)

    def list(self, request, *args, **kwargs):
        photos = self.get_queryset()
        serializer = self.serializer_class(photos, many=True)
        return Response(data=serializer.data, status=status.HTTP_200_OK)


class PartnerServiceGymTrainersPhotosList(generics.ListAPIView):
    """List view to retrieve all partner gym trainer photos."""

    serializer_class = PartnerServiceGymPhotosSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated & (IsPartner | IsPartnerAdmin)]

    def get_queryset(self):
        # Filter partner service photos by the authenticated user
        return AvailablePartnerGymTrainers.objects.filter(partner=self.request.user)

    def list(self, request, *args, **kwargs):
        photos = self.get_queryset()
        serializer = self.serializer_class(photos, many=True)
        return Response(data=serializer.data, status=status.HTTP_200_OK)


class VerifyCAC(generics.GenericAPIView):
    """
    VerifyCAC is a POST request handler for verifying a
    registered partner business It takes in the business name and
    RC number as payload.
    """

    serializer_class = VerifyCacSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsPartner)

    def post(self, request):
        user = request.data
        current_user = request.user

        user["users"] = current_user.id

        resource = "https://searchapp.cac.gov.ng/searchapp/api/public-search/company-business-name-it"
        payload = {
            "searchTerm": user["cac"],
        }

        serializer = self.serializer_class(data=user)
        if serializer.is_valid(raise_exception=True):
            serializer.save(users=current_user)
            try:
                response = requests.post(
                    url=resource,
                    json=payload,
                )

                if response.status_code == 200:
                    resp = response.json()["data"]
                    for name in resp:
                        business_name = user["business_name"].upper()
                        if business_name == name["approvedName"]:
                            response_data = {
                                "status": "success",
                                "message": "Your business is verified!",
                                "data": response.json(),
                            }
                            return Response(
                                data=response_data, status=status.HTTP_200_OK
                            )
                        else:
                            error_response = {
                                "status": "fail",
                                "message": "The business name provided does not match the RC number!",
                            }
                            return Response(
                                data=error_response, status=status.HTTP_404_NOT_FOUND
                            )
                else:
                    error_response = {
                        "error": "An error occurred!",
                    }
                    return Response(data=error_response, status=response.status_code)
            except requests.exceptions.RequestException as e:
                return Response(
                    {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
