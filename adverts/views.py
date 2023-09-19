# Third party imports
from rest_framework import generics, status
from rest_framework.permissions import (
    AllowAny, IsAuthenticated
)
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication

# In project imports.
from .serializers import (
    AdvertStartSeriailizers, AdvertContdSerializers, 
    AdvertServicecSerializers, BrandAvertLogoUploadsSerializers,
    BookAvertSerializers, BrandAvertSurveySerializers
)
from .models import (
    BrandAdService, BrandAdlogo, BrandAdSurvey, BookAnAd
)


# Create your views here.

class StartRegisterAdverts(generics.GenericAPIView):
    serializer_class = AdvertStartSeriailizers

    def post(self, request):
        user = request.data
        serializer = self.serializer_class(data=user)
        if serializer.is_valid(raise_exception=True):
            serializer.save()
            user_data = serializer.data

        response = {"message": "Details successfully submitted!", "data": user_data}
        return Response(data=response, status=status.HTTP_201_CREATED)
    

class ContdRegisterAdverts(generics.GenericAPIView):
    authentication_classes = [JWTAuthentication]
    serializer_class = AdvertContdSerializers

    def post(self, request):
        user = request.data
        serializer = self.serializer_class(data=user)
        if serializer.is_valid(raise_exception=True):
            serializer.save()
            user_data = serializer.data

        response = {"message": "Details successfully submitted!", "data": user_data}
        return Response(data=response, status=status.HTTP_201_CREATED)
    
    
class Survey(generics.GenericAPIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, )
    serializer_class = BrandAvertSurveySerializers

    def post(self, request):
        user = request.data
        serializer = self.serializer_class(data=user)
        if serializer.is_valid(raise_exception=True):
            serializer.save()
            user_data = serializer.data

        response = {"message": "Survey results updated!", "data": user_data}
        return Response(data=response, status=status.HTTP_200_OK)
    

class SurveyList(generics.RetrieveAPIView):
    queryset = BrandAdSurvey.objects.all()
    serializer_class = BrandAvertSurveySerializers
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, )



class UploadLogo(generics.CreateAPIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, )
    serializer_class = BrandAvertLogoUploadsSerializers
    parser_classes = (MultiPartParser,)
    queryset = BrandAdlogo.objects.all()


class CreateBrandAdvertService(generics.GenericAPIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, )
    serializer_class = AdvertServicecSerializers

    def post(self, request):
        user = request.data
        serializer = self.serializer_class(data=user)
        if serializer.is_valid(raise_exception=True):
            serializer.save()
            user_data = serializer.data

        response = {"message": "Service Created!", "data": user_data}
        return Response(data=response, status=status.HTTP_201_CREATED)  
    

class BrandAdServiceListView(generics.RetrieveAPIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, )
    queryset = BrandAdService.objects.all()
    serializer_class = AdvertServicecSerializers
    

class BookAnAdvert(generics.GenericAPIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, )
    serializer_class = BookAvertSerializers

    def post(self, request):
        user = request.data
        serializer = self.serializer_class(data=user)
        if serializer.is_valid(raise_exception=True):
            serializer.save()
            user_data = serializer.data
            if BookAnAdvert.booking == "confirm":
                    response = {"message": "Ad booked!", "data": user_data}
                    return Response(data=response, status=status.HTTP_200_OK)
            elif BookAnAdvert.booking =="cancel":
                    response = {"message": "Ad cancelled!", "data": user_data}
                    return Response(data=serializer.errors, status=status.HTTP_200_OK)
                

class BookedAdvertListView(generics.RetrieveAPIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated, )
    queryset = BookAnAd.objects.all()
    serializer_class = BookAvertSerializers
