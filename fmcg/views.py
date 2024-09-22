from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .models import PRODUCT_CATEGORY, COMPANY


class CategoryListView(APIView):
    """
    CategoryListView is the GET request handler that returns a list of product categories.
    """
    def get(self, request):
        categories = [category[1] for category in PRODUCT_CATEGORY]
        return Response(
            data={
                "status": "success.",
                "message": "FMCG Categories retrieved successfully.",
                "categories": categories,
            },
            status=status.HTTP_200_OK)


class CompanyListView(APIView):
    """
    CompanyListView is the GET request handler that returns a list of fmcg companies.
    """
    def get(self, request):
        companies = [company[1] for company in COMPANY]
        return Response(
            data={
                "status": "success.",
                "message": "FMCG Companies retrieved successfully.",
                "categories": companies,
            },
            status=status.HTTP_200_OK)
