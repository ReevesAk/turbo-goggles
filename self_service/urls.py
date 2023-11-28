from django.urls import path
from .views import GymBooking, GymBookingList, TableBooking, TableBookingList


urlpatterns = [
    path("table-booking/", TableBooking.as_view(), name="table_booking"),
    path("table-booking-list/", TableBookingList.as_view(), name="table_booking_list"),
    path("gym-subcription/", GymBooking.as_view(), name="gym_subcription"),
    path("gym-sub-list/", GymBookingList.as_view(), name="gym_sub_list"),
]
