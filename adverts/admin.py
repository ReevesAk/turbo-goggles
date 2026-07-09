from django.contrib import admin

from .models import CreateAd, AdMedia, AdLocation, StoreVisitQRCode


class AdLocationInline(admin.TabularInline):
    model = AdLocation
    extra = 0


class AdMediaInline(admin.TabularInline):
    model = AdMedia
    extra = 0


@admin.register(CreateAd)
class CreateAdAdmin(admin.ModelAdmin):
    list_display = [
        "campaign_name",
        "business_or_brand_name",
        "task_type",
        "reward_points",
        "is_active",
        "created_at",
    ]
    list_filter = ["task_type", "is_active", "industry", "gender"]
    search_fields = ["campaign_name", "business_or_brand_name", "user__email"]
    readonly_fields = ["created_at", "updated_at"]
    inlines = [AdLocationInline, AdMediaInline]


@admin.register(StoreVisitQRCode)
class StoreVisitQRCodeAdmin(admin.ModelAdmin):
    list_display = ["ad", "token", "scan_count", "qr_image_url", "created_at"]
    readonly_fields = ["token", "scan_count", "created_at"]
    search_fields = ["ad__campaign_name", "ad__user__email"]
