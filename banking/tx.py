# Third party imports.
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.pagination import PageNumberPagination

# In-projects imports.
from accounts.models import TxModel
from vas.models import ValueAddedServices

from banking.serializers import TxModelSerializer
from vas.serializers import (
    AirtimeTopupSerializer,
    DataSubscriptionSerializer,
    BillPaymentSerializer,
)
from security import encrypt


class PaginationStyle(PageNumberPagination):
    page_size = 20


class AllTransactions(generics.ListAPIView):
    queryset = TxModel.objects.all()
    serializer_class = TxModelSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        transactions = TxModel.objects.filter(user=self.request.user)
        return transactions

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.serializer_class(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.serializer_class(queryset, many=True)
        encrypt_resp = encrypt(serializer.data)
        return Response(data=encrypt_resp, status=status.HTTP_200_OK)


class RetrieveTransaction(generics.GenericAPIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = (IsAuthenticated,)

    def get(self, request, tx_reference):
        user = request.user

        try:
            # Attempt to retrieve from AirtimeTopup
            airtime_instance = ValueAddedServices.objects.filter(
                user=user, tx_reference=tx_reference
            ).first()
            if airtime_instance:
                serializer = AirtimeTopupSerializer(airtime_instance)
                resp = {
                    "status": "success",
                    "message:": f"Transaction for {tx_reference} found!",
                    "data": serializer.data,
                }
                encrypt_resp = encrypt(resp)
                return Response(
                    data=encrypt_resp,
                    status=status.HTTP_200_OK,
                )

            # Attempt to retrieve from DataSubscription
            data_instance = ValueAddedServices.objects.filter(
                user=user, tx_reference=tx_reference
            ).first()
            if data_instance:
                serializer = DataSubscriptionSerializer(data_instance)
                resp = {
                    "status": "success",
                    "message:": f"Transaction for {tx_reference} found!",
                    "data": serializer.data,
                }
                encrypt_resp = encrypt(resp)
                return Response(
                    data=encrypt_resp,
                    status=status.HTTP_200_OK,
                )

            # Attempt to retrieve from TvSubscription.
            tvSub_instance = ValueAddedServices.objects.filter(
                user=user, tx_reference=tx_reference
            ).first()
            if tvSub_instance:
                serializer = BillPaymentSerializer(tvSub_instance)
                resp = {
                    "status": "success",
                    "message:": f"Transaction for {tx_reference} found!",
                    "data": serializer.data,
                }
                encrypt_resp = encrypt(resp)
                return Response(
                    data=encrypt_resp,
                    status=status.HTTP_200_OK,
                )

            # # Attempt to retrieve from WaecRegistration.
            # waec_reg_instance = WaecRegistration.objects.filter(
            #     user=user, tx_reference=tx_reference
            # ).first()
            # if waec_reg_instance:
            #     serializer = WaecRegistrationSerializer(waec_reg_instance)
            #     return Response(
            #         data={
            #             "status": "success",
            #             "message:": f"Transaction for {tx_reference} found!",
            #             "data": serializer.data,
            #         },
            #         status=status.HTTP_200_OK,
            #     )

            # # Attempt to retrieve from HealthInsurance.
            # health_insurance_instance = HealthInsurance.objects.filter(
            #     user=user, tx_reference=tx_reference
            # ).first()
            # if health_insurance_instance:
            #     serializer = HealthInsuranceSerializer(health_insurance_instance)
            #     return Response(
            #         data={
            #             "status": "success",
            #             "message:": f"Transaction for {tx_reference} found!",
            #             "data": serializer.data,
            #         },
            #         status=status.HTTP_200_OK,
            #     )

            # # Attempt to retrieve from VehicleInsurance.
            # vehicle_insurance_instance = VehicleInsurance.objects.filter(
            #     user=user, tx_reference=tx_reference
            # ).first()
            # if vehicle_insurance_instance:
            #     serializer = VehicleInsuranceSerializer(vehicle_insurance_instance)
            #     return Response(
            #         data={
            #             "status": "success",
            #             "message:": f"Transaction for {tx_reference} found!",
            #             "data": serializer.data,
            #         },
            #         status=status.HTTP_200_OK,
            #     )

            # # Attempt to retrieve from TvSubscription.
            # tvSub_instance = AccidentInsurance.objects.filter(
            #     user=user, tx_reference=tx_reference
            # ).first()
            # if tvSub_instance:
            #     serializer = AccidentInsuranceSerializer(tvSub_instance)
            #     return Response(
            #         data={
            #             "status": "success",
            #             "message:": f"Transaction for {tx_reference} found!",
            #             "data": serializer.data,
            #         },
            #         status=status.HTTP_200_OK,
            #     )

            # # Attempt to retrieve from HomeCoverInsurance.
            # home_cover_instance = HomeCoverInsurance.objects.filter(
            #     user=user, tx_reference=tx_reference
            # ).first()
            # if home_cover_instance:
            #     serializer = HomeCoverInsuranceSerializer(home_cover_instance)
            #     return Response(
            #         data={
            #             "status": "success",
            #             "message:": f"Transaction for {tx_reference} found!",
            #             "data": serializer.data,
            #         },
            #         status=status.HTTP_200_OK,
            #     )

            # If none of the above, return 404
            return Response(
                data=encrypt({"status": "fail", "detail": "Transaction not found."}),
                status=status.HTTP_404_NOT_FOUND,
            )

        except Exception as e:
            return Response(
                data=encrypt({"error": str(e)}), status=status.HTTP_400_BAD_REQUEST
            )
