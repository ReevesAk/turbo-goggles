from django.contrib import admin

from .models import (
    BrandTaskSubmission,
    SocialProfile,
    SocialTask,
    TaskSubmission,
    UserTrustScore,
    VerificationResult,
)


@admin.register(SocialTask)
class SocialTaskAdmin(admin.ModelAdmin):
    list_display = ["title", "platform", "task_type", "reward_points", "is_active", "total_submissions", "max_submissions"]
    list_filter = ["platform", "task_type", "is_active"]
    search_fields = ["title", "target_account"]


@admin.register(TaskSubmission)
class TaskSubmissionAdmin(admin.ModelAdmin):
    list_display = ["user", "task", "status", "reward_issued", "created_at"]
    list_filter = ["status", "reward_issued", "task__platform"]
    search_fields = ["user__email", "task__title"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(VerificationResult)
class VerificationResultAdmin(admin.ModelAdmin):
    list_display = ["submission", "verdict", "confidence_score", "action_confirmed"]
    list_filter = ["verdict"]


@admin.register(UserTrustScore)
class UserTrustScoreAdmin(admin.ModelAdmin):
    list_display = ["user", "score", "total_submissions", "approved_submissions", "rejected_submissions"]
    search_fields = ["user__email"]


@admin.register(SocialProfile)
class SocialProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "x_username", "instagram_username", "facebook_username", "tiktok_username"]
    search_fields = ["user__email", "x_username", "instagram_username"]


@admin.register(BrandTaskSubmission)
class BrandTaskSubmissionAdmin(admin.ModelAdmin):
    list_display = ["user", "ad", "task_type_display", "status", "reward_issued", "created_at"]
    list_filter = ["status", "reward_issued", "ad__task_type"]
    search_fields = ["user__email", "ad__campaign_name", "ad__business_or_brand_name"]
    readonly_fields = ["created_at", "updated_at", "reward_issued"]

    def task_type_display(self, obj):
        return obj.ad.get_task_type_display() if obj.ad.task_type else "-"
    task_type_display.short_description = "Task Type"
