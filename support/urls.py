from django.urls import path

from .views import CreateTicket, AssignTicket, GetAllSupportTickets, GetSingleTicket, RateSupportAgent

urlpatterns = [
    path("create", CreateTicket.as_view(), name="create_ticket"),
    path("assign", AssignTicket.as_view(), name="assign_ticket"),
    path("get-all", GetAllSupportTickets.as_view(), name="get_all"),
    path("get-single/<uuid:ticket_id>/", GetSingleTicket.as_view(), name="get_single_ticket"),
    path("rate-support-agent/<uuid:ticket_id>/<uuid:agent_id>/", RateSupportAgent.as_view(), name="rate_agent"),
]
