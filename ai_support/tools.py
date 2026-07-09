import json
import logging

from django.utils import timezone

from banking.models import WalletModel, TransferModel, Cashback
from gamification.models import Points, PointTransaction
from support.models import Ticket
from vas.models import ValueAddedServices

logger = logging.getLogger(__name__)

TOOLS = [
    {
        "name": "get_wallet_info",
        "description": "Get the user's wallet balance, cashback balance, tier level, and account status.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_recent_transfers",
        "description": "Get the user's recent transfers with status, amount, and beneficiary details.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Number of transfers to fetch (default 5, max 10).",
                }
            },
            "required": [],
        },
    },
    {
        "name": "get_cashback_info",
        "description": "Get the user's cashback balance and recent cashback history.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_vas_transactions",
        "description": "Get the user's recent VAS purchases (airtime, data, electricity, cable TV).",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Filter by category name e.g. 'airtime', 'data', 'electricity', 'cable'.",
                }
            },
            "required": [],
        },
    },
    {
        "name": "get_points_info",
        "description": "Get the user's points balance, tier, and recent point transactions.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_ticket_status",
        "description": (
            "Get the status of the user's support ticket(s). Pass ticket_number to check "
            "a specific ticket, or omit it to get their most recent tickets."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticket_number": {
                    "type": "string",
                    "description": "The ticket number to look up, e.g. 'TCK0123'. Omit for the user's most recent tickets.",
                }
            },
            "required": [],
        },
    },
    {
        "name": "create_support_ticket",
        "description": (
            "Escalate to a human support agent by creating a ticket. "
            "Use this when: (1) the issue involves external service delivery "
            "(token not working, data not activated, transfer sent but recipient didn't receive), "
            "(2) the issue requires manual investigation, "
            "(3) you cannot resolve the issue from available data. "
            "Do NOT use for questions you can answer directly."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Brief title of the issue."},
                "description": {
                    "type": "string",
                    "description": "Full description including what the user said and relevant data already pulled.",
                },
                "category": {
                    "type": "string",
                    "description": "One of: Transfer Issue, VAS Issue, Account Issue, Points Issue, KYC Issue, Other.",
                },
                "priority": {
                    "type": "string",
                    "enum": ["Low", "Medium", "High"],
                    "description": "Ticket priority.",
                },
                "conversation_summary": {
                    "type": "string",
                    "description": (
                        "Internal summary for the agent: what the user asked, what data you "
                        "already looked up and found, and what you already ruled out. Lets the "
                        "agent skip re-asking things already covered."
                    ),
                },
            },
            "required": ["title", "description", "category", "priority", "conversation_summary"],
        },
    },
]


def execute_tool(name, inputs, user, session):
    handlers = {
        "get_wallet_info": _get_wallet_info,
        "get_recent_transfers": _get_recent_transfers,
        "get_cashback_info": _get_cashback_info,
        "get_vas_transactions": _get_vas_transactions,
        "get_points_info": _get_points_info,
        "get_ticket_status": _get_ticket_status,
        "create_support_ticket": _create_support_ticket,
    }
    handler = handlers.get(name)
    if not handler:
        return {"data": {"error": f"Unknown tool: {name}"}, "escalated": False}
    return handler(inputs, user, session)


def _get_wallet_info(inputs, user, session):
    try:
        wallet = WalletModel.objects.filter(user=user).first()
        if not wallet:
            return {"data": {"error": "No wallet found for this user."}, "escalated": False}
        return {
            "data": {
                "balance": str(wallet.balance),
                "cashback_balance": str(wallet.cashback_balance),
                "tier_level": wallet.tier_level,
                "account_number": wallet.account_number,
                "status": "Active" if wallet.status else "Inactive",
                "pin_locked": wallet.pin_locked_until is not None and wallet.pin_locked_until > timezone.now(),
                "pin_locked_until": wallet.pin_locked_until.isoformat() if wallet.pin_locked_until else None,
                "tier2_upgrade_status": wallet.tier2_upgrade_status,
            },
            "escalated": False,
        }
    except Exception as e:
        logger.error("get_wallet_info failed for user %s: %s", user.id, e)
        return {"data": {"error": "Could not retrieve wallet info."}, "escalated": False}


def _get_recent_transfers(inputs, user, session):
    try:
        limit = min(int(inputs.get("limit", 5)), 10)
        transfers = TransferModel.objects.filter(user=user).order_by("-created_at")[:limit]
        return {
            "data": [
                {
                    "amount": str(t.amount),
                    "currency": t.currency,
                    "beneficiary_name": t.beneficiary_name,
                    "beneficiary_account": t.beneficiary_account_number,
                    "status": t.transaction_type,
                    "narration": t.narration,
                    "reference": t.tx_reference,
                    "date": t.created_at.isoformat(),
                }
                for t in transfers
            ],
            "escalated": False,
        }
    except Exception as e:
        logger.error("get_recent_transfers failed for user %s: %s", user.id, e)
        return {"data": {"error": "Could not retrieve transfers."}, "escalated": False}


