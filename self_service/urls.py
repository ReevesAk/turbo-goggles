from django.urls import path
from .views import (
    GymBooking,
    GymBookingList,
    GymBookingDetail,
    TableBooking,
    TableBookingList,
    TableBookingDetail,
    CinemaBookingView,
    CinemaBookingList,
    CinemaBookingDetail,
    BookCourierSercvice,
    CourierBookingList,
    CourierBookingDetail,
    BookConsumableSercvice,
    ConsumableBookingList,
    ConsumableBookingDetail,
)


urlpatterns = [
    path("table-booking/", TableBooking.as_view(), name="table_booking"),
    path("table-booking-list/", TableBookingList.as_view(), name="table_booking_list"),
    path(
        "table-booking-details/<int:id>/",
        TableBookingDetail.as_view(),
        name="table_booking_details",
    ),
    path("gym-subcription/", GymBooking.as_view(), name="gym_subcription"),
    path("gym-sub-list/", GymBookingList.as_view(), name="gym_sub_list"),
    path(
        "gym-subcription-details/<int:id>/",
        GymBookingDetail.as_view(),
        name="gym_subcription_details",
    ),
    path("cinema-booking/", CinemaBookingView.as_view(), name="cinema_booking"),
    path(
        "cinema-booking-list/", CinemaBookingList.as_view(), name="cinema_booking_list"
    ),
    path(
        "cinema_booking-details/<int:id>/",
        CinemaBookingDetail.as_view(),
        name="cinema_booking_details",
    ),
    path("courier-booking/", BookCourierSercvice.as_view(), name="courier_booking"),
    path(
        "courier-booking-list/",
        CourierBookingList.as_view(),
        name="courier_booking_list",
    ),
    path(
        "courier_booking-details/<int:id>/",
        CourierBookingDetail.as_view(),
        name="courier_booking_details",
    ),
    path(
        "consumable-booking/",
        BookConsumableSercvice.as_view(),
        name="consumable_booking",
    ),
    path(
        "consumable-booking-list/",
        ConsumableBookingList.as_view(),
        name="consumable_booking_list",
    ),
    path(
        "consumable-booking-details/<int:id>/",
        ConsumableBookingDetail.as_view(),
        name="consumable_booking_details",
    ),
]
