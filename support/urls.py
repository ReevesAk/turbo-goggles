from django.urls import path

from .views import CreateTicket, AssignTicket, GetAllSupportTickets, GetSingleTicket

urlpatterns = [
    path("create", CreateTicket.as_view(), name="create_ticket"),
    path("assign", AssignTicket.as_view(), name="assign_ticket"),
    path("get-all", GetAllSupportTickets.as_view(), name="get_all"),
    path("get-single/<uuid:ticket_id>/", GetSingleTicket.as_view(), name="get_single_ticket")
]
