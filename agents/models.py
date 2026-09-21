from decimal import Decimal

from django.db import models

from accounts.models import User


class ReferralAgent(models.Model):
    """A member who has opted into the referral-agent program. Distinct from
    the privileged accounts.User "Agent" role (USER_CATEGORY_CHOICES) and its
    agent_pin - this is an ordinary member sharing agent_code to bring new
    users onto the platform."""

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="referral_agent"
    )
    agent_code = models.CharField(max_length=50, unique=True, db_index=True)
    status = models.CharField(max_length=20, default="active")
    balance = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.agent_code} ({self.user_id})"


class AgentReferral(models.Model):
    """One row per user who registered using a ReferralAgent's agent_code.
    referred is OneToOne so a user can be claimed by exactly one agent."""

    agent = models.ForeignKey(
        ReferralAgent, on_delete=models.CASCADE, related_name="referrals"
    )
    referred = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="referred_by_agent"
    )
    agent_code_used = models.CharField(max_length=50)
    bonus_credited = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.referred_id} referred by {self.agent.agent_code}"


class AgentSignupBonus(models.Model):
    """Snapshot of the flat bonus paid out for one AgentReferral - append-only,
    created at most once per agent_referral (see the OneToOne). Snapshots
    AgentSettings.signup_bonus_amount at credit time so a later rate change
    doesn't shift historical figures - same pattern as banking.CashbackRule /
    partners.PartnerCommissionRule."""

    agent_referral = models.OneToOneField(
        AgentReferral, on_delete=models.CASCADE, related_name="bonus"
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)


class AgentSettings(models.Model):
    """Singleton admin-configurable settings for the referral-agent program.
    Use AgentSettings.get_solo() rather than querying directly - there is
    always exactly one row (id=1)."""

    signup_bonus_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("500.00")
    )

    def __str__(self):
        return f"Agent settings (signup bonus: {self.signup_bonus_amount})"

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(id=1)
        return obj
