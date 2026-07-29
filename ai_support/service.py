import logging

import anthropic
from django.conf import settings

from .tools import TOOLS, execute_tool

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a support assistant for Picadailys, a Nigerian fintech super-app. \
You help users with questions about their wallet balance, transfers, airtime/data/electricity/cable \
purchases (VAS), cashback, rewards points, and existing support tickets.

Rules:
1. Always look up the user's actual data before answering — never guess balances or transaction status.
2. For issues involving external service delivery — electricity token not working on the meter, \
data not activated on the phone, transfer sent but recipient did not receive, cable subscription \
not activated — do NOT comment on status. Immediately create a support ticket without any further analysis.
3. Be concise and friendly. Write in plain English, not technical jargon.
4. Currency is Nigerian Naira (₦). Format amounts with the ₦ symbol.
5. If you cannot resolve the issue from the available data, escalate by creating a support ticket.
6. When escalating, tell the user only: "I've raised a support ticket for our team. \
An agent will reach out to you shortly." — nothing else about the issue.
7. If the user asks about an existing ticket (e.g. "what's happening with my ticket", "any update?"), \
use get_ticket_status to check it — do NOT create a new ticket for a status inquiry.
8. When creating a ticket, always fill in conversation_summary for the agent: what the user \
asked, what data you already checked and what it showed, and anything you already ruled out — \
so the agent doesn't repeat work you've already done."""


def run_ai_support(user, session):
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    escalated = False
    ticket_number = None

    while True:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=session.messages,
        )

        content_dicts = [block.model_dump() for block in response.content]
        session.messages.append({"role": "assistant", "content": content_dicts})

        if response.stop_reason == "end_turn":
            reply = next(
                (
                    block["text"]
                    for block in content_dicts
                    if block.get("type") == "text"
                ),
                "I'm sorry, I couldn't process that. Please try again.",
            )
            if not escalated:
                session.resolved_by_ai = True
            session.save()
            return {
                "reply": reply,
                "escalated": escalated,
                "ticket_number": ticket_number,
            }

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in content_dicts:
                if block.get("type") == "tool_use":
                    result = execute_tool(block["name"], block["input"], user, session)
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block["id"],
                            "content": str(result["data"]),
                        }
                    )
                    if result.get("escalated"):
                        escalated = True
                        ticket_number = result.get("ticket_number")

            session.messages.append({"role": "user", "content": tool_results})
            continue

        # Unexpected stop reason — bail out
        logger.warning(
            "Unexpected stop_reason '%s' for session %s",
            response.stop_reason,
            session.id,
        )
        session.save()
        return {
            "reply": "Something went wrong. Please try again.",
            "escalated": escalated,
            "ticket_number": ticket_number,
        }
