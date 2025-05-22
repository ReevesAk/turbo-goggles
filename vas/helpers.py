import logging
import requests
from decouple import config

from rest_framework import status
from rest_framework.response import Response


vtpass_url = config("VT_PASS_BASE_URL")
x_secret = config("VT_PASS_SECRET_KEY")
api_key = config("VT_PASS_API_KEY")
x_token = config("VT_PASS_PUBLIC_KEY")

headers = {"secret-key": x_secret, "api-key": api_key}


class VAS:
    @staticmethod
    def aritime(service_id, req_id, amount, phone):
        resource = "pay"
        payload = {
            "request_id": req_id,
            "serviceID": service_id,
            "amount": amount,
            "phone": phone,
        }

        try:
            response = requests.post(
                url=vtpass_url + resource,
                json=payload,
                headers=headers,
            )
            return response
        except requests.exceptions.RequestException as e:
            logging.error(f"Airtime topup API request error: {str(e)}")
            return response

    @staticmethod
    def data(service_id, req_id, amount, phone, billersCode, variation_code):
        resource = "pay"
        payload = {
            "request_id": req_id,
            "serviceID": service_id,
            "amount": amount,
            "phone": phone,
            "billersCode": billersCode,
            "variation_code": variation_code,
        }

        try:
            response = requests.post(
                url=vtpass_url + resource,
                json=payload,
                headers=headers,
            )
            return response
        except requests.exceptions.RequestException as e:
            logging.error(f"Data subscription API request error: {str(e)}")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @staticmethod
    def electricity(service_id, req_id, amount, phone, billersCode, variation_code):
        resource = "pay"
        payload = {
            "request_id": req_id,
            "serviceID": service_id,
            "amount": amount,
            "phone": phone,
            "billersCode": billersCode,
            "variation_code": variation_code,
        }

        try:
            response = requests.post(
                url=vtpass_url + resource,
                json=payload,
                headers=headers,
            )
            return response
        except requests.exceptions.RequestException as e:
            logging.error(f"Tv subscription API request error: {str(e)}")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @staticmethod
    def newTvSub(
        service_id,
        amount,
        req_id,
        phone,
        billersCode,
        variation_code,
        quantity,
        subscription_type,
    ):
        resource = "pay"
        payload = {
            "request_id": req_id,
            "serviceID": service_id,
            "amount": amount,
            "phone": phone,
            "billersCode": billersCode,
            "variation_code": variation_code,
            "subscription_type": subscription_type,
            "quantity": quantity,
        }

        try:
            response = requests.post(
                url=vtpass_url + resource,
                json=payload,
                headers=headers,
            )
            return response
        except requests.exceptions.RequestException as e:
            logging.error(f"Data subscription API request error: {str(e)}")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @staticmethod
    def renewTvSub(service_id, req_id, amount, phone, billersCode, subscription_type):
        resource = "pay"
        payload = {
            "request_id": req_id,
            "serviceID": service_id,
            "amount": amount,
            "phone": phone,
            "billersCode": billersCode,
            "subscription_type": subscription_type,
        }

        try:
            response = requests.post(
                url=vtpass_url + resource,
                json=payload,
                headers=headers,
            )
            return response
        except requests.exceptions.RequestException as e:
            logging.error(f"Data subscription API request error: {str(e)}")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @staticmethod
    def intl_topup(
        service_id,
        req_id,
        amount,
        phone,
        billersCode,
        operator_id,
        variation_code,
        country_code,
        email,
        product_type_id,
    ):
        resource = "pay"
        payload = {
            "request_id": req_id,
            "serviceID": service_id,
            "amount": amount,
            "phone": phone,
            "billersCode": billersCode,
            "operator_id": operator_id,
            "variation_code": variation_code,
            "country_code": country_code,
            "email": email,
            "product_type_id": product_type_id,
        }

        try:
            response = requests.post(
                url=vtpass_url + resource,
                json=payload,
                headers=headers,
            )
            return response
        except requests.exceptions.RequestException as e:
            logging.error(f"International topup API request error: {str(e)}")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @staticmethod
    def waec_reg(service_id, req_id, phone, variation_code, quantity):
        resource = "pay"
        payload = {
            "request_id": req_id,
            "serviceID": service_id,
            "variation_code": variation_code,
            "quantity": quantity,
            "phone": phone,
        }

        try:
            response = requests.post(
                url=vtpass_url + resource,
                json=payload,
                headers=headers,
            )
            return response
        except requests.exceptions.RequestException as e:
            logging.error(f"Waec registration API request error: {str(e)}")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @staticmethod
    def check_status(req_id):
        resource = "requery"
        payload = {
            "request_id": req_id,
        }

        status_headers = {
            "accept": "application/json",
            "api-key": api_key,
            "secret-key": x_secret,
        }
        try:
            response = requests.get(
                url=vtpass_url + resource, headers=status_headers, json=payload
            )
            return response
        except requests.exceptions.RequestException as e:
            logging.error(f" API request error: {str(e)}")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
