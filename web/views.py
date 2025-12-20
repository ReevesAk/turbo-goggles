import logging

from django.shortcuts import get_object_or_404
from django.contrib.auth.hashers import check_password

from .models import Applications, JobModel, NewsletterSubscribers

# In project imports.
from .serializers import (
    ApplicationsSerializers,
    GetApplicationsSerializers,
    JobSerializer,
    NewsletterSubscribersSerializer
)

# Third party imports.
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.parsers import MultiPartParser, JSONParser
from rest_framework.pagination import PageNumberPagination

from cloudinary import uploader as cloud
from security import encrypt, decrypt

from permissions import (
    IsAdmin,
)


class CustomPageNumberPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100


logger = logging.getLogger(__name__)


class CreateJob(generics.CreateAPIView):
    serializer_class = JobSerializer
    permission_classes = [IsAuthenticated, IsAdmin]
    authentication_classes = [JWTAuthentication]

    def post(self, request):
        decrypted_payload = decrypt(request.data)

        payload = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_payload.items()
        }

        current_user = request.user
        pin = payload.get("pin")

        if not check_password(pin, current_user.admin_pin):
            return Response(
                encrypt({"status": "fail", "message": "Incorrect pin."}),
                status=status.HTTP_400_BAD_REQUEST,
            )

        if JobModel.objects.filter(title=payload.get("title")).exists():
            return Response(
                encrypt({
                    "status": "fail",
                    "message": "This job posting already exists.",
                }),
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = self.serializer_class(data=payload)
        serializer.is_valid(raise_exception=True)
        serializer.validated_data.pop("pin", None)

        job = serializer.save()

        return Response(
            encrypt({
                "status": "success",
                "message": "Job Created!",
                "data": {
                    "id": job.id,
                    "title": job.title,
                    "location": job.location,
                    "salary": str(job.salary),
                    "is_active": job.is_active,
                },
            }),
            status=status.HTTP_201_CREATED,
        )


class JobList(generics.ListAPIView):
    """
    List all job postings.
    """

    queryset = JobModel.objects.all().order_by("-created_at")
    serializer_class = JobSerializer
    permission_classes = ()
    pagination_class = CustomPageNumberPagination

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        paginator = self.pagination_class()
        paginated_qs = paginator.paginate_queryset(queryset, request)
        serializer = self.get_serializer(paginated_qs, many=True)

        response = {
            "status": "success",
            "message": "Jobs retrieved successfully",
            "data": serializer.data,
        }

        return Response(response, status=status.HTTP_200_OK)


class JobDetail(generics.RetrieveAPIView):
    serializer_class = JobSerializer
    queryset = JobModel.objects.all()
    permission_classes = ()
    lookup_field = "id"

    def retrieve(self, request, *args, **kwargs):
        job = self.get_object()
        response = {
            "status": "success",
            "message": "Job details retrieved",
            "data": JobSerializer(job).data,
        }
        return Response(response, status=status.HTTP_200_OK)


class UpdateJob(generics.UpdateAPIView):
    serializer_class = JobSerializer
    queryset = JobModel.objects.all()
    permission_classes = [IsAuthenticated, IsAdmin]
    lookup_field = "id"

    def update(self, request, *args, **kwargs):
        job = self.get_object()
        decrypted_payload = decrypt(request.data)

        serializer = self.get_serializer(job, data=decrypted_payload, partial=True)
        current_user = request.user
        pin = decrypted_payload.get("pin")
        if not check_password(password=pin, encoded=current_user.admin_pin):
            return Response(
                data=encrypt({
                    "status": "fail",
                    "message": "Incorrect pin.",
                }),
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer.is_valid(raise_exception=True)
        serializer.save()

        response = {
            "status": "success",
            "message": "Job updated successfully",
            "data": serializer.data,
        }
        return Response(
            encrypt(response), status=status.HTTP_200_OK
        )


class DeleteJob(generics.DestroyAPIView):
    queryset = JobModel.objects.all()
    permission_classes = [IsAuthenticated, IsAdmin]
    lookup_field = "id"

    def destroy(self, request, *args, **kwargs):
        job = self.get_object()
        current_user = request.user

        # Decrypt payload to get admin pin
        decrypted_payload = decrypt(request.data)
        pin = decrypted_payload.get("pin")

        if not pin or not check_password(password=pin, encoded=current_user.admin_pin):
            return Response(
                data=encrypt({
                    "status": "fail",
                    "message": "Incorrect pin."
                }),
                status=status.HTTP_400_BAD_REQUEST,
            )

        job.delete()

        response = {
            "status": "success",
            "message": "Job deleted successfully"
        }

        return Response(
            data=encrypt(response),
            status=status.HTTP_200_OK
        )


class SubmitJobApplication(generics.CreateAPIView):
    """
    SubmitJobApplication handles the POST request of job applications to Picadailys.
    """

    serializer_class = ApplicationsSerializers
    permission_classes = (AllowAny,)
    parser_classes = (
        MultiPartParser,
        JSONParser,
    )

    def post(self, request, *args, **kwargs):
        job_id = kwargs.get("job_id")

        if not job_id:
            return Response(
                {
                    "status": "fail",
                    "message": "job_id is required in the URL params."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            job = JobModel.objects.get(id=job_id)
        except JobModel.DoesNotExist:
            return Response(
                {
                    "status": "fail",
                    "message": "Invalid job ID."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = ApplicationsSerializers(data=request.data)
        serializer.is_valid(raise_exception=True)

        cv_upload = request.data.get("cv")
        upload_cv = cloud.upload(cv_upload)
        cv_url = upload_cv["url"]

        # Prevent duplicate application per job
        if Applications.objects.filter(
            email=request.data.get("email"),
            job=job
        ).exists():
            return Response(
                {
                    "status": "fail",
                    "message": "You have already applied for this job."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        application = Applications.objects.create(
            job=job,
            job_title=job.title,   # ✅ from DB
            first_name=request.data.get("first_name"),
            last_name=request.data.get("last_name"),
            email=request.data.get("email"),
            phone_number=request.data.get("phone_number"),
            gender=request.data.get("gender"),
            state=request.data.get("state"),
            lga=request.data.get("lga"),
            address=request.data.get("address"),
            cv=cv_url,
        )
        # TODO
        # send application to careers@picadailys.com.
        # name = request.data.get("name", "N/A")
        # email = request.data.get("email", "N/A")
        # role = request.data.get("role", "N/A")
        # content = f""" # name: {name}, 
        # # email: {email},
        # CV: [View CV]({cv_url}), # cover letter: [View Cover Letter]({letter_url}),

        # """ # sendMail(content=content, subject=role)

        return Response(
            {
                "status": "success",
                "message": "Job application sent!",
                "data": {
                    "job_id": job.id,
                    "job_title": job.title,
                    "first_name": application.first_name,
                    "last_name": application.last_name,
                    "email": application.email,
                    "phone_number": application.phone_number,
                    "cv": cv_url,
                },
            },
            status=status.HTTP_201_CREATED
        )

    def upload_image(self, image_data):
        doc_image = cloud.upload(file=image_data)
        self.uploaded_doc_url = doc_image["url"]


class DeleteJobApplication(generics.DestroyAPIView):
    """
    Deletes a single job application entry by ID.
    """

    queryset = Applications.objects.all()
    serializer_class = ApplicationsSerializers
    permission_classes = [IsAuthenticated, IsAdmin]
    authentication_classes = [JWTAuthentication]

    def delete(self, request, pk, *args, **kwargs):
        application = get_object_or_404(Applications, pk=pk)

        decrypted_payload = decrypt(request.data)

        current_user = request.user
        pin = decrypted_payload.get("pin")
        if not check_password(password=pin, encoded=current_user.admin_pin):
            return Response(
                data=encrypt({
                    "status": "fail",
                    "message": "Incorrect pin.",
                }),
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            application.delete()
            return Response(
                data=encrypt({
                    "status": "success",
                    "message": "Job application deleted successfully",
                }),
                status=status.HTTP_200_OK,
            )
        except Exception as err:
            return Response(
                data={
                    "status": "error",
                    "message": f"An error occurred: {err}",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class JobApplicationDetail(generics.ListAPIView):
    """
    Retrieve a single job application based on the email.
    """

    queryset = Applications.objects.all()
    serializer_class = ApplicationsSerializers
    permission_classes = [IsAuthenticated, IsAdmin]
    authentication_classes = [JWTAuthentication]

    def get_queryset(self):
        email = self.kwargs.get("email")
        email.lower()
        if email is None:
            return Response(
                data={"error": "Email parameter is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        applications = Applications.objects.filter(email=email)
        if not applications.exists():
            return Response(
                data={"error": "No job applications with this email exist."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            data={
                "status": "success",
                "data": ApplicationsSerializers(applications, many=True).data,
            },
            status=status.HTTP_200_OK,
        )


class JobApplicationList(generics.ListAPIView):
    """
    List all job applications.
    """

    queryset = Applications.objects.all()
    serializer_class = GetApplicationsSerializers
    permission_classes = [IsAuthenticated, IsAdmin]
    authentication_classes = [JWTAuthentication]

    def get(self, request, *args, **kwargs):
        paginator = CustomPageNumberPagination()
        applications = Applications.objects.all().order_by("-created_at")
        result_page = paginator.paginate_queryset(applications, request)
        serializer = GetApplicationsSerializers(result_page, many=True)
        return paginator.get_paginated_response(serializer.data)


class NewsletterSubscriptionView(generics.CreateAPIView):
    """
    NewsletterSubscriptionView handles the POST request to subscribe to the newsletter.
    """

    permission_classes = (AllowAny,)
    serializer_class = NewsletterSubscribersSerializer

    def post(self, request, *args, **kwargs):
        payload = request.data
        email = payload.get("email")

        if not email:
            return Response(
                data={
                    "status": "fail",
                    "message": "Email is required."
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        logger.error(f"Newsletter subscription attempt failed: {email}")

        if NewsletterSubscribers.objects.filter(email=email).exists():
            return Response(
                data={
                    "status": "fail",
                    "message": "This email is already subscribed."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        NewsletterSubscribers.objects.create(email=email)
        logger.info(f"New newsletter subscription: {email}")

        return Response(
            data={
                "status": "success",
                "message": "Subscribed to newsletter successfully.",
            },
            status=status.HTTP_201_CREATED
        )


class NewsletterUnsubscribeView(generics.DestroyAPIView):
    """
    NewsletterUnsubscribeView handles the DELETE request to unsubscribe from the newsletter.
    """

    permission_classes = (AllowAny,)

    def delete(self, request, *args, **kwargs):
        payload = request.data
        email = payload.get("email")

        if not email:
            return Response(
                data={
                    "status": "fail",
                    "message": "Email is required."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            subscriber = NewsletterSubscribers.objects.get(email=email)
            subscriber.delete()
            logger.info(f"Newsletter unsubscribed: {email}")
            return Response(
                data={
                    "status": "success",
                    "message": "Unsubscribed from newsletter successfully."
                },
                status=status.HTTP_200_OK
            )
        except NewsletterSubscribers.DoesNotExist:
            logger.error(f"Unsubscribe attempt failed - email not found: {email}")
            return Response(
                data={
                    "status": "fail",
                    "message": "This email is not subscribed."
                },
                status=status.HTTP_404_NOT_FOUND
            )


class ListNewsletterSubscribersView(generics.ListAPIView):
    """
    List all newsletter subscribers.
    """

    queryset = NewsletterSubscribers.objects.all().order_by("-subscribed_at")
    serializer_class = NewsletterSubscribersSerializer
    permission_classes = [IsAuthenticated, IsAdmin]
    authentication_classes = [JWTAuthentication]
    pagination_class = CustomPageNumberPagination

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        paginator = self.pagination_class()
        paginated_qs = paginator.paginate_queryset(queryset, request)
        serializer = self.get_serializer(paginated_qs, many=True)

        response = {
            "status": "success",
            "message": "Newsletter subscribers retrieved successfully",
            "data": serializer.data,
        }

        return Response(encrypt(response), status=status.HTTP_200_OK)
