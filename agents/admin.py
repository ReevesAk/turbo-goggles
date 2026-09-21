from django.contrib import admin

from .models import ReferralAgent, AgentReferral, AgentSignupBonus, AgentSettings


@admin.register(AgentSettings)
class AgentSettingsAdmin(admin.ModelAdmin):
    list_display = ("signup_bonus_amount",)

    def has_add_permission(self, request):
        # Singleton row (id=1, see AgentSettings.get_solo) - edit it, never add another.
        return not AgentSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ReferralAgent)
class ReferralAgentAdmin(admin.ModelAdmin):
    list_display = ("agent_code", "user", "balance", "status", "created_at")
    search_fields = ("agent_code", "user__email")


@admin.register(AgentReferral)
class AgentReferralAdmin(admin.ModelAdmin):
    list_display = ("agent", "referred", "bonus_credited", "created_at")
    list_filter = ("bonus_credited",)


@admin.register(AgentSignupBonus)
class AgentSignupBonusAdmin(admin.ModelAdmin):
    list_display = ("agent_referral", "amount", "created_at")
