import jwt
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ReferralAgent
from .services import ReferralAgentService


class AgentStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        agent = ReferralAgent.objects.filter(user=request.user).first()
        return Response(
            {
                "is_agent": agent is not None,
                "has_wallet": request.user.has_wallet,
                "agent_code": agent.agent_code if agent else None,
            }
        )


class AgentOnboardView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not request.user.has_wallet:
            return Response(
                {"status": "fail", "message": "Create a wallet first."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        agent = ReferralAgentService.onboard(request.user)
        return Response({"agent_code": agent.agent_code})


class AgentWebTokenView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        agent = ReferralAgent.objects.filter(user=request.user).first()
        if not agent:
            return Response(
                {"status": "fail", "message": "Not registered as an agent."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({"url": ReferralAgentService.issue_web_dashboard_url(agent)})


def _resolve_agent(request):
    """Reads the short-lived handoff JWT (ReferralAgentService.issue_web_token)
    from the Authorization header. Deliberately separate from the app's normal
    session auth - this token identifies a ReferralAgent, not a logged-in
    User, and is only ever consumed by the web dashboard."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    try:
        return ReferralAgentService.resolve_web_token(auth.split(" ", 1)[1])
    except (jwt.PyJWTError, ReferralAgent.DoesNotExist):
        return None


class AgentMeView(APIView):
    permission_classes = []
    authentication_classes = []

    def get(self, request):
        agent = _resolve_agent(request)
        if not agent:
            return Response(status=status.HTTP_401_UNAUTHORIZED)
        return Response(
            {
                "agent_code": agent.agent_code,
                "balance": agent.balance,
                "referred_count": agent.referrals.count(),
            }
        )


class AgentReferralsView(APIView):
    permission_classes = []
    authentication_classes = []

    class _Pagination(PageNumberPagination):
        page_size = 20

    def get(self, request):
        agent = _resolve_agent(request)
        if not agent:
            return Response(status=status.HTTP_401_UNAUTHORIZED)
        referrals = agent.referrals.select_related("referred").order_by("-created_at")
        paginator = self._Pagination()
        page = paginator.paginate_queryset(referrals, request)
        data = [{"name": r.referred.full_name, "joined": r.created_at} for r in page]
        return paginator.get_paginated_response(data)


class AgentWithdrawView(APIView):
    permission_classes = []
    authentication_classes = []

    def post(self, request):
        agent = _resolve_agent(request)
        if not agent:
            return Response(status=status.HTTP_401_UNAUTHORIZED)
        ok, agent = ReferralAgentService.withdraw(agent)
        if not ok:
            return Response(
                {"status": "fail", "message": "Could not credit wallet - try again."},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response({"balance": agent.balance})
