import logging
import random
import string
import time
from decimal import Decimal

import jwt
from decouple import config
from django.conf import settings
from django.db import transaction
from django.db.models import F

from banking.controllers import Wallet
from banking.models import WalletModel
from .models import ReferralAgent, AgentReferral, AgentSignupBonus, AgentSettings

logger = logging.getLogger(__name__)

CODE_RANDOM_LENGTH = 6
AGENT_CODE_SUFFIX = "AGT"
WEB_TOKEN_TTL_SECONDS = 5 * 60
agent_dashboard_url = config("REFERRAL_AGENT_DASHBOARD_URL")


class ReferralAgentService:
    @staticmethod
    def _generate_agent_code(user):
        """Loop-until-unique generator scoped to ReferralAgent.agent_code -
        mirrors gamification.referrals.Referrals.generate_code, but that
        helper only checks User.referral_code/walk_to_earn_referral_code, not
        this table, so it can't be reused directly here."""
        prefix = (user.first_name or "USER").upper().replace(" ", "")[:5]
        while True:
            suffix = "".join(
                random.choices(
                    string.ascii_uppercase + string.digits, k=CODE_RANDOM_LENGTH
                )
            )
            code = f"{prefix}{suffix}{AGENT_CODE_SUFFIX}"
            if not ReferralAgent.objects.filter(agent_code=code).exists():
                return code

    @classmethod
    def onboard(cls, user):
        agent = ReferralAgent.objects.filter(user=user).first()
        if agent:
            return agent
        return ReferralAgent.objects.create(
            user=user, agent_code=cls._generate_agent_code(user)
        )

    @staticmethod
    def issue_web_dashboard_url(agent):
        """Builds the full agent-dashboard link, token included, so the
        mobile app never needs to know the dashboard's domain itself - only
        this module reads REFERRAL_AGENT_DASHBOARD_URL."""
        payload = {
            "agent_id": agent.id,
            "iat": int(time.time()),
            "exp": int(time.time()) + WEB_TOKEN_TTL_SECONDS,
        }
        token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
        separator = "&" if "?" in agent_dashboard_url else "?"
        return f"{agent_dashboard_url}{separator}token={token}"

    @staticmethod
    def resolve_web_token(token):
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        return ReferralAgent.objects.get(id=payload["agent_id"])

    @staticmethod
    @transaction.atomic
    def record_referral(agent, referred_user, code_used):
        """Called once at registration when referred_user signed up with
        agent.agent_code. Does not credit the bonus yet - that only happens
        once the referred user actually creates a wallet, see
        credit_signup_bonus."""
        return AgentReferral.objects.create(
            agent=agent, referred=referred_user, agent_code_used=code_used
        )

    @staticmethod
    @transaction.atomic
    def credit_signup_bonus(referred_user):
        ref = (
            AgentReferral.objects.select_for_update()
            .filter(referred=referred_user, bonus_credited=False)
            .first()
        )
        if not ref:
            return
        amount = AgentSettings.get_solo().signup_bonus_amount
        AgentSignupBonus.objects.create(agent_referral=ref, amount=amount)
        ref.bonus_credited = True
        ref.save(update_fields=["bonus_credited"])
        ReferralAgent.objects.filter(id=ref.agent_id).update(
            balance=F("balance") + amount
        )

    @staticmethod
    @transaction.atomic
    def withdraw(agent):
        """Moves agent.balance into the user's real, bank-backed wallet via
        Wallet.Credit (the 9PSB credit/transfer call banking.transfers uses
        for every other wallet credit) rather than incrementing
        WalletModel.balance directly - that field isn't locally writable
        source of truth, see banking/transfers.py's Paystack funding flow,
        which never touches it after a successful Wallet.Credit either.

        Returns (success, agent). On failure agent.balance is left untouched
        so the withdrawal can be retried.
        """
        agent = ReferralAgent.objects.select_for_update().get(id=agent.id)
        if agent.balance <= 0:
            return True, agent

        wallet = WalletModel.objects.get(user=agent.user, walletType="INDIVIDUAL")
        amount = agent.balance
        response = Wallet.Credit(
            acct_no=wallet.account_number,
            amount=float(amount),
            reason=f"Referral agent balance withdrawal for {agent.agent_code}.",
        )
        if not response or response.status_code != 200:
            logger.error(
                "Agent withdrawal credit failed for agent %s: %s",
                agent.agent_code,
                getattr(response, "text", "no response"),
            )
            return False, agent

        agent.balance = Decimal("0.00")
        agent.save(update_fields=["balance"])
        return True, agent
