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
            if response.status_code == 200:
                resp = response.json()
                date_of_birth = resp["data"]["dob"]
                phone_number = resp["data"]["phone_number"]
                first_name = resp["data"]["first_name"]
                last_name = resp["data"]["last_name"]

                return {
                    "date_of_birth": date_of_birth,
                    "phone_num": phone_number,
                    "first_name": first_name,
                    "last_name": last_name,
                }
            else:
                logging.error(
                    f"BVN API error: {response.status_code} - {response.text}"
                )
                return None
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
            "country": country
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
                    "customer_id": customer_id
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
    def upgradeTier1(
        id, dob, phone, street, street2, city, state, postal_code, bvn):
        resource = "customers/upgrade/tier1"
        payload = {
           "dob": dob,
            "phone": {
                "phone_country_code": "+234",
                "phone_number": phone[1:]
            },
            "address": {
                "street": street,
                "street2": street2,
                "city": city,
                "state": state,
                "country": "NG",
                "postal_code": postal_code
            },
            "customer_id": id,
            "identification_number": bvn
        }

        try:
            response = requests.post(
                url=base_url + resource,
                json=payload,
                header=headers,
            )
            if response.status_code == 200:
                return Response(data="Tier One upgrade successful!", status=status.HTTP_200_OK)
            else:
                logging.error(
                    f"Upgrade customer Tier 1 API error: {response.status_code} - {response.text}"
                )
                return Response(data=f"Tier1 upgrade failed: - {response.text}", status=response.status_code)

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
                "country": "NG"
            },
            "customer_id": customer_id
        }

        try:
            response = requests.post(
                url=base_url + resource,
                json=payload,
                header=headers,
            )
            if response.status_code == 200:
                return {
                    "type": id_type,
                    "image": id_img,
                    "number": id_no,
                    "country": "NG"
                }
            else:
                logging.error(
                    f"Upgrade customer Tier 1 API error: {response.status_code} - {response.text}"
                )
                return None
            
        except requests.exceptions.RequestException as e:
            logging.error(f"Upgrade customer to Tier 1 API request error: {str(e)}")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
