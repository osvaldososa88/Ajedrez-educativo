from django.contrib import admin

from .models import Bot, BotProfile, BotProgress


@admin.register(BotProfile)
class BotProfileAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'engine_depth', 'move_time_ms', 'skill_level',
        'multipv', 'error_probability', 'uci_elo',
    )
    search_fields = ('name',)
    list_editable = ('engine_depth', 'skill_level', 'error_probability')


@admin.register(Bot)
class BotAdmin(admin.ModelAdmin):
    list_display = (
        'display_name', 'nickname', 'category', 'order', 'displayed_elo',
        'profile', 'is_active', 'avatar',
    )
    list_filter = ('category', 'is_active', 'profile')
    search_fields = ('display_name', 'nickname', 'description')
    list_editable = ('order', 'displayed_elo', 'is_active')
    ordering = ('category', 'order')
    list_per_page = 50


@admin.register(BotProgress)
class BotProgressAdmin(admin.ModelAdmin):
    list_display = ('user', 'bot', 'unlocked', 'defeated', 'defeated_at')
    list_filter = ('unlocked', 'defeated', 'bot__category')
    search_fields = ('user__username', 'bot__display_name')
    readonly_fields = ('created_at', 'updated_at')
