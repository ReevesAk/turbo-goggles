from django.urls import path
from .views import *

urlpatterns = [
    path(
        "register-adverts/", StartRegisterAdverts.as_view(), name="register_ads-start"
    ),
    path(
        "register-adverts-contd/",
        ContdRegisterAdverts.as_view(),
        name="register_ads-contd",
    ),
    path("add-service/", CreateBrandAdvertService.as_view(), name="creare-service"),
    path(
        "list-service/<int:id>/", BrandAdServiceListView.as_view(), name="list_service"
    ),
    path("upload-logo/", UploadLogo.as_view(), name="upload_logo"),
    path("book-ad/", BookAnAdvert.as_view(), name="book_an_ad"),
    path("create-survey/", Survey.as_view(), name="create_survey"),
    path("list-survey/<int:id>/", SurveyList.as_view(), name="list_survey"),
]
