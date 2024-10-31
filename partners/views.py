from decouple import config
from django.template.loader import render_to_string
from commons import Message

# Third party imports.
from rest_framework import generics
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import MultiPartParser, JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.pagination import PageNumberPagination
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
    UpdatePartnerServiceSerializer,
)
from accounts.models import User, AccountType, UserNotification
from roles.models import ActivityModel
from .models import (
    PartnerServices,
    PartnerServicePhotos,
    AvailablePartnerGymTrainers,
)
from .controllers import CAC
from permissions import (
    IsPartner,
    IsPartnerAdmin,
    IsUserOrMember,
    IsOwnerOrReadOnly,
    IsPartnerUserOrMember,
    IsSuperAdmin,
)


picadailys_email = config("EMAIL_HOST_USER")
app_password = config("EMAIL_HOST_PASSWORD")


class PaginationStyle(PageNumberPagination):
    page_size = 20


# Create your views here.
class CreatePartner(generics.GenericAPIView):
    """CreatePartner handles the POST request of creating a partner
    account.
    """

    serializer_class = BecomePartnerSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        user_data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in request.data.items()
        }
        authenticated_user = request.user

        serializer = self.serializer_class(data=user_data)
        if serializer.is_valid(raise_exception=True):
            serializer.save()
            AccountType.objects.create(
                user=authenticated_user,
                user_type="Partner",
            )
            authenticated_user.active_role = "Partner"
            authenticated_user.save()

            UserNotification.objects.create(
                user=authenticated_user,
                title="Partner Registration.",
                message=f"{authenticated_user.first_name} {authenticated_user.last_name} registered as {authenticated_user.business_name}.",
            )

            ActivityModel.objects.create(
                user=authenticated_user,
                title="Partner Registration.",
                description=f"{authenticated_user.first_name} {authenticated_user.last_name} registered as {authenticated_user.business_name}.",
            )

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
    permission_classes = [
        IsAuthenticated & (IsPartnerUserOrMember | IsPartnerAdmin | IsSuperAdmin)
    ]
    pagination_class = PaginationStyle

    def get_queryset(self):
        partners = User.objects.filter(active_role="Partner")
        return partners

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.serializer_class(page, many=True)
            return self.get_paginated_response(serializer.data)

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
    - `from_station`: From_station is the pickup station of courier service.
    - `destination`: Destination of the pickup station.
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
            current_user = {
                key: value.strip() if isinstance(value, str) else value
                for key, value in request.data.items()
            }
            if current_user.business_verified is True:
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

                    if request.data["service"] == "Fitness and Entertainment":
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

                    if request.data["service"] == "Courier Services":
                        PartnerServices.objects.cretae(
                            user=request.user,
                            business=request.data["business"],
                            service=request.data["service"],
                            service_star=request.data["service_star"],
                            price=request.data["price"],
                            description=request.data["description"],
                            from_station=request.data["from_station"],
                            destination=-request.data["destination"],
                        )

                    response = {
                        "status": "success",
                        "message": "Service recorded!",
                        "image urls": image_urls,
                        "gym trainers": gym_trainer_img_urls,
                        "data": serializer.data,
                    }

                    UserNotification.objects.create(
                        user=current_user,
                        title="Partner Service.",
                        message="You have successfully created a service.",
                    )

                    ActivityModel.objects.create(
                        user=current_user,
                        title="Partner Service.",
                        description=f"{current_user.first_name} {current_user.last_name} has created a service: {partner_service.business_name}.",
                    )

                    return Response(data=response, status=status.HTTP_201_CREATED)

                except Exception as err:
                    return Response(
                        {"error": "An error occurred: {}".format(err)},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    )
            else:
                response = {
                    "status": "fail",
                    "message": "Sorry, you have to validate your business before you can create a service!",
                }
                return Response(data=response, status=status.HTTP_201_CREATED)

        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UpdatePartnerService(generics.UpdateAPIView):
    """
    API endpoint to update a PartnerService.

    To update a service, send a PUT request with the service ID and the updated data in the request body.

    **Parameters:**

    - `service_id`: ID of the service to update (required for PUT requests).
    - `service_photos`: List of new images to upload (optional).
    - `trainer_photo`: New image for the trainer (optional, only applicable for "Gym" services).
    - Any other fields you want to update (e.g., `business`, `service`, `price`, etc.).

    **Example usage (PUT):**

    ```
    curl -X PUT -H "Authorization: Bearer <your_token>" -F "service_id=1" -F "service_photos=@image3.jpg" -F "price=120"
    ```
    """

    serializer_class = UpdatePartnerServiceSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsPartner)
    parser_classes = (
        MultiPartParser,
        JSONParser,
    )

    def update(self, request, *args, **kwargs):
        payload = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in request.data.items()
        }
        partner_service = self.get_object()
        serializer = self.get_serializer(partner_service, data=payload, partial=True)
        if serializer.is_valid(raise_exception=True):
            service_uploads = request.data.getlist("service_photos")
            trainer_uploads = request.data.getlist("trainer_photo")
            image_urls = []
            gym_trainer_img_urls = []

            try:
                serializer.save()  # Update basic partner service details

                # Update service photos
                for upload in service_uploads:
                    upload_result = cloud.upload(file=upload)
                    image_url = upload_result["url"]
                    image_urls.append(image_url)

                    # Create new PartnerServicePhotos objects
                    PartnerServicePhotos.objects.create(
                        partner=partner_service.user,
                        photo=image_url,
                    )

                # Update trainer details (if applicable)
                if request.data.get("service") == "Gym" and trainer_uploads:
                    for photo in trainer_uploads:
                        upload_res = cloud.upload(file=photo)
                        gym_trainer_img_url = upload_res["url"]
                        gym_trainer_img_urls.append(gym_trainer_img_url)

                        # Update existing AvailablePartnerGymTrainers objects or create new ones
                        AvailablePartnerGymTrainers.objects.update(
                            partner=partner_service.user,
                            defaults={
                                "trainer_name": request.data.get("trainer_name"),
                                "trainer_price": request.data.get("trainer_price"),
                                "trainer_photo": gym_trainer_img_url,
                            },
                        )

                    current_user = request.user
                    UserNotification.objects.create(
                        user=current_user,
                        title="Partner Service.",
                        message="You have successfully updated their service.",
                    )

                    ActivityModel.objects.create(
                        user=current_user,
                        title="Partner Service.",
                        description=f"{current_user.first_name} {current_user.last_name} has successfully updated their service: {partner_service.business_name}.",
                    )

                response = {
                    "status": "success",
                    "message": "Service updated!",
                    "image urls": image_urls,
                    "gym trainers": gym_trainer_img_urls,
                    "data": serializer.data,
                }
                return Response(data=response, status=status.HTTP_200_OK)

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
    permission_classes = [
        IsAuthenticated & (IsPartner | IsUserOrMember | IsPartnerAdmin)
    ]
    pagination_class = PaginationStyle

    def get_queryset(self):
        user = self.request.user
        queryset = PartnerServices.objects.filter(user=user)
        return queryset

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.serializer_class(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.serializer_class(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class DeletePartnerService(generics.DestroyAPIView):
    """
    DeletePartnerService is the DELETE request handler that allows a
    partner to delete their service.
    """

    queryset = PartnerServices.objects.all()
    serializer_class = PartnerServiceSerializer
    permission_classes = [IsAuthenticated, IsOwnerOrReadOnly]
    authentication_classes = [JWTAuthentication]

    def destroy(self, request, *args, **kwargs):
        try:
            service = self.get_object()

            if service.user == request.user:
                current_user = request.user
                UserNotification.objects.create(
                    user=current_user,
                    title="Partner Service.",
                    message=f"You have successfully deleted your service: {service.business}.",
                )

                ActivityModel.objects.create(
                    user=current_user,
                    title="Partner Service.",
                    description=f"{current_user.first_name} {current_user.last_name} has successfully updated their service: {service.business}.",
                )
                service.delete()
                return Response(
                    {"status": "Service deleted."},
                    status=status.HTTP_204_NO_CONTENT,
                )

            else:
                return Response(
                    {"detail": "You can only delete a service you uploaded."},
                    status=status.HTTP_403_FORBIDDEN,
                )

        except PartnerServices.DoesNotExist:
            return Response(
                {"detail": "Service not found."},
                status=status.HTTP_404_NOT_FOUND,
            )


class AllPartnersServiceList(generics.ListAPIView):
    serializer_class = PartnerServiceSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = permission_classes = [
        IsAuthenticated & (IsPartnerUserOrMember | IsPartnerAdmin)
    ]
    pagination_class = PaginationStyle

    def get_queryset(self):
        """
        Retrieves all Partner users.
        """
        return User.objects.filter(active_role="Partner").order_by("created_at")

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        data = []

        if page is not None:
            # Apply pagination
            for partner in page:
                partner_data = {
                    "name": partner.business_name,
                    "services": PartnerServiceSerializer(
                        PartnerServices.objects.filter(user=partner), many=True
                    ).data,
                }
                data.append(partner_data)
            serialized_data = self.get_paginated_response(data)
        else:
            # No pagination applied (small result set or no limit/offset provided)
            for partner in queryset:
                partner_data = {
                    "name": partner.business_name,
                    "services": PartnerServiceSerializer(
                        PartnerServices.objects.filter(user=partner), many=True
                    ).data,
                }
                data.append(partner_data)
            serialized_data = Response(data, status=status.HTTP_200_OK)

        # Update response structure to include pagination information (if applicable)
        response = {
            "status": "success",
            "message": "All Partners services fetched successfully!",
            "data": (
                serialized_data.data
                if hasattr(serialized_data, "data")
                else serialized_data.content
            ),  # Handle both paginated and non-paginated responses
        }
        if hasattr(
            serialized_data, "pagination"
        ):  # Add pagination details if available
            response.update(serialized_data.pagination)

        return Response(response, status=status.HTTP_200_OK)


class GetPartnerDetails(generics.RetrieveAPIView):
    """GetPartnerDetails returns the profile details of a partner user."""

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
        payload = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in request.data.items()
        }
        current_user = request.user

        serializer = self.serializer_class(data=payload)
        if serializer.is_valid(raise_exception=True):
            serializer.save()
            rc_number = serializer.validated_data.get("rc_number")
            business = serializer.validated_data.get("business_name")
            verify_cac_response = CAC.verify(
                rc_number=rc_number, business_name=business
            )
            if verify_cac_response.status_code == 200:
                resp = verify_cac_response.json()["entity"]
                business_name = payload["business_name"].upper()
                if business_name == resp["company_name"]:
                    response_data = {
                        "status": "success",
                        "message": "Your business is verified!",
                        "data": verify_cac_response.json(),
                    }
                    # Assign true to current user.
                    current_user.business_verified = True
                    current_user.save()

                    UserNotification.objects.create(
                        user=request.user,
                        title="Business Verification.",
                        message="This is to inform you that the verification of your business is successful.",
                    )

                    ActivityModel.objects.create(
                        user=current_user,
                        title="Business Verification.",
                        description=f"{current_user.first_name} {current_user.last_name} has successfully verified their business: {current_user.business}.",
                    )

                    # send transactional email.
                    body = "This is to inform you that the verification of your business on Picadailys is successful."

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
                        email=request.user.email,
                        subject="Profile Update.",
                    )

                    return Response(data=response_data, status=status.HTTP_200_OK)
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
                    "status": "fail",
                    "error": "An error occurred!",
                    "data": verify_cac_response.json(),
                }
                return Response(
                    data=error_response, status=verify_cac_response.status_code
                )
        else:
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)