def _get_cashback_info(inputs, user, session):
    try:
        wallet = WalletModel.objects.filter(user=user).first()
        cashbacks = Cashback.objects.filter(user=user).order_by("-created_at")[:5]
        return {
            "data": {
                "cashback_balance": str(wallet.cashback_balance) if wallet else "0.00",
                "recent_cashbacks": [
                    {
                        "amount": str(c.amount),
                        "service_type": c.service_type,
                        "date": c.created_at.isoformat(),
                        "expires_at": c.expires_at.isoformat() if c.expires_at else None,
                    }
                    for c in cashbacks
                ],
            },
            "escalated": False,
        }
    except Exception as e:
        logger.error("get_cashback_info failed for user %s: %s", user.id, e)
        return {"data": {"error": "Could not retrieve cashback info."}, "escalated": False}


def _get_vas_transactions(inputs, user, session):
    try:
        qs = ValueAddedServices.objects.filter(user=user).order_by("-created_at")
        category = inputs.get("category", "").lower()
        if category:
            qs = qs.filter(category_name__icontains=category)
        transactions = qs[:10]
        return {
            "data": [
                {
                    "category": t.category_name,
                    "item": t.itemName,
                    "amount": str(t.amount),
                    "phone_number": t.phone_number,
                    "status": t.status,
                    "date": t.created_at.isoformat() if hasattr(t, "created_at") else None,
                }
                for t in transactions
            ],
            "escalated": False,
        }
    except Exception as e:
        logger.error("get_vas_transactions failed for user %s: %s", user.id, e)
        return {"data": {"error": "Could not retrieve VAS transactions."}, "escalated": False}


def _get_points_info(inputs, user, session):
    try:
        points = Points.objects.filter(user=user).first()
        recent_txns = PointTransaction.objects.filter(user=user).order_by("-created_at")[:5]
        return {
            "data": {
                "balance": points.balance if points else 0,
                "tier": points.tier if points else "Starter",
                "naira_value": str(points.naira_value) if points else "0.00",
                "recent_transactions": [
                    {
                        "type": t.transaction_type,
                        "amount": t.amount,
                        "reason": t.reason,
                        "source": t.source,
                        "balance_after": t.balance_after,
                        "date": t.created_at.isoformat(),
                    }
                    for t in recent_txns
                ],
            },
            "escalated": False,
        }
    except Exception as e:
        logger.error("get_points_info failed for user %s: %s", user.id, e)
        return {"data": {"error": "Could not retrieve points info."}, "escalated": False}


def _get_ticket_status(inputs, user, session):
    try:
        qs = Ticket.objects.filter(user=user, deleted=False).order_by("-created_at")
        ticket_number = inputs.get("ticket_number")
        if ticket_number:
            qs = qs.filter(number=ticket_number)
        tickets = qs[:5]
        if not tickets:
            return {"data": {"error": "No matching ticket found."}, "escalated": False}
        return {
            "data": [
                {
                    "ticket_number": t.number,
                    "title": t.title,
                    "category": t.category,
                    "status": t.status,
                    "priority": t.priority,
                    "opened_at": t.opened_at.isoformat() if t.opened_at else None,
                    "resolved_at": t.resolved_at.isoformat() if t.resolved_at else None,
                    "assigned": t.assigned_to is not None,
                }
                for t in tickets
            ],
            "escalated": False,
        }
    except Exception as e:
        logger.error("get_ticket_status failed for user %s: %s", user.id, e)
        return {"data": {"error": "Could not retrieve ticket status."}, "escalated": False}


def _create_support_ticket(inputs, user, session):
    try:
        full_name = user.full_name or f"{user.first_name or ''} {user.last_name or ''}".strip()
        ticket = Ticket.objects.create(
            user=user,
            title=inputs["title"],
            description=inputs["description"],
            ai_summary=inputs["conversation_summary"],
            category=inputs["category"],
            priority=inputs["priority"],
            channel="AI Assistant",
            status="New",
            customer_name=full_name,
            customer_email=user.email,
            customer_phone_number=user.phone_number,
            opened_at=timezone.now(),
        )
        session.escalate(ticket)
        logger.info("AI support escalated to ticket %s for user %s", ticket.number, user.id)
        return {
            "data": {"ticket_number": ticket.number, "status": "created"},
            "escalated": True,
            "ticket_number": ticket.number,
        }
    except Exception as e:
        logger.error("create_support_ticket failed for user %s: %s", user.id, e)
        return {"data": {"error": "Could not create support ticket."}, "escalated": False}
