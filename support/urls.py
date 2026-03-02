from django.urls import path


from .views import (
    CreateTicket, RegisterManager, SupportPhoneVerifyOTP,
    AssignTicket, ReassignTicket, UpdateTicketStatus, GetAllSupportTickets, 
    GetSingleTicket, RateSupportAgent, GetTicketByChannel, UsersWithTickets,
    AddAgent, AgentSignUpComplete, LoginAgent, SetAgentPin,
    GetAllAgentModeratorAndSupportManager, DeleteTicket, GetMyAssignedTickets,
    EscalateTicketAPIView, TicketRRTrailAPIView, DisableAgentrole, EnableAgentrole, DeleteAgent,
    CompleteTicketAPIView, ListUserDetailsAPI, AgentForgotPin, AgentPinVerifyOTP, AgentResetPin
)


app_name = "support"


urlpatterns = [
    path("register-manager", RegisterManager.as_view(), name="register_manager"),
    path("verifyotp", SupportPhoneVerifyOTP.as_view(), name="verifyotp"),
    path("agent-forgot-pin", AgentForgotPin.as_view(), name="agent_forgot_pin"),
    path("verify-agent-pin-otp", AgentPinVerifyOTP.as_view(), name="verify_agent_pin_otp"),
    path("reset-agent-pin", AgentResetPin.as_view(), name="reset_agent_pin"),
    path("add-agent", AddAgent.as_view(), name="add_support_agent"),
    path("set-agent-pin", SetAgentPin.as_view(), name="set_agent_pin"),
    path("signup-complete/<str:user_id>/", AgentSignUpComplete.as_view(), name="signup-complete"),
    path("login", LoginAgent.as_view(), name="login_agent"),
    path("disable-agent", DisableAgentrole.as_view(), name="disable_agent"),
    path("re-enable-agent", EnableAgentrole.as_view(), name="enable_agent"),
    path("delete-agent", DeleteAgent.as_view(), name="delete_agent_users"),
    path("create", CreateTicket.as_view(), name="create_ticket"),
    path("assign/<str:ticket_number>/", AssignTicket.as_view(), name="assign_ticket"),
    path("reassign/<str:ticket_number>/", ReassignTicket.as_view(), name="reassign_ticket"),
    path("update-status/<str:ticket_number>/", UpdateTicketStatus.as_view(), name="update_ticket_status"),
    path("get-all", GetAllSupportTickets.as_view(), name="get_all"),
    path("my-assigned-tickets", GetMyAssignedTickets.as_view(), name="my_assigned_tickets"),
    path("delete-ticket/<str:ticket_number>/", DeleteTicket.as_view(), name="delete_ticket"),
    path("escalate-ticket/<str:ticket_id>/", EscalateTicketAPIView.as_view(), name="escalate_ticket"),
    path("ticket-rr-trail/<str:ticket_number>/", TicketRRTrailAPIView.as_view(), name="ticket_rr_trail"),
    path("get-all-agents-moderators-and-manager", GetAllAgentModeratorAndSupportManager.as_view(), name="get_all_agents_and_moderators"),
    path("get-single-ticket/<str:ticket_number>/", GetSingleTicket.as_view(), name="get_single_ticket"),
    path('users-with-tickets/', UsersWithTickets.as_view(), name='users-with-tickets'),
    path("rate-support-agent/<uuid:ticket_number>/<uuid:agent_id>/", RateSupportAgent.as_view(), name="rate_agent"),
    path("complete-ticket/<str:ticket_number>/", CompleteTicketAPIView.as_view(), name="complete_ticket"),
    path("list-user-details/", ListUserDetailsAPI.as_view(), name="list_user_details"),
    path("search-by-channel/<str:search_term>/", GetTicketByChannel.as_view(), name="serach_channel")
]
