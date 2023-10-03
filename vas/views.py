from datetime import datetime
import requests
from decouple import config

from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication


from .serializers import AirtimeTopupSerilizers


vtpass_url = config("VT_PASS_BASE_URL")
x_secret = config("VT_PASS_SECRET_KEY")
api_key = config("VT_PASS_API_KEY")
x_token = config("VT_PASS_PUBLIC_KEY")


class AirTimeTopUp(generics.GenericAPIView):
    serializer_class = AirtimeTopupSerilizers
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        user = request.data

        current_datetime = datetime.now()
        res_id = current_datetime.strftime("%Y%m%d%H%M" + "picadailys")

        resource = "pay"
        payload = {
            "request_id": res_id,
            "serviceID": user["serviceID"],
            "amount": user["amount"],
            "phone": user["phone"],
        }

        airtime_headers = {"secret-key": x_secret, "api-key": api_key}

        serializer = self.serializer_class(data=user)
        if serializer.is_valid(raise_exception=True):
            serializer.save()
            try:
                response = requests.post(
                    url=vtpass_url + resource,
                    json=payload,
                    headers=airtime_headers,
                )

                if response.status_code == 200:
                    response_data = {
                        "data": response.json(),
                    }

                    return Response(data=response_data, status=status.HTTP_201_CREATED)
                else:
                    return Response(response.json(), status=response.status_code)

            except requests.exceptions.RequestException as e:
                return Response(
                    {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
