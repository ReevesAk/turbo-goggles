import logging
from django.db import transaction
from django.db.models import Prefetch
from decouple import config
from django.http import Http404

# Third party imports.
from rest_framework import generics, views
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
    VerifyCAC,
)
from .controllers import CAC
from permissions import (
    IsPartner,
    IsPartnerAdmin,
    IsOwnerOrReadOnly,
    IsPartnerUserOrMember,
    IsSuperAdmin,
)
from security import encrypt, decrypt


picadailys_email = config("EMAIL_HOST_USER")
app_password = config("EMAIL_HOST_PASSWORD")


class PaginationStyle(PageNumberPagination):
    page_size = 20


logger = logging.getLogger(__name__)


# Create your views here.
class CreatePartner(generics.GenericAPIView):
    """CreatePartner handles the POST request of creating a partner
    account.
    """

    serializer_class = BecomePartnerSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        logger.info("Partner registration POST method called by user %s", request.user)

        decrypted_payload = decrypt(request.data)
        user_data = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_payload.items()
        }
        authenticated_user = request.user
        logger.debug("User data received: %s", user_data)

        serializer = self.serializer_class(data=user_data)

        if serializer.is_valid(raise_exception=True):
            try:
                with transaction.atomic():
                    logger.info("Saving user data for %s", authenticated_user)

                    # Save the user data
                    serializer.save()
                    logger.info("User data saved successfully.")

                    # Assign the "Partner" role
                    AccountType.objects.create(
                        user=authenticated_user,
                        user_type="Partner",  # Consider using a constant for "Partner"
                    )
                    authenticated_user.active_role = "Partner"
                    authenticated_user.save()
                    logger.info(
                        "User role updated to Partner for %s", authenticated_user
                    )

                    # Create notifications and log activities
                    UserNotification.objects.create(
                        user=authenticated_user,
                        title="Partner Registration.",
                        message=(
                            f"{authenticated_user.first_name} {authenticated_user.last_name} "
                            f"registered as {authenticated_user.business_name}."
                        ),
                    )
                    logger.debug("User notification created for %s", authenticated_user)

                    ActivityModel.objects.create(
                        user=authenticated_user,
                        title="Partner Registration.",
                        description=(
                            f"{authenticated_user.first_name} {authenticated_user.last_name} "
                            f"registered as {authenticated_user.business_name}."
                        ),
                    )
                    logger.debug("Activity log created for %s", authenticated_user)

                    response = {
                        "status": "success",
                        "message": "Partner account created successfully.",
                        "data": serializer.data,
                    }
                    logger.info(
                        "Partner registration successful for %s", authenticated_user
                    )
                    return Response(data=encrypt(response), status=status.HTTP_201_CREATED)

            except Exception as e:
                logger.error(
                    "Error during partner registration: %s", str(e), exc_info=True
                )
                return Response(
                    data=encrypt({
                        "status": "error",
                        "message": "An error occurred during registration.",
                    }),
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        logger.warning(
            "Invalid data received for partner registration: %s", serializer.errors
        )
        return Response(data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST)


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
        return Response(encrypt(serializer.data), status=status.HTTP_200_OK)


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
        logger.info("Partner service creation requested by user: %s", request.user)

        serializer = PartnerServiceSerializer(data=request.data)

        if serializer.is_valid(raise_exception=True):
            decrypted_payload = decrypt(request.data)
            cleaned_data = {
                key: value.strip() if isinstance(value, str) else value
                for key, value in decrypted_payload.items()
            }

            current_user = request.user
            if not current_user.business_verified:
                logger.warning(
                    "User %s attempted to create a service without a verified business.",
                    current_user,
                )
                return Response(
                    data=encrypt({
                        "status": "fail",
                        "message": "Sorry, you have to validate your business before you can create a service!",
                    }),
                    status=status.HTTP_403_FORBIDDEN,
                )

            service_uploads = request.data.getlist("service_photos")
            trainer_uploads = request.data.getlist("trainer_photo")
            image_urls = []
            gym_trainer_img_urls = []

            try:
                # Save the PartnerServices instance
                serializer.validated_data["user"] = current_user
                partner_service = serializer.save()
                logger.info("Partner service created successfully: %s", partner_service)

                # Handle service photos upload
                image_urls = self.upload_service_photos(
                    service_uploads, partner_service
                )
                logger.info("Uploaded service photos: %s", image_urls)

                # Handle trainer photos if applicable
                if cleaned_data.get("service") == "Fitness and Entertainment":
                    gym_trainer_img_urls = self.upload_trainer_photos(
                        trainer_uploads, partner_service, cleaned_data
                    )
                    logger.info("Uploaded gym trainer photos: %s", gym_trainer_img_urls)

                # Handle Courier Services if applicable
                if cleaned_data.get("service") == "Courier Services":
                    self.create_courier_service(cleaned_data, current_user)
                    logger.info("Courier service created by user: %s", current_user)

                # Create notifications and activity log
                self.create_notifications(current_user, partner_service)
                logger.info(
                    "Notifications and activity logs created for user: %s", current_user
                )

                response = {
                    "status": "success",
                    "message": "Service recorded!",
                    "image_urls": image_urls,
                    "gym_trainers": gym_trainer_img_urls,
                    "data": serializer.data,
                }
                logger.info("Service creation successful. Response: %s", response)

                return Response(data=encrypt(response), status=status.HTTP_201_CREATED)

            except Exception as err:
                logger.error(
                    "Error during service creation for user %s: %s",
                    current_user,
                    str(err),
                    exc_info=True,
                )
                return Response(
                    data=encrypt({"error": f"An error occurred: {str(err)}"}),
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

    def upload_service_photos(self, uploads, partner_service):
        logger.info("Uploading service photos for partner service: %s", partner_service)
        image_urls = []
        for upload in uploads:
            upload_result = cloud.upload(file=upload)
            image_url = upload_result["url"]
            image_urls.append(image_url)
            logger.debug("Uploaded photo: %s", image_url)

            # Associate the uploaded photo with the PartnerServices instance
            PartnerServicePhotos.objects.create(
                partner=partner_service,  # Use the PartnerServices instance
                photo=image_url,
            )
        return image_urls

    def upload_trainer_photos(self, uploads, partner_service, cleaned_data):
        logger.info("Uploading trainer photos for partner service: %s", partner_service)
        gym_trainer_img_urls = []
        for photo in uploads:
            upload_res = cloud.upload(file=photo)
            gym_trainer_img_url = upload_res["url"]
            gym_trainer_img_urls.append(gym_trainer_img_url)
            logger.debug("Uploaded trainer photo: %s", gym_trainer_img_url)

            AvailablePartnerGymTrainers.objects.create(
                partner=partner_service.user,
                trainer_name=cleaned_data["trainer_name"],
                trainer_price=cleaned_data["trainer_price"],
                trainer_photo=gym_trainer_img_url,
            )
        return gym_trainer_img_urls

    def create_courier_service(self, cleaned_data, current_user):
        logger.info("Creating courier service for user: %s", current_user)
        PartnerServices.objects.create(
            user=current_user,
            business=cleaned_data["business"],
            service=cleaned_data["service"],
            service_star=cleaned_data["service_star"],
            price=cleaned_data["price"],
            description=cleaned_data["description"],
            from_station=cleaned_data["from_station"],
            destination=cleaned_data["destination"],
        )

    def create_notifications(self, current_user, partner_service):
        logger.info(
            "Creating notifications and activity logs for user: %s", current_user
        )
        UserNotification.objects.create(
            user=current_user,
            title="Partner Service.",
            message="You have successfully created a service.",
        )

        ActivityModel.objects.create(
            user=current_user,
            title="Partner Service.",
            description=f"{current_user.first_name} {current_user.last_name} has created a service: {partner_service.business}.",
        )


class UpdatePartnerService(generics.UpdateAPIView):
    """
    API endpoint to update a PartnerService.

    To update a service, send a PUT request with the service ID and the updated data in the request body.

    **Parameters:**

    - `service_id`: ID of the service to update (required for PUT requests).
    - `service_photos`: List of new images to upload (optional).
    - `trainer_photo`: New image for the trainer (optional, only applicable for "Gym" services).
    - Any other fields you want to update (e.g., `service_star`, `price`, etc.).

    **Example usage (PUT):**

    ```
    curl -X PUT -H "Authorization: Bearer <your_token>" -F "service_id=1" -F "service_photos=@image3.jpg" -F "price=120"
    ```
    """

    serializer_class = UpdatePartnerServiceSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)
    parser_classes = (
        MultiPartParser,
        JSONParser,
    )
    queryset = PartnerServices.objects.all()

    def get_object(self, service_id):
        try:
            service = PartnerServices.objects.get(id=service_id)
            logger.info("Retrieved partner service with ID: %s", service_id)
            return service
        except PartnerServices.DoesNotExist:
            logger.warning("Partner service with ID %s not found.", service_id)
            raise Http404("Partner service not found.")

    def update(self, request, service_id, *args, **kwargs):
        logger.info(
            "Update request received for service ID: %s by user: %s",
            service_id,
            request.user,
        )

        partner_service = self.get_object(service_id)
        decrypted_payload = decrypt(request.data)
        payload = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_payload.items()
        }
        logger.debug("Payload after cleaning: %s", payload)

        serializer = self.get_serializer(partner_service, data=payload, partial=True)

        if serializer.is_valid(raise_exception=True):
            service_uploads = request.data.getlist("service_photos")
            trainer_uploads = request.data.getlist("trainer_photo")
            image_urls = []
            gym_trainer_img_urls = []

            try:
                # Save the updated partner service details
                serializer.save()
                logger.info("Partner service with ID %s successfully updated.", service_id)

                # Update service photos
                for upload in service_uploads:
                    upload_result = cloud.upload(file=upload)
                    image_url = upload_result["url"]
                    image_urls.append(image_url)
                    logger.debug("Uploaded service photo URL: %s", image_url)

                    # Create new PartnerServicePhotos objects
                    PartnerServicePhotos.objects.create(
                        partner=partner_service,
                        photo=image_url,
                    )
                logger.info("Service photos updated for service ID %s.", service_id)

                # Update trainer details (if applicable)
                if request.data.get("service") == "Gym" and trainer_uploads:
                    for photo in trainer_uploads:
                        upload_res = cloud.upload(file=photo)
                        gym_trainer_img_url = upload_res["url"]
                        gym_trainer_img_urls.append(gym_trainer_img_url)
                        logger.debug("Uploaded trainer photo URL: %s", gym_trainer_img_url)

                        # Update or create AvailablePartnerGymTrainers objects
                        AvailablePartnerGymTrainers.objects.update_or_create(
                            partner=partner_service.user,
                            defaults={
                                "trainer_name": request.data.get("trainer_name"),
                                "trainer_price": request.data.get("trainer_price"),
                                "trainer_photo": gym_trainer_img_url,
                            },
                        )
                    logger.info("Trainer details updated for service ID %s.", service_id)

                # Log notifications and activity
                current_user = request.user
                UserNotification.objects.create(
                    user=current_user,
                    title="Partner Service.",
                    message="You have successfully updated your service.",
                )
                logger.info("Notification created for user: %s", current_user)

                ActivityModel.objects.create(
                    user=current_user,
                    title="Partner Service.",
                    description=f"{current_user.first_name} {current_user.last_name} has successfully updated their service: {partner_service.business}.",
                )
                logger.info("Activity log created for user: %s", current_user)

                response = {
                    "status": "success",
                    "message": "Service updated!",
                    "image_urls": image_urls,
                    "gym_trainers": gym_trainer_img_urls,
                    "data": serializer.data,
                }
                logger.info(
                    "Update response prepared for service ID %s: %s", service_id, response
                )

                return Response(data=encrypt(response), status=status.HTTP_200_OK)

            except Exception as err:
                logger.error(
                    "Error during update of service ID %s by user %s: %s",
                    service_id,
                    request.user,
                    str(err),
                    exc_info=True,
                )
                return Response(
                    {"error": f"An error occurred: {str(err)}"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
        else:
            logger.warning(
                "Validation failed for service ID %s. Errors: %s",
                service_id,
                serializer.errors,
            )
            return Response(data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST)


class PartnerServiceList(generics.ListAPIView):
    """PartnerServiceList lists all the services belonging to
    an authenticated Partner.
    """

    serializer_class = PartnerServiceSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    pagination_class = PaginationStyle

    def get_queryset(self):
        user = self.request.user
        logger.info(f"Fetching services for user: {user.id} ({user.first_name} {user.last_name})")
        # Use prefetch_related to optimize queries
        return PartnerServices.objects.filter(user=user).prefetch_related(
            Prefetch(
                "service_photos",
                queryset=PartnerServicePhotos.objects.all(),
                to_attr="photos",  # Store prefetched results in 'photos'
            )
        )

    def list(self, request, *args, **kwargs):
        logger.info("List method called to fetch partner services.")
        try:
            queryset = self.get_queryset()
            page = self.paginate_queryset(queryset)

            def get_service_data(services):
                services_data = []
                for service in services:
                    # Use prefetched 'photos' instead of querying again
                    photos_urls = [photo.photo for photo in service.photos]

                    # Serialize the service data
                    service_data = self.serializer_class(service).data
                    service_data["images"] = photos_urls  # Include photo URLs

                    services_data.append(service_data)
                return services_data

            if page is not None:
                logger.info(f"Paginated data fetched with {len(page)} records.")
                services_data = get_service_data(page)
                resp = {
                    "status": "success",
                    "message": "All services fetched.",
                    "data": services_data,
                }
                encrypted_resp = encrypt(resp)
                return self.get_paginated_response(encrypted_resp)

            # For non-paginated responses
            logger.info(
                f"Fetched all services without pagination. Total: {len(queryset)}"
            )
            services_data = get_service_data(queryset)
            resp = {
                "status": "success",
                "message": "All services fetched.",
                "data": services_data,
            }
            return Response(data=encrypt(resp), status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(
                f"Error occurred while fetching partner services: {str(e)}",
                exc_info=True,
            )
            return Response(
                data=encrypt({
                    "status": "error",
                    "message": "An error occurred while fetching services.",
                }),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class PartnerServiceDetailView(views.APIView):
    """PartnerServiceDetailView is the GET request handler to get the details of a single
    service of any authenticated Partner.
    """

    serializer_class = PartnerServiceSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get_object(self, service_id):
        try:
            return PartnerServices.objects.get(id=service_id)
        except PartnerServices.DoesNotExist:
            raise Http404("Partner service not found.")

    def get(self, request, service_id, *args, **kwargs):
        partner_service = self.get_object(service_id)

        # Get all photos associated with the service
        photos = PartnerServicePhotos.objects.filter(partner=partner_service)
        photos_urls = [photo.photo for photo in photos]

        # Serialize the service data
        service_data = self.serializer_class(partner_service).data
        service_data["images"] = photos_urls  # Add images to the service data

        return Response(
            data=encrypt({
                "status": "success",
                "message": "Service details fetched.",
                "data": service_data,
            }),
            status=status.HTTP_200_OK,
        )


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
            current_user = request.user

            if service.user == current_user:
                # Log the service deletion request
                logger.info(
                    f"User {current_user.id} ({user.first_name} {user.last_name}) is attempting to delete service {service.id} ({service.business})."
                )

                # Create a user notification
                UserNotification.objects.create(
                    user=current_user,
                    title="Partner Service.",
                    message=f"You have successfully deleted your service: {service.business}.",
                )

                # Log the notification creation
                logger.info(
                    f"Notification created for user {current_user.id} about service deletion."
                )

                # Create an activity log
                ActivityModel.objects.create(
                    user=current_user,
                    title="Partner Service.",
                    description=f"{current_user.first_name} {current_user.last_name} has successfully deleted their service: {service.business}.",
                )

                # Log the activity creation
                logger.info(
                    f"Activity log created for user {current_user.id} about service deletion."
                )

                # Delete the service
                service.delete()

                # Log successful deletion
                logger.info(
                    f"Service {service.id} ({service.business}) successfully deleted by user {current_user.id}."
                )

                return Response(
                    data=encrypt({"status": "Service deleted."}),
                    status=status.HTTP_204_NO_CONTENT,
                )
            else:
                # Log unauthorized delete attempt
                logger.warning(
                    f"Unauthorized deletion attempt: User {current_user.id} ({user.first_name} {user.last_name}) tried to delete service {service.id} ({service.business}) owned by another user."
                )
                return Response(
                    data=encrypt({"detail": "You can only delete a service you uploaded."}),
                    status=status.HTTP_403_FORBIDDEN,
                )

        except PartnerServices.DoesNotExist:
            # Log service not found error
            logger.error(
                f"Service not found. User {request.user.id} ({request.user.first_name} {request.user.last_name}) attempted to delete a non-existent service."
            )
            return Response(
                data=encrypt({"detail": "Service not found."}),
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as e:
            # Log unexpected exceptions
            logger.exception(
                f"An unexpected error occurred while deleting a service for user {request.user.id} ({request.user.first_name} {request.user.last_name}): {str(e)}"
            )
            return Response(
                data=encrypt({"detail": "An unexpected error occurred. Please try again later."}),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class AllPartnersServiceList(generics.ListAPIView):
    serializer_class = PartnerServiceSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = permission_classes = [
        IsAuthenticated & (IsPartnerUserOrMember | IsPartnerAdmin)
    ]
    pagination_class = PaginationStyle

    def get_queryset(self, business=None):
        """
        Retrieves all Partner services filtered by business name if provided.
        """
        queryset = PartnerServices.objects.all()

        if business:
            queryset = queryset.filter(business=business)

        return queryset.order_by("created_at")

    def list(self, request, *args, **kwargs):
        business = kwargs.get("business")

        queryset = self.get_queryset(business=business)

        # Prepare the response data
        response_data = []
        for service in queryset:
            # Serialize the service data
            service_data = PartnerServiceSerializer(service).data

            # Get all photos associated with the service
            photos = PartnerServicePhotos.objects.filter(partner=service)
            photos_urls = [photo.photo for photo in photos]

            # Add images to the service data
            service_data["images"] = photos_urls

            # Append the modified service data to the response list
            response_data.append(service_data)

        response = {
            "status": "success",
            "message": "Partner services fetched successfully!",
            "data": response_data,
        }

        return Response(data=encrypt(response), status=status.HTTP_200_OK)


class GetPartnerDetails(generics.RetrieveAPIView):
    """GetPartnerDetails returns the profile details of a partner user."""

    serializer_class = PartnerProfileSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsPartner)

    def retrieve(self, request, *args, **kwargs):
        user = self.request.user  # Get the authenticated user
        serializer = self.get_serializer(user)
        return Response(data=encrypt(serializer.data), status=status.HTTP_200_OK)


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
        return Response(data=encrypt(serializer.data), status=status.HTTP_200_OK)


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
        return Response(data=encrypt(serializer.data), status=status.HTTP_200_OK)


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
        return Response(data=encrypt(serializer.data), status=status.HTTP_200_OK)


class VerifyCACView(generics.GenericAPIView):
    """
    VerifyCACView is a POST request handler for verifying a
    registered partner business It takes in the business name and
    RC number as payload.
    """

    serializer_class = VerifyCacSerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, IsPartner)

    def post(self, request):
        try:
            decrypted_payload = decrypt(request.data)
            payload = {
                key: value.strip() if isinstance(value, str) else value
                for key, value in decrypted_payload.items()
            }
            current_user = request.user

            logger.info(
                f"User {current_user.id} ({current_user.first_name} {current_user.last_name}) initiated a business verification request."
            )

            serializer = self.serializer_class(data=payload)
            if serializer.is_valid(raise_exception=True):
                serializer.save()

                rc_number = serializer.validated_data.get("rc_number")
                business = serializer.validated_data.get("business_name")
                logger.info(
                    f"Serialized data saved. RC Number: {rc_number}, Business Name: {business}."
                )

                verify_cac_response = CAC.verify(
                    rc_number=rc_number, business_name=business
                )
                logger.info(
                    f"CAC verification response received. Status Code: {verify_cac_response.status_code}."
                )

                if verify_cac_response.status_code == 200:
                    resp = verify_cac_response.json()["entity"]

                    # Normalize and compare business names
                    submitted_business_name = "".join(business.split()).upper()
                    verified_business_name = "".join(
                        resp["company_name"].split()
                    ).upper()

                    if submitted_business_name == verified_business_name:
                        logger.info(
                            f"Business name verification succeeded for user {current_user.id}."
                        )

                        # Update user details
                        current_user.business_verified = True
                        current_user.is_cac_approved = True
                        current_user.save()
                        logger.info(
                            f"User {current_user.id}'s business verification status updated."
                        )

                        # Create VerifyCAC entry
                        VerifyCAC.objects.create(
                            users=current_user,
                            rc_number=rc_number,
                            business_name=verified_business_name,
                        )
                        logger.info(
                            f"VerifyCAC entry created for user {current_user.id}."
                        )

                        # Create UserNotification and ActivityModel entries
                        UserNotification.objects.create(
                            user=request.user,
                            title="Business Verification",
                            message="This is to inform you that your business verification was successful.",
                        )
                        logger.info(f"Notification created for user {current_user.id}.")

                        ActivityModel.objects.create(
                            user=current_user,
                            title="Business Verification",
                            description=f"{current_user.first_name} {current_user.last_name} has successfully verified their business: {verified_business_name}.",
                        )
                        logger.info(f"Activity log created for user {current_user.id}.")

                        response_data = {
                            "status": "success",
                            "message": "Your business is verified!",
                            "data": resp,
                        }
                        return Response(data=encrypt(response_data), status=status.HTTP_200_OK)
                    else:
                        logger.warning(
                            f"Business name mismatch for user {current_user.id}. Provided: {submitted_business_name}, Verified: {verified_business_name}."
                        )
                        error_response = {
                            "status": "fail",
                            "message": "The business name provided does not match the RC number!",
                        }
                        return Response(
                            data=encrypt(error_response), status=status.HTTP_404_NOT_FOUND
                        )
                else:
                    error_details = verify_cac_response.json().get(
                        "message", "Unknown error"
                    )
                    logger.error(
                        f"CAC verification failed for user {current_user.id}. Details: {error_details}"
                    )
                    error_response = {
                        "status": "fail",
                        "error": "An error occurred while verifying with CAC",
                        "details": error_details,
                    }
                    return Response(
                        data=encrypt(error_response), status=verify_cac_response.status_code
                    )

            logger.error(
                f"Serializer validation failed for user {current_user.id}. Errors: {serializer.errors}"
            )
            return Response(data=encrypt(serializer.errors), status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            logger.exception(
                f"An unexpected error occurred during business verification for user {request.user.id} ({request.user.first_name} {request.user.last_name}): {str(e)}"
            )
            return Response(
                data=encrypt({"status": "fail", "message": "An unexpected error occurred."}),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
