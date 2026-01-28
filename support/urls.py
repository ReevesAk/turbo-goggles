from django.urls import path


from .views import (
    CreateTicket, RegisterManager, SupportPhoneVerifyOTP,
    AssignTicket, ReassignTicket, UpdateTicketStatus, GetAllSupportTickets, 
    GetSingleTicket, RateSupportAgent, GetTicketByChannel, UsersWithTickets,
    AddAgent, AgentSignUpComplete, LoginAgent, SetAgentPin,
    GetAllAgentAndModeratorUsers, DeleteTicket, GetMyAssignedTickets,
    EscalateTicketAPIView, TicketRRTrailAPIView,
)


app_name = "support"


urlpatterns = [
    path("register-manager", RegisterManager.as_view(), name="register_manager"),
    path("verifyotp", SupportPhoneVerifyOTP.as_view(), name="verifyotp"),
    path("add-agent", AddAgent.as_view(), name="add_support_agent"),
    path("set-agent-pin", SetAgentPin.as_view(), name="set_agent_pin"),
    path("signup-complete/<str:user_id>/", AgentSignUpComplete.as_view(), name="signup-complete"),
    path("login", LoginAgent.as_view(), name="login_agent"),
    path("create", CreateTicket.as_view(), name="create_ticket"),
    path("assign/<str:ticket_number>/", AssignTicket.as_view(), name="assign_ticket"),
    path("reassign/<str:ticket_number>/", ReassignTicket.as_view(), name="reassign_ticket"),
    path("update-status/<str:ticket_number>/", UpdateTicketStatus.as_view(), name="update_ticket_status"),
    path("get-all", GetAllSupportTickets.as_view(), name="get_all"),
    path("my-assigned-tickets", GetMyAssignedTickets.as_view(), name="my_assigned_tickets"),
    path("delete-ticket/<str:ticket_number>/", DeleteTicket.as_view(), name="delete_ticket"),
    path("escalate-ticket/<str:ticket_id>/", EscalateTicketAPIView.as_view(), name="escalate_ticket"),
    path("ticket-rr-trail/<str:ticket_id>/", TicketRRTrailAPIView.as_view(), name="ticket_rr_trail"),
    path("get-all-agents-and-moderators", GetAllAgentAndModeratorUsers.as_view(), name="get_all_agents_and_moderators"),
    path("get-single-ticket/<str:ticket_number>/", GetSingleTicket.as_view(), name="get_single_ticket"),
    path('users-with-tickets/', UsersWithTickets.as_view(), name='users-with-tickets'),
    path("rate-support-agent/<uuid:ticket_number>/<uuid:agent_id>/", RateSupportAgent.as_view(), name="rate_agent"),
    path("search-by-channel/<str:search_term>/", GetTicketByChannel.as_view(), name="serach_channel")
]
