from django.urls import path

from .views import (
    JobList,
    CreateJob,
    JobDetail,
    UpdateJob,
    DeleteJob,
    SubmitJobApplication,
    JobApplicationList,
    SingleJobApplicationsList,
    JobApplicationDetail,
    DeleteJobApplication,
    NewsletterSubscriptionView,
    NewsletterUnsubscribeView,
    ListNewsletterSubscribersView,
    ContactUsView,
    ListBusinessesAndIndividualsToContact
)

app_name = "web"

urlpatterns = [
    path("jobs/", JobList.as_view(), name="job-list"),
    path("jobs/create/", CreateJob.as_view(), name="job-create"),
    path("jobs/<int:id>/", JobDetail.as_view(), name="job-detail"),
    path("jobs/<int:id>/update/", UpdateJob.as_view(), name="job-update"),
    path("jobs/<int:id>/delete/", DeleteJob.as_view(), name="job-delete"),
    path("career/<int:job_id>/submit-application", SubmitJobApplication.as_view(), name="submit_application"),
    # Applications endpoints.
    path(
        "career/get-applications",
        JobApplicationList.as_view(),
        name="application-list",
    ),
    path(
        "career/get-applications/<int:job_id>",
        SingleJobApplicationsList.as_view(),
        name="job-applications-list",
    ),
    path(
        "career/applications/<str:email>/",
        JobApplicationDetail.as_view(),
        name="application-detail",
    ),
    path(
        "career/applications/<int:pk>/delete/",
        DeleteJobApplication.as_view(),
        name="delete-application",
    ),
    path(
        "newsletter/subscribe/",
        NewsletterSubscriptionView.as_view(),
        name="newsletter-subscribe",
    ),
    path(
        "newsletter/unsubscribe/",
        NewsletterUnsubscribeView.as_view(),
        name="newsletter-unsubscribe",
    ),
    path(
        "newsletter/subscribers/",
        ListNewsletterSubscribersView.as_view(),
        name="list-newsletter-subscribers",
    ),
    path("contact-us", ContactUsView.as_view(), name="contact_us"),
    path("list-contact-us-requests", ListBusinessesAndIndividualsToContact.as_view(), name="list_contact_us_requests")
]
