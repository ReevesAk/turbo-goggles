import logging
import requests
from decouple import config

from rest_framework import status
from rest_framework.response import Response

from .models import Cards


api_secret_key = config("MAPLERAD_SECRET_KEY")
base_url = config("MAPLERAD_BASE_URL")

headers = {
    "accept": "application/json",
    "content-Type": "application/json",
    "Authorization": "Bearer " + api_secret_key,
}


class BVN:
        @staticmethod
        def verify(bvn):
            resource = "identity/bvn"

            payload = {
                "bvn": bvn,
            }

            try:
                response = requests.post(
                    url=base_url + resource,
                    json=payload,
                    header=headers,
                )
                return response
            except requests.exceptions.RequestException as e:
                logging.error(f"BVN API request error: {str(e)}")
                return Response(
                    {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )


class Customer:
    @staticmethod
    def create(f_name, l_name, email, country):
        resource = "customers"
        payload = {
            "f_name": f_name,
            "l_name": l_name,
            "email": email,
            "country": country,
        }

        try:
            response = requests.post(
                url=base_url + resource,
                json=payload,
                header=headers,
            )
            if response.status_code == 200:
                resp = response.json()
                country = resp["data"]["country"]
                email = resp["data"]["email"]
                first_name = resp["data"]["first_name"]
                last_name = resp["data"]["last_name"]
                customer_id = resp["data"]["id"]

                return {
                    "country": country,
                    "email": email,
                    "first_name": first_name,
                    "last_name": last_name,
                    "customer_id": customer_id,
                }
            else:
                logging.error(
                    f"Enroll customer API error: {response.status_code} - {response.text}"
                )
                return None
        except requests.exceptions.RequestException as e:
            logging.error(f"Enroll customer API request error: {str(e)}")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @staticmethod
    def upgradeTier1(id, dob, phone, street, street2, city, state, postal_code, bvn):
        resource = "customers/upgrade/tier1"
        payload = {
            "dob": dob,
            "phone": {"phone_country_code": "+234", "phone_number": phone[1:]},
            "address": {
                "street": street,
                "street2": street2,
                "city": city,
                "state": state,
                "country": "NG",
                "postal_code": postal_code,
            },
            "customer_id": id,
            "identification_number": bvn,
        }

        try:
            response = requests.post(
                url=base_url + resource,
                json=payload,
                header=headers,
            )
            return response

        except requests.exceptions.RequestException as e:
            logging.error(f"Upgrade customer to Tier 1 API request error: {str(e)}")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @staticmethod
    def upgradeTier2(id_type, id_no, id_img, customer_id):
        resource = "customers/upgrade/tier2"
        payload = {
            "identity": {
                "type": id_type,
                "image": id_img,
                "number": id_no,
                "country": "NG",
            },
            "customer_id": customer_id,
        }

        try:
            response = requests.post(
                url=base_url + resource,
                json=payload,
                header=headers,
            )
            return response

        except requests.exceptions.RequestException as e:
            logging.error(f"Upgrade customer to Tier 1 API request error: {str(e)}")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class VirtualCard:
    @staticmethod
    def fund(id, amount):
        resource = f"issuing/{id}/fund"
        payload = {
            "amount": amount,
        }

        try:
            response = requests.post(
                url=base_url + resource,
                json=payload,
                header=headers,
            )
            return response

        except requests.exceptions.RequestException as e:
            logging.error(f"Fund a USD card API request error: {str(e)}")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @staticmethod
    def Freeze(id):
        resource = f"issuing/{id}/freeze"

        try:
            response = requests.post(
                url=base_url + resource,
                header=headers,
            )
            return response

        except requests.exceptions.RequestException as e:
            logging.error(f"Freezing a USD card API request error: {str(e)}")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def Unfreeze(id):
        resource = f"issuing/{id}/unfreeze"

        try:
            response = requests.post(
                url=base_url + resource,
                header=headers,
            )
            return response

        except requests.exceptions.RequestException as e:
            logging.error(f"Unfreezing a USD card API request error: {str(e)}")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
