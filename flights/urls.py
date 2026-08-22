from django.urls import path

from .views import (
    AirportSearchView,
    FareRulesView,
    FlightBookingView,
    FlightCancelView,
    FlightRevalidateView,
    FlightSearchView,
)

app_name = "flights"


urlpatterns = [
    path("search/", FlightSearchView.as_view(), name="flight_search"),
    path("revalidate/", FlightRevalidateView.as_view(), name="flight_revalidate"),
    path("fare-rules/", FareRulesView.as_view(), name="flight_fare_rules"),
    path("book/", FlightBookingView.as_view(), name="flight_booking"),
    path("cancel/", FlightCancelView.as_view(), name="flight_cancel"),
    path("airports/", AirportSearchView.as_view(), name="airport_search"),
]
