import logging
import requests
from decouple import config

from rest_framework import status
from rest_framework.response import Response


api_secret_key = config("MAPLERAD_SECRET_KEY")
base_url = config("MAPLERAD_BASE_URL")

headers = {
    "accept": "application/json",
    "content-Type": "application/json",
    "Authorization": "Bearer "+ api_secret_key,
}


