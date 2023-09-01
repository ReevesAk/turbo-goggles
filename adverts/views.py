# Third party imports
from rest_framework import generics, status
from rest_framework.permissions import (
    AllowAny, IsAuthenticated
)
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser
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
    permission_classes = [JWTAuthentication]
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
    permission_classes = (AllowAny,)
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
    permission_classes = [IsAuthenticated]
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
    permission_classes = (IsAuthenticated,)



class UploadLogo(generics.CreateAPIView):
    serializer_class = BrandAvertLogoUploadsSerializers
    parser_classes = (MultiPartParser,)
    queryset = BrandAdlogo.objects.all()
   

class CreateBrandAdvertService(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
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
    queryset = BrandAdService.objects.all()
    serializer_class = AdvertServicecSerializers
    permission_classes = [IsAuthenticated]
    

class BookAnAdvert(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = BookAvertSerializers

    def post(self, request):
        user = request.data
        serializer = self.serializer_class(data=user)
        if serializer.is_valid(raise_exception=True):
            serializer.save()
            user_data = serializer.data
            match BookAnAdvert.booking:  
                case "confirm":
                    response = {"message": "Ad booked!", "data": user_data}
                    return Response(data=response, status=status.HTTP_200_OK)
                case "cancel":
                    response = {"message": "Ad cancelled!", "data": user_data}
                    return Response(data=serializer.errors, status=status.HTTP_200_OK)
                

class BookedAdvertListView(generics.RetrieveAPIView):
    queryset = BookAnAd.objects.all()
    serializer_class = BookAvertSerializers
    permission_classes = [IsAuthenticated]
