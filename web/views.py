import logging

from django.core.exceptions import ValidationError
from django.db import transaction
from django.template.loader import render_to_string
from django.shortcuts import get_object_or_404
from django.contrib.auth.hashers import check_password

from .models import Applications, JobModel, NewsletterSubscribers, ContactUs

# In project imports.
from .serializers import (
    ApplicationsSerializers,
    GetApplicationsSerializers,
    JobSerializer,
    ListJobSerializer,
    NewsletterSubscribersSerializer,
    UnsubscribeNewsletterSerializer,
    ContactUsSerializer,
    GetApplicationsWaitlistSerializers,
)

from support.models import Ticket
from support.utils import generate_ticket_number

# Third party imports.
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.parsers import MultiPartParser, JSONParser
from rest_framework.pagination import PageNumberPagination

from drf_spectacular.utils import extend_schema, OpenApiExample

from cloudinary import uploader as cloud
from security import encrypt, decrypt
from commons import Messaging

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
                encrypt(
                    {
                        "status": "fail",
                        "message": "This job posting already exists.",
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = self.serializer_class(data=payload)
        serializer.is_valid(raise_exception=True)
        serializer.validated_data.pop("pin", None)

        job = serializer.save()

        return Response(
            encrypt(
                {
                    "status": "success",
                    "message": "Job Created!",
                    "data": {
                        "id": job.id,
                        "title": job.title,
                        "location": job.location,
                        "salary": str(job.salary),
                        "is_active": job.is_active,
                    },
                }
            ),
            status=status.HTTP_201_CREATED,
        )


class JobList(generics.ListAPIView):
    """
    List all active and non-expired job postings.
    """

    queryset = JobModel.objects.all().order_by("-created_at")
    serializer_class = ListJobSerializer
    permission_classes = ()
    pagination_class = CustomPageNumberPagination

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        paginator = self.pagination_class()
        paginated_qs = paginator.paginate_queryset(queryset, request)
        serializer = self.get_serializer(paginated_qs, many=True)

        return paginator.get_paginated_response(
            {
                "status": "success",
                "message": "Jobs retrieved successfully",
                "data": serializer.data,
            }
        )


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
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "Incorrect pin.",
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer.is_valid(raise_exception=True)
        serializer.save()

        response = {
            "status": "success",
            "message": "Job updated successfully",
            "data": serializer.data,
        }
        return Response(encrypt(response), status=status.HTTP_200_OK)


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
                data=encrypt({"status": "fail", "message": "Incorrect pin."}),
                status=status.HTTP_400_BAD_REQUEST,
            )

        job.delete()

        response = {"status": "success", "message": "Job deleted successfully"}

        return Response(data=encrypt(response), status=status.HTTP_200_OK)


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
                {"status": "fail", "message": "job_id is required in the URL params."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            job = JobModel.objects.get(id=job_id)
        except JobModel.DoesNotExist:
            return Response(
                {"status": "fail", "message": "Invalid job ID."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = ApplicationsSerializers(data=request.data)
        serializer.is_valid(raise_exception=True)

        cv_file = serializer.validated_data.pop("cv")
        upload_cv = cloud.upload(cv_file)
        cv_url = upload_cv["url"]

        portfolio_file = serializer.validated_data.pop("portfolio_file", None)
        portfolio_text = serializer.validated_data.pop("portfolio_text", None)
        if portfolio_file:
            upload_portfolio = cloud.upload(portfolio_file)
            portfolio_value = upload_portfolio["url"]
        elif portfolio_text:
            portfolio_value = portfolio_text.strip()
        else:
            portfolio_value = None

        cover_letter_file = serializer.validated_data.pop("cover_letter", None)
        if cover_letter_file:
            upload_cover_letter = cloud.upload(cover_letter_file)
            cover_letter_url = upload_cover_letter["url"]
        else:
            cover_letter_url = None

        # Prevent duplicate application per job
        if Applications.objects.filter(
            email=request.data.get("email"), job=job
        ).exists():
            return Response(
                {"status": "fail", "message": "You have already applied for this job."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        application = Applications.objects.create(
            **serializer.validated_data,
            job=job,
            job_title=job.title,  # ✅ from DB
            cv=cv_url,
            portfolio=portfolio_value,
            cover_letter=cover_letter_url,
        )

        text_content = render_to_string(
            template_name="empty_email.html",
            context={
                "custom_text": f"""
                    Dear HR,<br><br>
                    Application for the position of <strong>{job.title}</strong> has been submitted successfully.<br><br>
                    Applicant Name: {application.first_name} {application.last_name}<br>
                    Email: {application.email}<br>
                    Phone Number: {application.phone_number}<br><br>
                    Please review the application and proceed
                    to complete your signup.<br><br>
                    If you have any questions, feel free to contact us at our support email or phone below.
                """,
                "support_email": "support@picadailys.com",
                "picadailys_phone": [
                    "02012271894",
                    "02012271895",
                ],
            },
        )

        Messaging.send_email(
            sender_email="Info@picadailys.com",
            body="Job application submitted successfully.",
            email=request.data.get("email"),
            html_content=text_content,
            subject=f"Application for {job.title} Received",
        )

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
                    "portfolio": portfolio_url,
                    "cover_letter": cover_letter_url,
                },
            },
            status=status.HTTP_201_CREATED,
        )

    def upload_image(self, image_data):
        doc_image = cloud.upload(file=image_data)
        self.uploaded_doc_url = doc_image["url"]


class SingleJobApplicationsList(generics.ListAPIView):
    """
    List all applications for a specific job (Admin only).
    PIN is validated manually from request body.
    """

    serializer_class = ApplicationsSerializers
    permission_classes = [IsAuthenticated, IsAdmin]
    authentication_classes = [JWTAuthentication]

    def get_queryset(self):
        job_id = self.kwargs.get("job_id")
        return Applications.objects.filter(job_id=job_id).order_by("-created_at")

    def post(self, request, *args, **kwargs):
        # 🔐 Decrypt payload
        decrypted_payload = decrypt(request.data)
        payload = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in decrypted_payload.items()
        }

        pin = payload.get("pin")
        if not pin:
            return Response(
                encrypt({"status": "fail", "message": "PIN is required."}),
                status=status.HTTP_400_BAD_REQUEST,
            )

        current_user = request.user

        # 🔑 Validate admin PIN
        if not check_password(pin, current_user.admin_pin):
            return Response(
                encrypt({"status": "fail", "message": "Incorrect PIN."}),
                status=status.HTTP_400_BAD_REQUEST,
            )

        queryset = self.get_queryset()

        if not queryset.exists():
            return Response(
                data=encrypt(
                    {
                        "status": "success",
                        "message": "No applications found for this job.",
                        "count": 0,
                        "data": [],
                    }
                ),
                status=status.HTTP_200_OK,
            )

        serializer = self.get_serializer(queryset, many=True)

        return Response(
            data=encrypt(
                {
                    "status": "success",
                    "message": "Applications retrieved successfully.",
                    "count": queryset.count(),
                    "data": serializer.data,
                }
            ),
            status=status.HTTP_200_OK,
        )


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
                data=encrypt(
                    {
                        "status": "fail",
                        "message": "Incorrect pin.",
                    }
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            application.delete()
            return Response(
                data=encrypt(
                    {
                        "status": "success",
                        "message": "Job application deleted successfully",
                    }
                ),
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
    serializer_class = ApplicationsSerializers
    permission_classes = [IsAuthenticated, IsAdmin]
    authentication_classes = [JWTAuthentication]

    def get(self, request, *args, **kwargs):
        email = kwargs.get("email")

        if not email:
            return Response(
                {"error": "Email parameter is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        queryset = Applications.objects.filter(email__iexact=email)

        if not queryset.exists():
            return Response(
                {"error": "No job applications with this email exist."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = self.get_serializer(queryset, many=True)
        return Response(
            {
                "status": "success",
                "data": serializer.data,
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
        applications = Applications.objects.exclude(waitlist=True).order_by(
            "-created_at"
        )
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
                data={"status": "fail", "message": "Email is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        logger.info(f"Newsletter subscription attempt successful: {email}")

        if NewsletterSubscribers.objects.filter(email=email).exists():
            return Response(
                data={"status": "fail", "message": "This email is already subscribed."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        NewsletterSubscribers.objects.create(email=email)
        logger.info(f"New newsletter subscription: {email}")

        return Response(
            data={
                "status": "success",
                "message": "Subscribed to newsletter successfully.",
            },
            status=status.HTTP_201_CREATED,
        )


class NewsletterUnsubscribeView(generics.GenericAPIView):
    permission_classes = (AllowAny,)
    serializer_class = UnsubscribeNewsletterSerializer

    def post(self, request):
        token = request.data.get("token")

        if not token:
            return Response(
                data={"status": "fail", "message": "Invalid unsubscribe request"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            subscriber = NewsletterSubscribers.objects.get(token=token)
            subscriber.delete()

            return Response(
                data={
                    "status": "success",
                    "message": "You’ve been unsubscribed successfully",
                },
                status=status.HTTP_200_OK,
            )

        except (NewsletterSubscribers.DoesNotExist, ValidationError):
            return Response(
                data={
                    "status": "fail",
                    "message": "This unsubscribe link is invalid or expired",
                },
                status=status.HTTP_400_BAD_REQUEST,
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


@extend_schema(
    request=ContactUsSerializer,
    examples=[
        OpenApiExample(
            "Business Use (WhatsApp)",
            value={
                "contact_type": "Business Use",
                "first_name": "Business",
                "last_name": "Name",
                "business_name": "Picadailys Ltd",
                "channel": {"type": "whatsapp", "value": "+2348012345678"},
                "message": "We want to partner with you",
                "accept_policy": True,
            },
        ),
        OpenApiExample(
            "Personal Use (Email)",
            value={
                "contact_type": "Personal Use",
                "first_name": "John",
                "last_name": "Doe",
                "product_of_interest": "Brand Advertisement",
                "channel": {"type": "email", "value": "john@example.com"},
                "message": "I’d like to know more",
                "accept_policy": True,
            },
        ),
    ],
)
class ContactUsView(generics.GenericAPIView):
    """
    ContactUsView is a the POST request handler for receieving user's contact information.
    Either for business or personal use. For busines use case, business names must be provided.
    For Personal use case, Full names must be provided.
    """

    serializer_class = ContactUsSerializer
    permission_classes = (AllowAny,)
    authentication_classes = []

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        contact_type = data.get("contact_type")
        channel = data.get("channel")

        try:
            with transaction.atomic():
                # ✅ Save to DB
                serializer.save()

                match contact_type:
                    case "Business Use":
                        business_name = data.get("business_name")
                        full_name = f"{data.get('first_name')} {data.get('last_name')}"
                        recipient_email = "support@picadailys.com"

                        text_content = render_to_string(
                            "empty_email.html",
                            {
                                "custom_text": (
                                    f"{data['message']}<br><br>"
                                    f"Name: {full_name}<br>"
                                    f"Business Name: {business_name}<br>"
                                    f"Channel: {channel['type']} - {channel['value']}"
                                )
                            },
                        )

                        Messaging.send_email(
                            sender_email="notifications@picadailys.com",
                            subject="Contact Us (Business)",
                            body=data["message"],
                            html_content=text_content,
                            email=recipient_email,
                        )

                        response_message = (
                            f"Contact Us form filled and sent from {business_name}."
                        )

                        # Create a support ticket for the business inquiry
                        full_name_for_ticket = full_name
                        customer_email = (
                            channel.get("value")
                            if channel.get("type") == "Email"
                            else None
                        )
                        customer_phone = (
                            channel.get("value")
                            if channel.get("type") == "Phone"
                            else None
                        )

                        ticket = Ticket.objects.create(
                            user=None,
                            title=f"Business Inquiry from {business_name}",
                            customer_name=full_name_for_ticket,
                            customer_email=customer_email,
                            customer_phone_number=customer_phone,
                            category="Business Inquiry",
                            channel="Website",
                            description=data["message"],
                            priority="Low",
                            status="New",
                        )

                        ticket.number = generate_ticket_number()
                        ticket.save(update_fields=["number"])

                    case "Personal Use":
                        full_name = f"{data.get('first_name')} {data.get('last_name')}"
                        interest = data.get("product_of_interest")
                        recipient_email = "info@picadailys.com"

                        text_content = render_to_string(
                            "empty_email.html",
                            {
                                "custom_text": (
                                    f"{data['message']}<br><br>"
                                    f"Name: {full_name}<br>"
                                    f"Interest: {interest}<br>"
                                    f"Channel: {channel['type']} - {channel['value']}"
                                )
                            },
                        )

                        Messaging.send_email(
                            sender_email="notifications@picadailys.com",
                            subject="Contact Us (Personal)",
                            body=data["message"],
                            html_content=text_content,
                            email=recipient_email,
                        )

                        response_message = (
                            f"Contact Us form filled and sent from {full_name}."
                        )

                        # Create a support ticket for the personal inquiry
                        customer_email = (
                            channel.get("value")
                            if channel.get("type") == "Email"
                            else None
                        )
                        customer_phone = (
                            channel.get("value")
                            if channel.get("type") == "Phone"
                            else None
                        )

                        ticket = Ticket.objects.create(
                            user=None,
                            title=f"Personal Inquiry from {full_name}",
                            customer_name=full_name,
                            customer_email=customer_email,
                            customer_phone_number=customer_phone,
                            category="Personal Inquiry",
                            channel="Website",
                            description=data["message"],
                            priority="Low",
                            status="New",
                        )

                        ticket.number = generate_ticket_number()
                        ticket.save(update_fields=["number"])

                    case _:
                        raise ValueError("Invalid contact type")

        except Exception as exc:
            return Response(
                {
                    "status": "fail",
                    "message": "Unable to process contact request.",
                    "error": str(exc),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                "status": "success",
                "message": response_message,
            },
            status=status.HTTP_200_OK,
        )


class ListBusinessesAndIndividualsToContact(generics.GenericAPIView):
    """
    Lists all Contact-Us requests grouped by contact type.
    """

    serializer_class = ContactUsSerializer
    permission_classes = [IsAuthenticated, IsAdmin]
    authentication_classes = [JWTAuthentication]
    pagination_class = CustomPageNumberPagination

    def get(self, request):
        business_qs = ContactUs.objects.filter(contact_type="Business Use").order_by(
            "-created_at"
        )

        personal_qs = ContactUs.objects.filter(contact_type="Personal Use").order_by(
            "-created_at"
        )

        business_serializer = self.serializer_class(business_qs, many=True)
        personal_serializer = self.serializer_class(personal_qs, many=True)

        response = {
            "status": "success",
            "message": "Contact requests retrieved successfully",
            "data": {
                "business_use": business_serializer.data,
                "personal_use": personal_serializer.data,
            },
        }

        return Response(encrypt(response), status=status.HTTP_200_OK)


class JoinApplicationWaitlist(generics.CreateAPIView):
    """
    JoinApplicationWaitlist handles the POST request of applications waitlist to Picadailys.
    """

    serializer_class = ApplicationsSerializers
    permission_classes = (AllowAny,)
    parser_classes = (
        MultiPartParser,
        JSONParser,
    )

    def post(self, request, *args, **kwargs):
        serializer = ApplicationsSerializers(data=request.data)
        serializer.is_valid(raise_exception=True)

        cv_file = serializer.validated_data.pop("cv")
        upload_cv = cloud.upload(cv_file)
        cv_url = upload_cv["url"]

        # Prevent duplicate application waitlist
        if Applications.objects.filter(
            email=request.data.get("email"),
        ).exists():
            return Response(
                {"status": "fail", "message": "You have already submitted your CV."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        application = Applications.objects.create(
            **serializer.validated_data,
            cv=cv_url,
        )
        application.waitlist = True

        return Response(
            {
                "status": "success",
                "message": "You have succesfully joined the waitlist!",
                "data": {
                    "first_name": application.first_name,
                    "last_name": application.last_name,
                    "email": application.email,
                    "phone_number": application.phone_number,
                    "joined_waitlist": application.waitlist,
                    "cv": cv_url,
                },
            },
            status=status.HTTP_201_CREATED,
        )

    def upload_image(self, image_data):
        doc_image = cloud.upload(file=image_data)
        self.uploaded_doc_url = doc_image["url"]


class WaitlistApplicationList(generics.ListAPIView):
    """
    List all Waitlist applications.
    """

    queryset = Applications.objects.all()
    serializer_class = GetApplicationsWaitlistSerializers
    permission_classes = [IsAuthenticated, IsAdmin]
    authentication_classes = [JWTAuthentication]

    def get(self, request, *args, **kwargs):
        paginator = CustomPageNumberPagination()
        applications = Applications.objects.exclude(waitlist=False).order_by(
            "-created_at"
        )
        result_page = paginator.paginate_queryset(applications, request)
        serializer = GetApplicationsWaitlistSerializers(result_page, many=True)
        return paginator.get_paginated_response(serializer.data)
