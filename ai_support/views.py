import logging

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from .models import AISupportSession
from .serializers import ChatMessageSerializer, SessionHistorySerializer
from .service import run_ai_support

logger = logging.getLogger(__name__)


class ChatView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChatMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        session_id = serializer.validated_data.get("session_id")
        message = serializer.validated_data["message"]
        user = request.user

        if session_id:
            session = get_object_or_404(AISupportSession, id=session_id, user=user)
            if session.is_escalated:
                ticket_number = session.ticket.number if session.ticket else None
                return Response({
                    "session_id": str(session.id),
                    "reply": (
                        f"Your issue has already been escalated to our support team "
                        f"(Ticket #{ticket_number}). An agent will reach out to you shortly."
                    ),
                    "escalated": True,
                    "ticket_number": ticket_number,
                })
        else:
            session = AISupportSession.objects.create(user=user)

        session.messages.append({"role": "user", "content": message})

        try:
            result = run_ai_support(user, session)
        except Exception as e:
            logger.error("AI support error for user %s session %s: %s", user.id, session.id, e)
            session.messages.append({
                "role": "assistant",
                "content": "I'm having trouble right now. Please try again in a moment.",
            })
            session.save()
            return Response({
                "session_id": str(session.id),
                "reply": "I'm having trouble right now. Please try again in a moment.",
                "escalated": False,
                "ticket_number": None,
            }, status=status.HTTP_200_OK)

        return Response({
            "session_id": str(session.id),
            "reply": result["reply"],
            "escalated": result["escalated"],
            "ticket_number": result.get("ticket_number"),
        }, status=status.HTTP_200_OK)


class SessionHistoryView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, session_id):
        session = get_object_or_404(AISupportSession, id=session_id, user=request.user)
        serializer = SessionHistorySerializer(session)
        return Response(serializer.data)


class SessionListView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        sessions = AISupportSession.objects.filter(user=request.user).order_by("-created_at")[:20]
        serializer = SessionHistorySerializer(sessions, many=True)
        return Response(serializer.data)
