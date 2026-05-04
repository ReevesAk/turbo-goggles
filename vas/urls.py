from django.urls import path
from .views import (
    AirTimeTopUp,
    DataSubscriptionView,
    GetDataPlans,
    BillPaymentCategoriesView,
    BillersCategoriesView,
    VerifyBillerAccountView,
    BillPaymentView,
)

app_name = "vas"


urlpatterns = [
    path(
        "airtime-topup",
        AirTimeTopUp.as_view(),
        name="airtime_topup",
    ),
    path(
        "get-productIds/<str:phone_number>/",
        GetDataPlans.as_view(),
        name="variation_codes",
    ),
    path("subscribe-data", DataSubscriptionView.as_view(), name="data_subscription"),
    path(
        "bill-payment-categories/<str:category_id>/",
        BillPaymentCategoriesView.as_view(),
        name="bill_payment_categories",
    ),
    path(
        "billers-categories/<str:billers_id>/",
        BillersCategoriesView.as_view(),
        name="billers_categories",
    ),
    path(
        "verify-biller-account/",
        VerifyBillerAccountView.as_view(),
        name="verify_biller_account",
    ),
    path("bill-payment/", BillPaymentView.as_view(), name="bill_payment"),
    # path("waec-registration/", WaecRegistration.as_view(), name="waec_registration"),
]
